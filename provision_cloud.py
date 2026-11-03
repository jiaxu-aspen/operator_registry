"""Provision this Windows user's registry and Workbench without printing secrets.

Run after deploying the Worker. The app tokens are generated locally and sent
to Cloudflare only as SHA-256 digests through Wrangler's secret bulk stdin.
The local configuration stores Windows DPAPI ciphertext, not plaintext tokens.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
from cloud_client import save_config, protect_token, validate_url


def main():
    """Create/reuse durable provision state, then activate clients after secret upload."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--workbench',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent;url=validate_url(args.url)
    state_path=root/'provisioning.local.json'
    if state_path.exists():
        state=json.loads(state_path.read_text())
        if state['url']!=url:raise SystemExit('Existing provisioning belongs to another endpoint; review before replacing it.')
    else:
        state={'url':url,'clients':{}}
        for name,role in [('registry-admin','admin'),('workbench-01','reader')]:
            secret=secrets.token_urlsafe(32)
            state['clients'][name]={'role':role,'hash':hashlib.sha256(secret.encode()).hexdigest(),
                'token_dpapi':protect_token(name+'.'+secret)}
        state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
    directory={name:{'hash':entry['hash'],'role':entry['role']} for name,entry in state['clients'].items()}
    # Keep credentials out of argv, shell interpolation, and captured tool logs.
    subprocess.run(['node',str(root/'cloud/node_modules/wrangler/bin/wrangler.js'),
        'secret','bulk','--config','wrangler.local.jsonc'],cwd=root/'cloud',
        input=json.dumps({'CLIENTS_JSON':json.dumps(directory)}),text=True,check=True)
    save_config(root/'registry-cloud.local.json',url,protect_token(state['clients']['registry-admin']['token_dpapi'],decrypt=True))
    save_config(args.workbench/'Operator Registry/registry-cloud.local.json',url,
        protect_token(state['clients']['workbench-01']['token_dpapi'],decrypt=True))
    print('Registry administrator and Workbench read-only credentials provisioned for this Windows user.')


if __name__=='__main__':main()
