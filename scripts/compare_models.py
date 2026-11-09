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
 '在 2022 年总决赛 G4（game_id=0042100404），勇士全场投篮、三分球和失误分别是多少？结合官方 G4 解析，解释一个可核实的进攻调整，注明比赛事件不能证明的内容。',
 '根据 2023 年热火对尼克斯的官方比赛解析，尼克斯 top-block 射手时，热火有哪些反跑和假手递手应对？用资料中的具体案例解释，不推断赛季使用频率。',
 '我们是成年业余五人制球队，每周训练一次 60 分钟，没有高大中锋，有两个稳定空位投手和一个能传球的内线，主要面对人盯人。结合勇士和热火资料，提出一个可以先练的简化配合，明确标为改编建议，给执行步骤、失败条件和来源。'
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
    vertex_project=PROJECT,vertex_location=os.getenv('VERTEX_LOCATION','global'),timeout=70,num_retries=0,max_tokens=3000)
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
