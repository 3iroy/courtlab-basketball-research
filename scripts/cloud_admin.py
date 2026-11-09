"""Small Cloud API helper. ADC tokens stay in memory; no credentials are written to the repo."""
import json,sys,time
from pathlib import Path
import google.auth
from google.auth.transport.requests import AuthorizedSession
PROJECT='ieor-4570-f26-ts3733';REGION='us-east1'
session=AuthorizedSession(google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])[0])
def request(method,url,body=None):
 r=session.request(method,url,json=body,timeout=60)
 if not r.ok:raise RuntimeError(f'{r.status_code}: {r.text[:1500]}')
 return r.json() if r.content else {}
def main():
 if len(sys.argv)<3:raise SystemExit('cloud_admin.py METHOD URL [body.json]')
 body=json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv)>3 else None
 print(json.dumps(request(sys.argv[1],sys.argv[2],body),indent=2))
if __name__=='__main__':main()
