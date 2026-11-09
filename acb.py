"""Bounded, read-only queries over pinned SkillCorner annotations.

No arbitrary model SQL; every filter is parameterized and every result is reproducible.
"""
import json
import re
from collections import Counter
import store

FAMILIES=('picks','handoffs','off_ball_screens','drives','isolations','posts','closeouts')
COMMIT='4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66'
BASE=f'https://github.com/SkillCorner/opendata-basketball/blob/{COMMIT}/'
NOTICE='SkillCorner model-derived annotations. Ten selected ACB 2025-2026 games; action counts are not possession efficiency or causal evidence. Actions may overlap within a chance.'
SEASON_NOTICE='Offense only, 293 of 327 ACB 2025-2026 games. Rows are player-team-season; all-teams total rows are excluded. Traded players can appear for multiple teams. Pick metrics count direct picks only. Points on drives/picks exclude free throws. Rates retain publisher units; consult the data dictionary. Missing values are not zero.'

def overview():
    with store.connect() as db:
        games=[dict(r) for r in db.execute('SELECT id,home,away,date FROM acb_games ORDER BY date')]
        counts={r[0]:r[1] for r in db.execute('SELECT family,count(*) FROM acb_events GROUP BY family')}
        teams={}
        for r in db.execute('SELECT metadata FROM acb_games'):
            m=json.loads(r[0])
            for k in ('homeTeam','awayTeam'): teams[str(m[k]['teamId'])]=m[k]['teamName']
    return {'games':games,'teams':teams,'action_counts':{f:counts[f] for f in FAMILIES},
        'season_metrics':{'picks':['handler_total_picks','handler_successful_pick','handler_ppp','handler_picks_vs_switch','screener_total_picks'],
                          'drives':['total_drives','successful_drives','category_pick_count','category_handoff_count','category_off_ball_screen_count'],
                          'shots':['attempts','mades','fg_percentage','cns_attempts','zone_three_attempts']},
        'event_limits':NOTICE,'season_limits':SEASON_NOTICE,'dictionary_search':'Search data_dictionary for metric definitions and known issues before interpreting rates.'}

def selection(family,game_id,team_id,direct):
    if family not in FAMILIES: raise ValueError('Unknown action family. Use '+', '.join(FAMILIES))
    if direct not in ('all','direct','indirect'): raise ValueError('direct must be all, direct or indirect')
    if game_id!='all' and not re.fullmatch(r'\d{6}',game_id): raise ValueError('Invalid ACB game ID')
    if team_id!='all' and not re.fullmatch(r'\d+',team_id): raise ValueError('Use exact ACB team ID from catalog')
    with store.connect() as db:
        if game_id!='all' and not db.execute('SELECT 1 FROM acb_games WHERE id=?',(game_id,)).fetchone(): raise ValueError('Game outside ACB sample')
        if team_id!='all' and not db.execute('SELECT 1 FROM acb_events WHERE team_id=?',(team_id,)).fetchone(): raise ValueError('Team outside ACB sample')
    sql='family=? AND (?=\'all\' OR game_id=?) AND (?=\'all\' OR team_id=?) AND (?=\'all\' OR direct=?)'
    args=(family,game_id,game_id,team_id,team_id,direct,int(direct=='direct'))
    return sql,args

def source(sid,title,url,locator,data,notice):
    return {'source_id':sid,'title':title,'url':url,'locator':locator,'kind':'acb_data',
        'evidence_url':'/evidence/'+sid,'text':json.dumps({'data':data,'limitations':notice},ensure_ascii=False),**data,'limitations':notice}

def action_counts(family,game_id='all',team_id='all',direct='all'):
    try: sql,args=selection(family,game_id,team_id,direct)
    except ValueError as exc: return {'error':str(exc)}
    with store.connect() as db: rows=db.execute('SELECT game_id,team_id,raw_json FROM acb_events WHERE '+sql,args).fetchall()
    records=[json.loads(r['raw_json']) for r in rows]
    breakdown={field:dict(Counter(str(x[field]) for x in records if field in x)) for field in ('bhrDefType','scrDefType','receiverDefType','setterDefType','cutterDefType','locationType','category','endType')}
    data={'family':family,'game_id':game_id,'offensive_team_id':team_id,'direct_filter':direct,'event_count':len(rows),
          'by_game':dict(Counter(r['game_id'] for r in rows)),'by_offensive_team':dict(Counter(r['team_id'] for r in rows)),
          'breakdowns':{k:v for k,v in breakdown.items() if v},
          'method':'COUNT event rows after exact family/game/offTeamId/direct filters; each breakdown counts the same filtered rows, omitting absent fields. No shot outcomes are attributed to an action.'}
    sid=f'acbcount-{family.replace("_", "X")}-{game_id}-{team_id}-{direct}'
    return source(sid,f'ACB {family}: {len(rows)} annotated actions',BASE.replace('/blob/','/tree/')+'data/matches',f'family={family}; game={game_id}; offTeamId={team_id}; direct={direct}',data,NOTICE)

