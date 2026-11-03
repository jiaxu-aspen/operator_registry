/** Private registry API. Tokens belong to individual clients, not to cards.
 * CLIENTS_JSON is a Worker secret mapping client IDs to {hash, role}.
 * Only SHA-256 digests of random 256-bit client secrets are stored in it.
 * Cloudflare account credentials are never distributed to desktop clients.
 */
const MAX_BYTES = 512000;
const reply = (body, status = 200) => Response.json(body, {
  status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }
});

/** Strict validation is shared by upload and tests; never coerce active flags. */
export function validateRecords(records) {
  if (!Array.isArray(records) || records.length > 1000) throw new Error('Invalid record count (maximum 1000).');
  const seen = new Set();
  return records.map(r => {
    if (!r || typeof r !== 'object' || typeof r.uid !== 'string' ||
        !/^(?:[0-9A-F]{2}){1,256}$/.test(r.uid) || seen.has(r.uid) ||
        typeof r.name !== 'string' || !r.name.trim() || r.name.length > 100 ||
        typeof r.initials !== 'string' || !/^[A-Z]{1,10}$/.test(r.initials) ||
        ![0, 1].includes(r.active)) throw new Error('Invalid or duplicate operator record.');
    seen.add(r.uid);
    return {uid:r.uid, name:r.name.trim(), initials:r.initials, active:r.active};
  }).sort((a,b) => a.uid.localeCompare(b.uid));
}

/** Hash comparison has fixed work after format checks; no secret is logged. */
async function authenticate(request, env) {
  const match = /^Bearer ([a-zA-Z0-9_-]{1,64})\.([a-zA-Z0-9_-]{43,128})$/.exec(request.headers.get('Authorization') || '');
  if (!match) return null;
  const clients = JSON.parse(env.CLIENTS_JSON || '{}');
  const client = clients[match[1]];
  if (!client || !['reader','admin'].includes(client.role) || !/^[a-f0-9]{64}$/.test(client.hash)) return null;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(match[2]));
  const actual = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2,'0')).join('');
  let mismatch = 0;
  for (let i=0;i<64;i++) mismatch |= actual.charCodeAt(i)^client.hash.charCodeAt(i);
  return mismatch ? null : {id:match[1], role:client.role};
}

/** Read bounded JSON even when Content-Length is absent or untrustworthy. */
async function readBody(request) {
  if (!request.body) throw new Error('Missing request body.');
  const reader = request.body.getReader();
  const chunks=[]; let total=0;
  while (true) {
    const {done,value}=await reader.read(); if(done) break;
    total+=value.length;
    if(total>MAX_BYTES) {await reader.cancel();throw new Error('Request too large.');}
    chunks.push(value);
  }
  const bytes=new Uint8Array(total);let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  return JSON.parse(new TextDecoder().decode(bytes));
}

export default {
  /** All reads use the D1 primary (no replica session or edge cache). */
  async fetch(request, env) {
    try {
      const url=new URL(request.url);
      if(url.protocol!=='https:') return reply({error:'HTTPS required.'},400);
      const client=await authenticate(request,env);
      if(!client) return reply({error:'Registry credentials rejected.'},401);
      const path=url.pathname;
      if(request.method==='POST' && path==='/v1/check') {
        let body;try{body=await readBody(request);}catch{return reply({error:'Invalid request.'},400);}
        if(typeof body.uid!=='string' || !/^(?:[0-9A-F]{2}){1,256}$/.test(body.uid))return reply({error:'Invalid card ID.'},400);
        const row=await env.DB.prepare('SELECT * FROM revisions ORDER BY version DESC LIMIT 1').first();
        const record=JSON.parse(row.records).find(r=>r.uid===body.uid);
        if(!record)return reply({error:'Card is not registered.'},404);
        if(record.active!==1)return reply({error:'This card is disabled.'},403);
        return reply({record,version:row.version,checked_utc:new Date().toISOString()});
      }
      // Station credentials only check a card; only administrators list/publish.
      if(path==='/v1/registry' && ['GET','PUT'].includes(request.method)) {
        if(client.role!=='admin')return reply({error:'Registry administrator access required.'},403);
        const current=await env.DB.prepare('SELECT * FROM revisions ORDER BY version DESC LIMIT 1').first();
        if(request.method==='GET')return reply({records:JSON.parse(current.records),version:current.version,published_utc:current.published_utc});
        let body,records;
        try {
          body=await readBody(request);records=validateRecords(body.records);
          if(!Number.isSafeInteger(body.base_version)||body.base_version<0)throw new Error();
        } catch{return reply({error:'Invalid upload. Maximum 1000 unique records.'},400);}
        if(body.base_version!==current.version)return reply({error:'Cloud registry changed. Retrieve latest before publishing.'},409);
        const ids=new Set(records.map(r=>r.uid));
        if(JSON.parse(current.records).some(r=>!ids.has(r.uid)))return reply({error:'Upload cannot remove cards. Disable them instead.'},400);
        const stamp=new Date().toISOString();
        // Compare-and-swap occurs inside a single SQL statement, including races
        // after the earlier validation read. Old revisions retain audit history.
        const saved=await env.DB.prepare(`INSERT INTO revisions(version,records,published_utc,published_by)
          SELECT ?,?,?,? WHERE (SELECT MAX(version) FROM revisions)=? RETURNING version`)
          .bind(body.base_version+1,JSON.stringify(records),stamp,client.id,body.base_version).first();
        if(!saved)return reply({error:'Cloud registry changed. Retrieve latest before publishing.'},409);
        return reply({version:saved.version,published_utc:stamp});
      }
      return reply({error:'Unknown registry operation.'},404);
    } catch {
      // Avoid leaking database errors, configuration, or submitted identities.
      return reply({error:'Cloud registry unavailable. Try again later.'},503);
    }
  }
};
