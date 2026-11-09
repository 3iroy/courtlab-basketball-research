"""Provision only CourtLab's dedicated resources; preserve existing services/triggers."""
import json,time
from cloud_admin import request,PROJECT,REGION
from pathlib import Path
p=PROJECT; region=REGION
sa=f'courtlab@{p}.iam.gserviceaccount.com'
# Dedicated runtime identity; existing Project 1 identity is never changed.
try:request('GET',f'https://iam.googleapis.com/v1/projects/{p}/serviceAccounts/{sa}')
except RuntimeError as e:
 if '404:' not in str(e):raise
 request('POST',f'https://iam.googleapis.com/v1/projects/{p}/serviceAccounts',{'accountId':'courtlab','serviceAccount':{'displayName':'CourtLab runtime'}})
policy=request('POST',f'https://cloudresourcemanager.googleapis.com/v1/projects/{p}:getIamPolicy',{})
member='serviceAccount:'+sa
if not any(x['role']=='roles/aiplatform.user' and member in x['members'] for x in policy.get('bindings',[])):
 policy.setdefault('bindings',[]).append({'role':'roles/aiplatform.user','members':[member]})
 request('POST',f'https://cloudresourcemanager.googleapis.com/v1/projects/{p}:setIamPolicy',{'policy':policy})
print('Runtime identity ready',flush=True)
# Permit only the existing build identity to deploy as the new runtime identity.
url=f'https://iam.googleapis.com/v1/projects/{p}/serviceAccounts/{sa}'
policy=request('POST',url+':getIamPolicy',{})
compute='serviceAccount:176221542819-compute@developer.gserviceaccount.com'
if not any(x['role']=='roles/iam.serviceAccountUser' and compute in x['members'] for x in policy.get('bindings',[])):
 policy.setdefault('bindings',[]).append({'role':'roles/iam.serviceAccountUser','members':[compute]})
 request('POST',url+':setIamPolicy',{'policy':policy})
registry=f'https://artifactregistry.googleapis.com/v1/projects/{p}/locations/{region}/repositories/courtlab'
try:request('GET',registry)
except RuntimeError as e:
 if '404:' not in str(e):raise
 print('Registry:',request('POST',registry.rsplit('/',1)[0]+'?repositoryId=courtlab',{'format':'DOCKER','description':'CourtLab course project images'}).get('name'),flush=True)
connection=f'projects/{p}/locations/{region}/connections/nba-fantasy-github'
link=connection+'/gitRepositoryLinks/3iroy-courtlab-basketball-research'
base='https://developerconnect.googleapis.com/v1/'
try:result=request('GET',base+link)
except RuntimeError as e:
 if '404:' not in str(e):raise
 result=request('POST',base+connection+'/gitRepositoryLinks?gitRepositoryLinkId=3iroy-courtlab-basketball-research',{'cloneUri':'https://github.com/3iroy/courtlab-basketball-research.git'})
print('GitHub link operation:',json.dumps(result),flush=True)
if not result.get('done') and '/operations/' in result.get('name',''):
 operation=result['name']
 for _ in range(12):
  result=request('GET',base+operation)
  if result.get('done'):break
  time.sleep(3)
 if not result.get('done'):raise RuntimeError('Repository link is still provisioning; rerun after it completes.')
if result.get('error'):raise RuntimeError(json.dumps(result['error']))
print('GitHub link ready',flush=True)
trigger={'name':'courtlab-main','filename':'cloudbuild.yaml',
 'serviceAccount':f'projects/{p}/serviceAccounts/176221542819-compute@developer.gserviceaccount.com',
 'developerConnectEventConfig':{'gitRepositoryLink':link,'gitRepositoryLinkType':'GITHUB','push':{'branch':'^main$'}}}
triggers=f'https://cloudbuild.googleapis.com/v1/projects/{p}/locations/{region}/triggers'
existing=request('GET',triggers).get('triggers',[])
created=next((t for t in existing if t['name']=='courtlab-main'),None)
if not created:created=request('POST',triggers,trigger)
result={'project':p,'region':region,'repository':'https://github.com/3iroy/courtlab-basketball-research','trigger_id':created['id'],'git_repository_link':link,'service':'courtlab','runtime_service_account':sa}
(Path(__file__).resolve().parents[1]/'data/deployment.json').write_text(json.dumps(result,indent=2))
print('TRIGGER',created['id'],flush=True)
