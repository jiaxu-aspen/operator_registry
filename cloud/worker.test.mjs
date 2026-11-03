/** Exercise the real fetch handler and SQL with SQLite, without Cloudflare or cards. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import worker from './worker.mjs';

const secret='x'.repeat(43);
const row={uid:'0001',name:'Example Operator',initials:'EO',active:1};
function fixture(){
  const sql=new DatabaseSync(':memory:');sql.exec(readFileSync(new URL('schema.sql',import.meta.url),'utf8'));
  const hash=createHash('sha256').update(secret).digest('hex');
  const env={CLIENTS_JSON:JSON.stringify({admin:{role:'admin',hash},station:{role:'reader',hash}}),
    DB:{prepare(text){return {args:[],bind(...args){this.args=args;return this;},
      async first(){return sql.prepare(text).get(...this.args)||null;}};}}};
  const call=(method,path,body,client='admin')=>worker.fetch(new Request('https://registry.example'+path,{
    method,headers:{Authorization:`Bearer ${client}.${secret}`},body:body===undefined?undefined:JSON.stringify(body)}),env);
  return {sql,env,call};
}

test('authentication and roles protect both reads and publication',async()=>{
  const f=fixture();
  assert.equal((await f.call('GET','/v1/registry',undefined,'unknown')).status,401);
  assert.equal((await f.call('GET','/v1/registry',undefined,'station')).status,403);
  assert.equal((await f.call('PUT','/v1/registry',{records:[row],base_version:0},'station')).status,403);
  assert.equal(f.sql.prepare('SELECT count(*) AS n FROM revisions').get().n,1);f.sql.close();
});
test('publish, fresh lookup, revocation and complete history',async()=>{
  const f=fixture();
  assert.equal((await f.call('PUT','/v1/registry',{records:[row],base_version:0})).status,200);
  const response=await f.call('POST','/v1/check',{uid:row.uid},'station');
  assert.equal(response.headers.get('cache-control'),'no-store');
  assert.equal((await response.json()).version,1);
  assert.equal((await f.call('PUT','/v1/registry',{records:[{...row,active:0}],base_version:1})).status,200);
  assert.equal((await f.call('POST','/v1/check',{uid:row.uid},'station')).status,403);
  assert.equal((await f.call('POST','/v1/check',{uid:'0002'},'station')).status,404);
  assert.equal(f.sql.prepare('SELECT count(*) AS n FROM revisions').get().n,3);f.sql.close();
});
test('competing uploads cannot lose the winning update',async()=>{
  const f=fixture();
  const replies=await Promise.all([f.call('PUT','/v1/registry',{records:[row],base_version:0}),
    f.call('PUT','/v1/registry',{records:[{...row,name:'Other'}],base_version:0})]);
  assert.deepEqual(replies.map(r=>r.status).sort(),[200,409]);
  assert.equal(f.sql.prepare('SELECT MAX(version) AS v FROM revisions').get().v,1);f.sql.close();
});
test('malformed records, removals and stale versions leave published data intact',async()=>{
  const f=fixture();
  for(const records of [[row,row],[{...row,active:true}],[{...row,uid:'0'}],[{...row,initials:'1'}]]){
    assert.equal((await f.call('PUT','/v1/registry',{records,base_version:0})).status,400);
  }
  await f.call('PUT','/v1/registry',{records:[row],base_version:0});
  assert.equal((await f.call('PUT','/v1/registry',{records:[],base_version:1})).status,400);
  assert.equal((await f.call('PUT','/v1/registry',{records:[row],base_version:0})).status,409);
  assert.equal((await (await f.call('GET','/v1/registry')).json()).version,1);f.sql.close();
});
test('backend failures are sanitized',async()=>{
  const f=fixture();f.sql.close();
  const res=await f.call('GET','/v1/registry');assert.equal(res.status,503);
  assert.deepEqual(await res.json(),{error:'Cloud registry unavailable. Try again later.'});
});
