"""Read-only, parameterized access to the shipped evidence database."""
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
DB = ROOT / 'data/courtlab.sqlite'
ALIASES = {'勇士': 'warriors golden state screening cutting', '热火': 'heat miami zone handoff',
           '联防': 'zone defence', '掩护': 'screen', '传切': 'cut passing', '手递手': 'handoff',
           '反跑': 'backdoor', '换防': 'switch', '业余': 'coach teaching practice'}

def connect():
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def catalog():
    with connect() as conn:
        docs = [dict(r) for r in conn.execute('SELECT id,title,url,kind,team,season,game_id FROM documents')]
        games = [dict(r) for r in conn.execute('SELECT * FROM games ORDER BY id')]
    import acb
    return {'documents': docs, 'games': games, 'acb': acb.overview(),
            'scope': 'WABC Levels 1-3 full text; 10 ACB 2025-2026 annotated games; 293-game ACB offensive aggregates; GSW 2021-22 and MIA 2022-23 playoff cases.',
            'limits': 'ACB annotations are model-derived actions, not full team playbooks. No raw tracking analysis or tested amateur effectiveness.'}

def search(query: str, team: str = '', limit: int = 6, kind: str = ''):
    with connect() as conn:
        known = conn.execute('SELECT id FROM documents WHERE id=?',(query.strip(),)).fetchone()
        if known:
            rows=conn.execute('SELECT p.id,p.locator,d.title,d.kind,d.team,d.season,substr(p.text,1,200) AS preview FROM passages p JOIN documents d ON d.id=p.document_id WHERE d.id=? ORDER BY p.rowid LIMIT ?', (query.strip(),limit)).fetchall()
            return {'results':[dict(r) for r in rows]}
    expanded = query.lower()
    for key, value in ALIASES.items():
        if key in expanded: expanded += ' ' + value
    stopwords = {'the','and','for','with','without','how','can','does','what','our','that','this','have','has','are','from','into','against','team','teams','use','using'}
    words = [w for w in dict.fromkeys(re.findall(r'[a-zA-Z]{3,}', expanded)) if w not in stopwords][:14]
    # Manuals use British spelling. Keep both variants for real text retrieval.
    for american,british in [('offense','offence'),('defense','defence')]:
        if american in words and british not in words: words.append(british)
    if not words:
        return {'error': 'Use English basketball keywords, e.g. zone, handoff, screen, cut.'}
    match = ' OR '.join('"' + w + '"' for w in words)
    # Zone-attack searches must retrieve zone-attack material, not generic shooting pages.
    if 'zone' in words and set(words) & {'attack','attacking','beat','beating','offense','offence','offensive'}:
        match = '"zone" AND ("offence" OR "offense" OR "offensive" OR "attack" OR "attacking") AND ('+match+')'
    with connect() as conn:
        rows = conn.execute('''SELECT p.id,p.locator,d.title,d.team,d.season,d.kind,
            snippet(passage_fts,1,'','', ' … ',32) AS preview
            FROM passage_fts JOIN passages p ON p.id=passage_fts.id
            JOIN documents d ON d.id=p.document_id
            WHERE passage_fts MATCH ? AND (?='' OR d.team=? OR d.team='') AND (?='' OR d.kind=?)
            ORDER BY bm25(passage_fts) LIMIT ?''', (match,team,team,kind,kind,max(1,min(limit,8)))).fetchall()
    return {'results': [dict(r) for r in rows], 'next_step': 'Read passage IDs before making claims.'}

def read_passage(id: str):
    with connect() as conn:
        r = conn.execute('''SELECT p.*,d.title,d.url,d.kind,d.team,d.season,d.game_id
            FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=?''',(id,)).fetchone()
    if r is None: return {'error':'Unknown passage ID.'}
    out = dict(r)
    out['source_id'] = out.pop('id')
    if out['kind']=='coaching_manual':
        page = re.search(r'PDF page (\d+)',out['locator']).group(1)
        out['url'] += '#page='+page
    out['evidence_url']='/evidence/'+quote(out['source_id'],safe='')
    return out

