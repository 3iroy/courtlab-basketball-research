"""Real same-model comparisons: no system prompt/tools baseline vs CourtLab, with traces."""
import asyncio,json,os,sys,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from litellm import acompletion
from context_panel import AgentContexts,PanelHooks
from research import MODEL_NAME,PROJECT,RunState,deep_research
ROOT=Path(__file__).resolve().parents[1]
QUERIES=[
 'In Game 4 of the 2022 NBA Finals (game_id=0042100404), what were the Warriors’ field goals, three-pointers and turnovers? Use the official G4 film study to explain one supported late-game defensive sequence. Explain what play-by-play cannot establish.',
 'According to the official 2023 Heat–Knicks film study, how did Miami counter top-blocking with backdoor cuts and fake handoffs? Explain specific sourced cases without inferring season-wide frequency.',
 'We are an adult amateur five-on-five team with one 60-minute practice per week, no tall center, two reliable open shooters and one passing big. We mostly face man-to-man defense. Use Warriors and Heat evidence to propose one simplified action, with execution steps, failure conditions and citations. Clearly label it as a proposed adaptation.'
]
async def main():
 args=argparse.ArgumentParser()
 args.add_argument('--sample',type=int,choices=[1,2,3])
 selected=args.parse_args().sample
 existing=ROOT/'data/comparisons.json'
 out=json.loads(existing.read_text()) if selected and existing.exists() else []
 for i,q in enumerate(QUERIES):
  if selected and i+1!=selected: continue
  start=time.monotonic()
  base=await acompletion(model=MODEL_NAME,messages=[{'role':'user','content':q}],
    vertex_project=PROJECT,vertex_location=os.getenv('VERTEX_LOCATION','global'),timeout=70,num_retries=2,max_tokens=3000)
  print('BASELINE',i+1,flush=True)
  state=RunState(PanelHooks(AgentContexts(),lambda x:None))
  async with asyncio.timeout(240):answer,meta=await deep_research(q,state)
  record={'question':q,'model':MODEL_NAME,'baseline_no_system_no_tools':base.choices[0].message.content,
          'agent_answer':answer,'research':meta,'tool_calls':state.traces,'seconds':round(time.monotonic()-start,2)}
  out=[row for row in out if row['question']!=q]
  out.append(record)
  out.sort(key=lambda row:QUERIES.index(row['question']))
  (ROOT/'data/comparisons.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
  print('AGENT',i+1,meta,'seconds',record['seconds'],flush=True)
 print('DONE',flush=True)
if __name__=='__main__':asyncio.run(main())
