"""Reproducible same-model comparison on the expanded ACB corpus."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(os.getenv('COURTLAB_ENV',str(ROOT/'.env')))
sys.path.insert(0,str(ROOT))
from litellm import acompletion
from context_panel import AgentContexts,PanelHooks
from research import MODEL_NAME,PROJECT,RunState,deep_research
import acb

QUESTION="In SkillCorner's ten ACB 2025-2026 sample games, how many annotated picks and handoffs are there? Separately identify the player-team row with the highest handler_total_picks in the 293-game season aggregate and report its count. Explain why these populations cannot be combined. Cite the actual dataset and keep the answer concise."
async def main():
    started=time.monotonic()
    baseline=await acompletion(model=MODEL_NAME,messages=[{'role':'user','content':QUESTION}],vertex_project=PROJECT,vertex_location=os.getenv('VERTEX_LOCATION','global'),timeout=70,num_retries=2,max_tokens=6000)
    print('Baseline complete',flush=True)
    state=RunState(PanelHooks(AgentContexts(),lambda x:None))
    async with asyncio.timeout(240): answer,meta=await deep_research(QUESTION,state)
    expected={'picks':acb.action_counts('picks')['event_count'],'handoffs':acb.action_counts('handoffs')['event_count'],
              'season_leader':acb.season_rows('picks',['handler_total_picks'],limit=1)['rows'][0]['row']}
    record={'question':QUESTION,'model':MODEL_NAME,'baseline_no_system_no_tools':baseline.choices[0].message.content,'baseline_finish_reason':baseline.choices[0].finish_reason,'agent_answer':answer,'research':meta,'tool_calls':state.traces,'expected_from_data_tools':expected,'seconds':round(time.monotonic()-started,2)}
    (ROOT/'data/acb-comparison.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(json.dumps({'answer':answer,'research':meta,'expected':expected,'seconds':record['seconds']},indent=2),flush=True)
if __name__=='__main__':asyncio.run(main())