def game_events(game_id: str, period: int = 0, keyword: str = '', limit: int = 30):
    if period < 0 or period > 10: return {'error':'period must be 0 (all) or 1–10.'}
    with connect() as conn:
        game=conn.execute('SELECT * FROM games WHERE id=?',(game_id,)).fetchone()
        if not game: return {'error':'Game outside the shipped corpus. Use list_catalog.'}
        rows=conn.execute('''SELECT game_id,event_id,period,clock,team,player,event_type,description,score
            FROM events WHERE game_id=? AND (?=0 OR period=?) AND description LIKE ?
            ORDER BY period,event_id LIMIT ?''',(game_id,period,period,'%'+keyword+'%',max(1,min(limit,40)))).fetchall()
    return {'game':dict(game),'events':[dict(r) for r in rows],
            'limit':max(1,min(limit,40)), 'warning':'Truncated event search, not all possessions. Events do not identify full tactical actions.'}

def event_evidence(game_id: str, event_id: int):
    with connect() as conn:
        row=conn.execute('SELECT * FROM events WHERE game_id=? AND event_id=?',(game_id,event_id)).fetchone()
    if not row: return {'error':'Unknown game/event.'}
    out=dict(row); out.pop('raw_json')
    out.update(source_id=f'event-{game_id}-{event_id}', title=f'{game_id}, Q{out["period"]} {out["clock"]}, event {event_id}',
               locator=f'game_id={game_id}, event_id={event_id}',kind='play_by_play',
               url=f'https://www.nba.com/game/{game_id}/play-by-play', text=out['description'])
    out['evidence_url']='/evidence/'+out['source_id']
    return out

def game_summary(game_id: str, team: str, period: int = 0):
    with connect() as conn:
        game=conn.execute('SELECT * FROM games WHERE id=?',(game_id,)).fetchone()
        if not game: return {'error':'Game outside corpus.'}
        rows=conn.execute('SELECT * FROM events WHERE game_id=? AND team=? AND (?=0 OR period=?)',
                          (game_id,team,period,period)).fetchall()
    if team not in {game['team'],game['opponent']} or not 0<=period<=10:
        return {'error':'Invalid team or period for this game.'}
    shots=[r for r in rows if r['event_type'] in (1,2)]
    threes=[r for r in shots if re.search(r'\b3PT\b',r['description'])]
    makes=sum(r['event_type']==1 for r in shots)
    threem=sum(r['event_type']==1 for r in threes)
    turnovers=sum(r['event_type']==5 for r in rows)
    sid=f'summary-{game_id}-{team}-{period}'
    result={'game_id':game_id,'team':team,'period':period,'field_goals':{'made':makes,'attempted':len(shots)},
            'three_pointers':{'made':threem,'attempted':len(threes)},'turnovers':turnovers,
            'method':'EVENTMSGTYPE 1/2 = made/missed field goals; 5 = turnovers; 3PT text flags three-point attempts. Filter game_id, primary team, optional period. Not a possession or tactical-efficiency calculation.',
            'source_id':sid,'title':f'{team} game {game_id}, period {period or "all"}: event summary',
            'url':f'https://www.nba.com/game/{game_id}/play-by-play','locator':f'game_id={game_id}, team={team}, period={period}',
            'evidence_url':'/evidence/'+sid,'kind':'computed_summary'}
    result['text']=json.dumps({k:v for k,v in result.items() if k not in ('text','evidence_url')},ensure_ascii=False)
    return result

def evidence(id: str):
    if id.startswith(('acbevent-', 'acbcount-', 'acbseason-')):
        import acb
        return acb.evidence(id)
    if id.startswith('event-'):
        match=re.fullmatch(r'event-(\d{10})-(\d+)',id)
        return event_evidence(match[1],int(match[2])) if match else {'error':'Invalid event ID.'}
    if id.startswith('summary-'):
        match=re.fullmatch(r'summary-(\d{10})-([A-Z]{3})-(\d+)',id)
        return game_summary(match[1],match[2],int(match[3])) if match else {'error':'Invalid summary ID.'}
    return read_passage(id)