def action_events(family,game_id='all',team_id='all',direct='all',limit=5):
    try: sql,args=selection(family,game_id,team_id,direct)
    except ValueError as exc: return {'error':str(exc)}
    with store.connect() as db:
        ids=[r[0] for r in db.execute('SELECT event_id FROM acb_events WHERE '+sql+' ORDER BY game_id,period,event_id LIMIT ?',(*args,max(1,min(limit,8))))]
    return {'events':[event_evidence(x) for x in ids], 'warning':'Ordered examples, not a random or representative sample. '+NOTICE}

def event_evidence(event_id):
    with store.connect() as db:
        r=db.execute('SELECT * FROM acb_events WHERE event_id=?',(event_id,)).fetchone()
        if not r: return {'error':'Unknown ACB event'}
        meta=json.loads(db.execute('SELECT metadata FROM acb_games WHERE id=?',(r['game_id'],)).fetchone()[0])
    row=json.loads(r['raw_json'])
    players={str(p['playerId']):p['firstName']+' '+p['lastName'] for k in ('homeTeam','awayTeam') for p in meta[k]['players']}
    names={k:players.get(str(v),'unknown') for k,v in row.items() if k.endswith('Id') and str(v) in players}
    return source('acbevent-'+event_id,f'ACB {r["game_id"]}: {event_id}',BASE+f'data/matches/{r["game_id"]}/{r["game_id"]}_dynamic_events.json',f'{r["family"]}.id={event_id}',{'event':row,'player_names':names,'home':meta['homeTeam']['teamName'],'away':meta['awayTeam']['teamName']},NOTICE)

def season_rows(family,metrics,team='',player='',limit=5):
    if family not in ('shots','picks','drives'): return {'error':'family must be shots, picks or drives'}
    with store.connect() as db:
        rows=[(r['row_id'],json.loads(r['raw_json'])) for r in db.execute('SELECT row_id,raw_json FROM acb_season WHERE family=? AND (?=\'\' OR lower(team) LIKE ?) AND (?=\'\' OR lower(player) LIKE ?)',(family,team,'%'+team.lower()+'%',player,'%'+player.lower()+'%'))]
        example=json.loads(db.execute('SELECT raw_json FROM acb_season WHERE family=? LIMIT 1',(family,)).fetchone()[0])
    if not metrics or len(metrics)>6 or any(m not in example or m in list(example)[:8] for m in metrics):
        return {'error':'Select 1-6 metric columns, ranking descending by first metric.','available_metrics':list(example)[8:]}
    rows=[(i,r) for i,r in rows if r['team_name']!='total']
    if any(r[metrics[0]] is not None and not isinstance(r[metrics[0]],(int,float)) for _,r in rows): return {'error':'Ranking metric must be numeric'}
    rows.sort(key=lambda pair:(pair[1][metrics[0]] is not None,pair[1][metrics[0]] or 0),reverse=True)
    return {'rows':[season_evidence(family,i,metrics) for i,r in rows[:max(1,min(limit,8))]],
        'matching_rows':len(rows),'ranked_by':metrics[0], 'limitations':SEASON_NOTICE,
        'warning':'Ranking is descriptive; no minimum opportunity threshold is applied. Low-volume rates do not establish superior skill.'}

def season_evidence(family,row_id,metrics=None):
    with store.connect() as db:
        found=db.execute('SELECT raw_json FROM acb_season WHERE family=? AND row_id=?',(family,row_id)).fetchone()
    if not found: return {'error':'Unknown aggregate row'}
    row=json.loads(found[0]); selected={k:row[k] for k in [*list(row)[:9],*(metrics or list(row)[9:]) ]}
    return source(f'acbseason-{family}-{row_id}',f'ACB {family}: {row["player_name"]}, {row["team_name"]}',BASE+f'data/aggregates/acb_{family}aggregates_20252026.csv',f'CSV line {row_id} (header line 1); player_id={row["player_id"]}; team_id={row["team_id"]}',{'row':selected},SEASON_NOTICE)

def evidence(sid):
    if sid.startswith('acbevent-'): return event_evidence(sid[len('acbevent-'):])
    m=re.fullmatch(r'acbcount-([a-zX]+)-(all|\d{6})-(all|\d+)-(all|direct|indirect)',sid)
    if m: return action_counts(m[1].replace('X','_'),m[2],m[3],m[4])
    m=re.fullmatch(r'acbseason-(shots|picks|drives)-(\d+)',sid)
    if m: return season_evidence(m[1],int(m[2]))
    return {'error':'Invalid ACB evidence ID'}
