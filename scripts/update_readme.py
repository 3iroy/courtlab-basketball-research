"""Append reproducible actual comparison outputs; never fabricate baseline answers."""
import json,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'README.md'
s=p.read_text().split('\n<!-- COMPARISONS -->')[0]
rows=json.loads((ROOT/'data/comparisons.json').read_text())
checks=[
 'Expected: GSW G4 FG 40/91, 3PT 15/43, 16 turnovers from events/game_id=0042100404. Tactical interpretation requires gsw-g4 passages, not PBP alone.',
 'Expected: Heat–Knicks case evidence about top-blocking, backdoor cuts, Love shooting and Adebayo fake-handoff options in mia-nyk passages. No season-wide frequency claim.',
 'Expected: a clearly labeled proposal matched to the supplied adult amateur roster and weekly practice constraint, grounded in WABC/NBA passages. No invented success rate.'
]
s+='\n<!-- COMPARISONS -->\n## Three sample queries: expected checks and actual comparisons\n'
for i,r in enumerate(rows):
 s+=f'\n### Sample {i+1}\n\n{r["question"]}\n\n{checks[i]}\n\n'
 s+=f'Model: `{r["model"]}`. Actual elapsed time including baseline: {r["seconds"]} seconds.\n\n'
 s+='<details><summary>Actual outputs — same model, side by side</summary>\n\n<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr>'
 s+='<td>'+html.escape(r['baseline_no_system_no_tools']).replace('\n','<br>')+'</td>'
 s+='<td>'+html.escape(r['agent_answer']).replace('\n','<br>')+'</td></tr></table>\n\n</details>\n'
 s+='\nFull tool trace: `data/comparisons.json`, sample '+str(i+1)+'.\n'
p.write_text(s)
