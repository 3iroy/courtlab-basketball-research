"""Apply the final evidence policy to saved real comparison outputs, preserving prior text."""
import asyncio,json,re,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
import research,store
from context_panel import PanelHooks,AgentContexts
async def audit_one(row):
 start=time.monotonic();answer=row['agent_answer'];title=answer.splitlines()[0].removeprefix('# ')
 claims=[];limits=[]
 for section in re.split(r'\n## ',answer)[1:]:
  heading,_,body=section.partition('\n')
  if heading.startswith('Sources'):continue
  if heading.startswith('Limitations'):
   limits=[x[2:] for x in body.splitlines() if x.startswith('- ')];continue
  kind='adaptation' if '**Proposed adaptation' in body else 'limitation' if '**Evidence limit' in body else 'observation'
  ids=list(dict.fromkeys(re.findall(r'\[\d+\]\(/evidence/([A-Za-z0-9-]+)\)',body)))
  text=re.sub(r'\[\d+\]\(/evidence/[A-Za-z0-9-]+\)','',body)
  text=re.sub(r'\*\*(?:Evidence|Proposed adaptation|Evidence limit)\*\*','',text).strip()
  claims.append(research.Claim(heading=heading,text=text,kind=kind,source_ids=ids))
 known={c['source_id'] for c in row['research']['citations']}
 ev={sid:store.evidence(sid) for sid in known}
 state=research.RunState(PanelHooks(AgentContexts(),lambda x:None));state.evidence=ev
 footer_start=len(claims)
 claims += [research.Claim(heading='Report limitation',text=x,kind='limitation',source_ids=[]) for x in limits]
 payload={'question':row['question'],'scope':store.catalog()['scope'],'catalog':store.catalog(),'claims':[
  {'index':i,**c.model_dump(),'evidence':{sid:ev[sid] for sid in c.source_ids if sid in ev}} for i,c in enumerate(claims)]}
 result=await research.audit_claims(payload,state)
 verdicts={v.claim_index:v for v in result.verdicts};accepted=[];accepted_limits=[];rejected=[]
 for i,c in enumerate(claims):
  v=verdicts.get(i)
  if v and v.supported and all(sid in known for sid in c.source_ids):
   if i>=footer_start:accepted_limits.append(c.text)
   else:accepted.append(c)
  else:rejected.append(v.reason if v else 'Missing audit verdict')
 state.trace('Evidence audit','check_citations',{}, {'final_comparison_audit':True,'accepted':len(accepted),'withheld':rejected})
 text,citations=research.render_report(title,accepted,accepted_limits,rejected,ev)
 row['pre_final_audit_answer']=answer;row['agent_answer']=text
 row['final_audit']=result.model_dump();row['tool_calls']+=state.traces
 row['research']['citations']=citations
 row['research']['withheld_claims']+=len(rejected)
 row['research']['status']='complete' if accepted else 'insufficient_evidence'
 row['seconds']=round(row['seconds']+time.monotonic()-start,2)
 print('FINAL AUDIT',len(accepted),'claims;',len(rejected),'withheld',flush=True)
 return row
async def main():
 p=ROOT/'data/comparisons.json';rows=json.loads(p.read_text())
 result=await asyncio.gather(*(audit_one(row) for row in rows))
 p.write_text(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())
