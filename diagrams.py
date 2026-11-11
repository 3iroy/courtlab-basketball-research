"""Static concept diagrams: bounded drawing data, never model-authored SVG or measured tracking."""
import json
import re
from typing import Literal
from pydantic import BaseModel, Field

PlayerID=Literal['O1','O2','O3','O4','O5','X1','X2','X3','X4','X5']
class Player(BaseModel):
    id: PlayerID
    x: float=Field(ge=5,le=95,allow_inf_nan=False)
    y: float=Field(ge=5,le=95,allow_inf_nan=False)
class Motion(BaseModel):
    start: PlayerID
    end_x: float=Field(ge=5,le=95,allow_inf_nan=False)
    end_y: float=Field(ge=5,le=95,allow_inf_nan=False)
    kind: Literal['pass','cut','screen']
    label: str=Field(max_length=60)
class Diagram(BaseModel):
    claim_index: int=Field(ge=0,le=15)
    title: str=Field(max_length=80)
    caption: str=Field(max_length=220)
    players: list[Player]=Field(min_length=2,max_length=10)
    motions: list[Motion]=Field(max_length=5)

def is_short_diagram_request(question: str) -> bool:
    """Recognize direct follow-ups that the planner could mistake for a source lookup."""
    try:
        context = json.loads(question)
    except json.JSONDecodeError:
        context = None
    latest = context.get('latest_question', question) if isinstance(context, dict) else question
    if not isinstance(latest, str):
        return False
    latest = latest.strip().rstrip('？?。！!').strip()
    chinese = (
        r'(?:请)?(?:有(?:没有)?|能(?:给我|画|显示)?|可以(?:给我|画|显示)?|给我|画|显示|来|发)?'
        r'(?:一张|个)?(?:静态)?(?:战术图|跑位图|半场示意图|示意图)(?:吗|么|呢)?'
    )
    english = r'(?:(?:can|could) you )?(?:show(?: me)?|draw|add|include) (?:a |the )?(?:static |tactical |half-court )*diagram'
    return bool(re.fullmatch(chinese, latest) or re.fullmatch(english, latest, re.IGNORECASE))


def prepare(diagram,claims,accepted,evidence):
    if diagram is None: return None,'No diagram proposed.'
    if diagram.claim_index>=len(claims):return None,'Unknown claim index.'
    claim=claims[diagram.claim_index]
    if not any(c is claim for c in accepted):return None,'The linked claim did not survive evidence checks.'
    if claim.kind=='limitation' or not claim.source_ids:return None,'No supported tactical claim.'
    ids=[p.id for p in diagram.players]
    if len(set(ids))!=len(ids):return None,'Duplicate player IDs.'
    if any(m.start not in ids for m in diagram.motions):return None,'An arrow starts at an absent player.'
    # Visually indistinguishable nodes are omitted instead of publishing an unreadable image.
    for i,p in enumerate(diagram.players):
        for q in diagram.players[i+1:]:
            if (p.x-q.x)**2+(p.y-q.y)**2<49:return None,'Player markers overlap.'
    if any(s not in evidence for s in claim.source_ids):return None,'Unknown diagram citation.'
    data=diagram.model_dump()
    data.update(kind='proposed_adaptation' if claim.kind=='adaptation' else 'concept_illustration',
                source_ids=claim.source_ids,
                disclaimer='Illustrative positions and arrows; not measured tracking or a reproduction of an exact game possession.')
    return data,''
