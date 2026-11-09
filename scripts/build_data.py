"""Rebuild the pinned basketball corpus from public primary sources and PBP archives."""
import csv, hashlib, io, json, re, sqlite3, tarfile, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
CACHE = ROOT / '.downloads'
ARCHIVE_ROOT = 'https://raw.githubusercontent.com/shufinskiy/nba_data/main/'
FILMS = [
 ('gsw-g1', 'GSW', '2021-22', '0042100401', 'https://www.nba.com/news/2022-nba-finals-film-study-game-1'),
 ('gsw-g2', 'GSW', '2021-22', '0042100402', 'https://www.nba.com/news/finals-film-study-warriors-defense-steps-up-in-game-2'),
 ('gsw-g4', 'GSW', '2021-22', '0042100404', 'https://www.nba.com/news/2022-finals-film-study-game-4'),
 ('gsw-g5', 'GSW', '2021-22', '0042100405', 'https://www.nba.com/news/finals-film-study-game-5'),
 ('mia-nyk', 'MIA', '2022-23', '0042200202', 'https://www.nba.com/news/knicks-heat-game-3-offensive-contrast'),
 ('mia-g2', 'MIA', '2022-23', '0042200402', 'https://www.nba.com/news/finals-film-study-nuggets-heat-game-2'),
 ('mia-g4', 'MIA', '2022-23', '0042200404', 'https://www.nba.com/news/finals-film-study-nuggets-defense-puts-them-one-win-away-from-a-championship'),
]
MANUAL = 'https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf'

def download(url, name):
 CACHE.mkdir(exist_ok=True)
 p = CACHE / name
 if not p.exists():
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CourtLab educational research'}),timeout=90) as r:
   p.write_bytes(r.read())
 return p.read_bytes()

def chunks(text, size=1800):
 paragraphs = text.split('\n')
 result, current = [], ''
 for p in paragraphs:
  p = p.strip()
  if not p: continue
  if len(current)+len(p)>size and current:
   result.append(current); current=''
  # Bound long extracted paragraphs as well.
  for start in range(0,len(p),size):
   bit=p[start:start+size]
   if len(current)+len(bit)>size and current: result.append(current); current=''
   current += ('\n' if current else '')+bit
 if current: result.append(current)
 return result

