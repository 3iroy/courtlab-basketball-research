"""Add pinned SkillCorner annotations/aggregates and full WABC manuals atomically.

Run after build_data.py. Raw tracking frames are deliberately not ingested.
"""
import csv
import hashlib
import io
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import ROOT, DATA, download, chunks, MANUAL
from pypdf import PdfReader

COMMIT = '4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66'
BASE = f'https://raw.githubusercontent.com/SkillCorner/opendata-basketball/{COMMIT}/'
ACTIONS = ('picks', 'handoffs', 'off_ball_screens', 'drives', 'isolations', 'posts', 'closeouts')
MANUALS = {
 1: 'https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-level-manuals-level-1-eng.pdf',
 2: MANUAL,
 3: 'https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-3-eng.pdf',
}

def build():
    target = DATA/'courtlab.sqlite'
    temp = DATA/'courtlab-expanded.sqlite'
    shutil.copy2(target, temp)
    db = sqlite3.connect(temp)
    manifest = json.loads((DATA/'manifest.json').read_text())
    now = datetime.now(timezone.utc).isoformat()
    manifest['sources'] = [s for s in manifest['sources'] if not s['id'].startswith(('wabc-', 'acb-'))]
    ids = [r[0] for r in db.execute("SELECT id FROM documents WHERE id LIKE 'wabc-%' OR id LIKE 'acb-%'")]
    for doc in ids:
        db.execute('DELETE FROM passage_fts WHERE id IN (SELECT id FROM passages WHERE document_id=?)', (doc,))
        db.execute('DELETE FROM passages WHERE document_id=?', (doc,))
        db.execute('DELETE FROM documents WHERE id=?', (doc,))
    db.executescript('''DROP TABLE IF EXISTS acb_games; DROP TABLE IF EXISTS acb_events; DROP TABLE IF EXISTS acb_season;
    CREATE TABLE acb_games(id TEXT PRIMARY KEY,home TEXT,away TEXT,date TEXT,metadata TEXT);
    CREATE TABLE acb_events(game_id TEXT,family TEXT,event_id TEXT PRIMARY KEY,period INTEGER,team_id TEXT,direct INTEGER,raw_json TEXT);
    CREATE INDEX acb_filter ON acb_events(family,game_id,team_id,direct);
    CREATE TABLE acb_season(family TEXT,row_id INTEGER,player TEXT,team TEXT,raw_json TEXT,PRIMARY KEY(family,row_id));
    ''')
    def document(id, title, url, kind, raw, season=''):
        sha = hashlib.sha256(raw).hexdigest()
        db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)', (id,title,url,kind,'',season,'',sha,now))
        manifest['sources'].append(dict(id=id,title=title,url=url,sha256=sha,retrieved_at=now))
    def passage(id, doc, loc, text):
        db.execute('INSERT INTO passages VALUES(?,?,?,?)', (id,doc,loc,text))
        db.execute('INSERT INTO passage_fts VALUES(?,?)', (id,text))
    def sc(path):
        return download(BASE+path, 'skillcorner/'+path)
    # download() needs each nested cache directory to exist.
    from build_data import CACHE
    for folder in ['docs/data_dictionary', 'data/aggregates', 'data/matches']:
        (CACHE/'skillcorner'/folder).mkdir(parents=True, exist_ok=True)
    matches = json.loads(sc('data/matches.json'))
    game_ids = [str(g['gameId'] if 'gameId' in g else g['id']) for g in matches]
    for gid in game_ids:
        (CACHE/'skillcorner/data/matches'/gid).mkdir(parents=True, exist_ok=True)
        path = f'data/matches/{gid}/{gid}_game_data.json'
        raw = sc(path); meta = json.loads(raw)
        db.execute('INSERT INTO acb_games VALUES(?,?,?,?,?)', (gid,meta['homeTeam']['teamName'],meta['awayTeam']['teamName'],meta['date'],json.dumps(meta)))
        path = f'data/matches/{gid}/{gid}_dynamic_events.json'
        raw = sc(path); bundle = json.loads(raw)
        document('acb-game-'+gid, f'ACB {gid}: {meta["homeTeam"]["teamName"]} vs {meta["awayTeam"]["teamName"]}', BASE+path, 'acb_events', raw, '2025-2026')
        for family in (*ACTIONS, 'shots', 'chances', 'possessions'):
            for row in bundle[family]:
                db.execute('INSERT INTO acb_events VALUES(?,?,?,?,?,?,?)',(gid,family,row['id'],row['period'],str(row['offTeamId']),int(row['direct']) if 'direct' in row else None,json.dumps(row)))
    for family in ('shots','drives','picks'):
        path=f'data/aggregates/acb_{family}aggregates_20252026.csv'
        raw=sc(path)
        document('acb-season-'+family, f'ACB 2025-2026 {family}: 293-game offensive aggregates',BASE+path,'acb_aggregates',raw,'2025-2026')
        for i,row in enumerate(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))),start=2):
            typed={k: (None if v=='' else v) for k,v in row.items()}
            for key in list(typed)[8:]:
                if typed[key] is not None:
                    try: typed[key]=float(typed[key])
                    except ValueError: pass
            db.execute('INSERT INTO acb_season VALUES(?,?,?,?,?)',(family,i,row['player_name'],row['team_name'],json.dumps(typed)))
    docs=['README.md','docs/PRIMER.md','docs/KNOWN_ISSUES.md','docs/aggregates_columns.md','docs/data_dictionary/README.md'] + [f'docs/data_dictionary/{x}.md' for x in (*ACTIONS,'shots','chances','possessions')]
    for path in docs:
        raw=sc(path); doc='acb-doc-'+path.replace('/','-').replace('.md','')
        document(doc, 'SkillCorner: '+path, BASE+path, 'data_dictionary',raw,'2025-2026')
        for i,part in enumerate(chunks(raw.decode())): passage(f'{doc}-{i+1}',doc,f'document passage {i+1}',part)
    raw=sc('LICENSE'); (DATA/'SKILLCORNER-LICENSE.txt').write_bytes(raw)
    manual_pages={}
    for level,url in MANUALS.items():
        raw=download(url,f'wabc-level{level}.pdf');doc=f'wabc-l{level}'
        document(doc,f'WABC Level {level} Coaches Manual',url,'coaching_manual',raw)
        reader=PdfReader(io.BytesIO(raw)); count=0
        for i,page in enumerate(reader.pages):
            text=page.extract_text() or ''
            if len(text.strip())<100: continue
            count+=1
            for j,part in enumerate(chunks(text)): passage(f'{doc}-p{i+1}-{j+1}',doc,f'PDF page {i+1}',part)
        manual_pages[str(level)]={'pdf_pages':len(reader.pages),'indexed_pages':count}
        print('WABC',level,manual_pages[str(level)],flush=True)
    manifest.update(retrieved_at=now,skillcorner_commit=COMMIT,wabc_manuals=manual_pages,
        acb_game_count=db.execute('SELECT count(*) FROM acb_games').fetchone()[0],
        acb_event_count=db.execute('SELECT count(*) FROM acb_events').fetchone()[0],
        acb_action_count=db.execute('SELECT count(*) FROM acb_events WHERE family NOT IN (\'shots\',\'chances\',\'possessions\')').fetchone()[0],
        acb_aggregate_rows=db.execute('SELECT count(*) FROM acb_season').fetchone()[0],acb_aggregate_game_count=293,
        passage_count=db.execute('SELECT count(*) FROM passages').fetchone()[0])
    manifest.pop('indexed_manual_pages',None);manifest.pop('manual_pdf_pages',None)
    manifest['limitations']=['ACB annotations are model-derived actions, not complete named team playbooks. Raw tracking frames are not shipped or analyzed.',
        'Detailed ACB events cover 10 selected games. Offensive season aggregates cover 293 of 327 games and cannot be reproduced from those 10 files.',
        'Pick aggregates count direct picks only; traded-player total rows must not be combined with team rows.',
        'NBA PBP lacks full tactical labels. Film studies are selected cases. Amateur adaptations are proposals, not tested effectiveness claims.']
    db.commit();db.execute('VACUUM');db.close();temp.replace(target)
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print({k:v for k,v in manifest.items() if k.endswith(('count','rows'))},flush=True)
if __name__=='__main__': build()