def build():
 DATA.mkdir(exist_ok=True)
 target=DATA/'courtlab.sqlite'
 temp=DATA/'courtlab-building.sqlite'
 if temp.exists(): temp.unlink()
 db = sqlite3.connect(temp)
 db.executescript('''DROP TABLE IF EXISTS documents; DROP TABLE IF EXISTS passages; DROP TABLE IF EXISTS events; DROP TABLE IF EXISTS games; DROP TABLE IF EXISTS passage_fts;
 CREATE TABLE documents(id TEXT PRIMARY KEY,title TEXT,url TEXT,kind TEXT,team TEXT,season TEXT,game_id TEXT,sha256 TEXT,retrieved_at TEXT);
 CREATE TABLE passages(id TEXT PRIMARY KEY,document_id TEXT,locator TEXT,text TEXT);
 CREATE VIRTUAL TABLE passage_fts USING fts5(id UNINDEXED,text);
 CREATE TABLE events(game_id TEXT,event_id INTEGER,period INTEGER,clock TEXT,team TEXT,player TEXT,event_type INTEGER,description TEXT,score TEXT,raw_json TEXT,PRIMARY KEY(game_id,event_id));
 CREATE TABLE games(id TEXT PRIMARY KEY,team TEXT,season TEXT,opponent TEXT,event_count INTEGER);
 ''')
 now=datetime.now(timezone.utc).isoformat()
 manifest={'retrieved_at':now,'sources':[],'errors':[]}
 def document(id,title,url,kind,team,season,game,raw):
  digest=hashlib.sha256(raw).hexdigest()
  db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)',(id,title,url,kind,team,season,game,digest,now))
  manifest['sources'].append({'id':id,'title':title,'url':url,'sha256':digest})
 def passage(id,doc,loc,text):
  db.execute('INSERT INTO passages VALUES(?,?,?,?)',(id,doc,loc,text))
  db.execute('INSERT INTO passage_fts VALUES(?,?)',(id,text))
 for yr,team,season in [(2021,'GSW','2021-22'),(2022,'MIA','2022-23')]:
  filename=f'nbastats_po_{yr}.tar.xz'; url=ARCHIVE_ROOT+'datasets/'+filename
  raw=download(url,filename)
  archive=tarfile.open(fileobj=io.BytesIO(raw),mode='r:xz')
  member=next(m for m in archive.getmembers() if m.isfile() and m.name.endswith('.csv'))
  rows=list(csv.DictReader(io.TextIOWrapper(archive.extractfile(member),encoding='utf-8-sig')))
  game_ids={r['GAME_ID'].zfill(10) for r in rows if r['PLAYER1_TEAM_ABBREVIATION']==team}
  document('pbp-'+team,f'{team} {season} playoff play-by-play',url,'play_by_play',team,season,'',raw)
  for gid in sorted(game_ids):
   selected=[r for r in rows if r['GAME_ID'].zfill(10)==gid]
   opponents={r['PLAYER1_TEAM_ABBREVIATION'] for r in selected}-{team,''}
   db.execute('INSERT INTO games VALUES(?,?,?,?,?)',(gid,team,season,','.join(sorted(opponents)),len(selected)))
   for r in selected:
    desc=' | '.join(r[k] for k in ['HOMEDESCRIPTION','VISITORDESCRIPTION','NEUTRALDESCRIPTION'] if r[k])
    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)',(gid,int(r['EVENTNUM']),int(r['PERIOD']),r['PCTIMESTRING'],r['PLAYER1_TEAM_ABBREVIATION'],r['PLAYER1_NAME'],int(r['EVENTMSGTYPE']),desc,r['SCORE'],json.dumps(r)))
  print('PBP',team,len(game_ids),'games',flush=True)
 for id,team,season,game,url in FILMS:
  try:
   raw=download(url,id+'.html'); soup=BeautifulSoup(raw,'html.parser')
   article=soup.find('article')
   if not article: raise ValueError('No article element')
   title=soup.find('h1').get_text(' ',strip=True)
   blocks=[]
   for e in article.select('p,h2,h3'):
    text=e.get_text(' ',strip=True)
    if text.startswith(('John Schuhmann is a senior', 'The views on this page')): break
    if text and not any(x in text for x in ['Related Content','All rights reserved','Privacy Policy','Terms of Use']): blocks.append(text)
   text='\n'.join(blocks)
   if len(text)<600: raise ValueError('Insufficient article text')
   document(id,title,url,'film_study',team,season,game,raw)
   for i,part in enumerate(chunks(text)):
    passage(f'{id}-{i+1}',id,f'extracted passage {i+1}',part)
   print('ARTICLE',id,len(text),flush=True)
  except Exception as exc:
   manifest['errors'].append({'url':url,'error':str(exc)}); print('ARTICLE FAILED',id,str(exc),flush=True)
 raw=download(MANUAL,'wabc-level2.pdf')
 document('wabc-l2','WABC Level 2 Coaches Manual',MANUAL,'coaching_manual','','','',raw)
 reader=PdfReader(io.BytesIO(raw))
 # Index the Team chapter: retain exact PDF page numbers, not inferred printed numbers.
 selected_pages=[]
 for i,page in enumerate(reader.pages):
  text=page.extract_text() or ''
  if any(term in text.lower() for term in ['zone defence','zone defense','offensive tactics','defensive tactics','hand off','handoff','hand-off','off ball','off-ball','screening','motion offence','motion offense']):
   if len(text.strip())<100: continue
   selected_pages.append(i+1)
   for j,part in enumerate(chunks(text)):
    passage(f'wabc-l2-p{i+1}-{j+1}','wabc-l2',f'PDF page {i+1}',part)
 manifest['manual_pdf_pages']=len(reader.pages)
 manifest['indexed_manual_pages']=selected_pages
 manifest['game_count']=db.execute('select count(*) from games').fetchone()[0]
 manifest['event_count']=db.execute('select count(*) from events').fetchone()[0]
 manifest['passage_count']=db.execute('select count(*) from passages').fetchone()[0]
 manifest['limitations']=['Play-by-play does not identify full off-ball actions or defensive coverages.','Film-study cases are selected examples, not an exhaustive tactical census.','No automatic video recognition or complete modern tracking data.','Amateur adaptations are proposals, not tested effectiveness claims.']
 db.commit(); db.execute('VACUUM'); db.close()
 temp.replace(target)
 (DATA/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print({k:manifest[k] for k in ['game_count','event_count','passage_count']},flush=True)
 if manifest['errors']: raise RuntimeError('Some sources failed; inspect data/manifest.json before publishing.')
if __name__=='__main__': build()
