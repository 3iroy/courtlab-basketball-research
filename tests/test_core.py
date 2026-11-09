import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from agents.tool_context import ToolContext
import app
import research
import store
from context_panel import AgentContexts,PanelHooks

client=TestClient(app.app)

def test_corpus_and_game_calculation():
    c=store.catalog()
    assert len(c['games'])==45
    assert sum(x['team']=='GSW' for x in c['games'])==22
    s=store.game_summary('0042100404','GSW')
    assert s['field_goals']=={'made':40,'attempted':91}
    assert s['three_pointers']=={'made':15,'attempted':43}
    q4=store.game_summary('0042100404','GSW',4)
    rows=store.game_events('0042100404',4,'',40)['events']
    assert all(r['period']==4 for r in rows)
    assert q4['field_goals']['attempted']<91
    assert 'error' in store.game_summary('0042100404','MIA')

def test_search_and_citable_pdf_page():
    r=store.search('zone defence',kind='coaching_manual')
    assert r['results']
    ev=store.read_passage(r['results'][0]['id'])
    assert ev['text'] and '#page=' in ev['url'] and 'PDF page' in ev['locator']
    assert 'error' in store.read_passage("' OR 1=1 --")
    assert store.search('" OR * (') .get('error')

def test_api_contract_and_evidence():
    assert client.get('/health').json()['ok']
    assert set(client.post('/chat',json={}).json()) >= {'response','session_id','tool_calls'}
    assert client.post('/chat',json={'message':'  '}).status_code==400
    assert client.post('/chat',json={'message':'test','session_id':'unknown'}).status_code==404
    assert client.get('/evidence/event-0042100404-2').status_code==200
    assert client.get('/evidence/missing').status_code==404
    data=client.get('/evidence/summary-0042100404-GSW-0').json()
    assert data['three_pointers']['made']==15

def test_parallel_fresh_contexts_and_followup(monkeypatch):
    starts=[]; shared={'active':0,'peak':0}; seen_prompts=[]
    async def fake_call(agent,prompt,state,turns=1,context=None):
        if agent.name=='Lead':
            if state.rounds==1:
                return research.Plan(tasks=[research.Task(task='NBA case',focus='NBA evidence'),research.Task(task='manual principles',focus='coaching principles')])
            if state.rounds==2:
                return research.Plan(tasks=[research.Task(task='resolve missing detail',focus='evidence gap')],gaps=['missing detail'])
            return research.Plan(done=True)
        assert agent.name.startswith('Researcher')
        starts.append(context)
        seen_prompts.append(json.loads(prompt))
        shared['active']+=1;shared['peak']=max(shared['peak'],shared['active'])
        await asyncio.sleep(.01)
        shared['active']-=1
        return research.Notes(findings='Insufficient evidence',source_ids=[],gaps=['missing detail'])
    monkeypatch.setattr(research,'call',fake_call)
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    answer,meta=asyncio.run(research.deep_research('specific question',state))
    assert shared['peak']==2 and len(starts)==3
    assert len({id(x) for x in starts})==3
    assert all('findings' not in p and set(p)=={'question','assignment','catalog'} for p in seen_prompts)
    assert meta['status']=='insufficient_evidence' and meta['researchers']==3
    assert state.rounds<=research.MAX_ROUNDS
    assert all('agent' in x for x in state.traces)

def test_clarification_does_not_dispatch(monkeypatch):
    async def fake_call(*a,**kw):return research.Plan(clarification='Which team and research goal?')
    monkeypatch.setattr(research,'call',fake_call)
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    answer,meta=asyncio.run(research.deep_research('basketball',state))
    assert meta['status']=='clarification' and state.researchers==0

def test_caps_and_unknown_citations():
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    own=research.WorkerState(state,'Researcher test')
    for _ in range(11):out=json.loads(own.execute('test',{},lambda:{'value':True}))
    assert 'error' in out and len(state.traces)==11
    ev=store.read_passage('mia-nyk-3')
    text,citations=research.render_report('Title',[
        research.Claim(heading='Case',text='Source-supported example',kind='observation',source_ids=['mia-nyk-3'])],[],[],{'mia-nyk-3':ev})
    assert '/evidence/mia-nyk-3' in text and citations[0]['source_id']=='mia-nyk-3'

def test_search_tool_returns_read_evidence():
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    own=research.WorkerState(state,'Researcher test')
    result=asyncio.run(research.search_sources.on_invoke_tool(
        ToolContext(context=own,tool_name='search_sources',tool_call_id='test',tool_arguments='{}'),json.dumps({'query':'gsw-g4','team':'GSW','kind':'film_study'})))
    data=json.loads(result)
    assert len(data['passages'])==3
    assert all(p['text'] and p['source_id'] in own.read_ids for p in data['passages'])
    assert all(p['source_id'] in state.evidence for p in data['passages'])

def test_researcher_finalizes_after_exploration_cap(monkeypatch):
    calls=[]
    async def fake_call(agent,prompt,state,turns=1,context=None):
        calls.append((agent.name,turns))
        if not agent.name.endswith('notes'):
            ev=store.read_passage('mia-nyk-3')
            context.read_ids.add(ev['source_id']);state.register(ev)
            raise research.MaxTurnsExceeded('cap')
        payload=json.loads(prompt)
        assert set(payload['your_retrieved_evidence'])=={'mia-nyk-3'}
        assert agent.tools==[]
        return research.Notes(findings='Supported notes',source_ids=['mia-nyk-3','unknown'],gaps=[])
    monkeypatch.setattr(research,'call',fake_call)
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    result=asyncio.run(research.worker(research.Task(task='case study',focus='NBA evidence'),'question',state,{}))
    assert result['source_ids']==['mia-nyk-3']
    assert len(calls)==2 and calls[0][1]==4 and calls[1][1]==1

def test_chat_and_stream_share_project1_shape(monkeypatch):
    async def fake_research(question,state):
        state.trace('Researcher 1','read_source',{'source_id':'mia-nyk-3'},{'source_id':'mia-nyk-3'})
        return 'Supported answer',{'status':'complete','rounds':1,'researchers':2,'citations':[]}
    monkeypatch.setattr(app,'deep_research',fake_research)
    response=client.post('/chat',json={'message':'A precise question'})
    assert response.status_code==200
    data=response.json()
    assert set(data)>={'response','session_id','tool_calls'}
    assert data['tool_calls'][0]['agent']=='Researcher 1'
    stream=client.post('/run',json={'message':'Follow up','session_id':data['session_id']})
    events=[json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
    assert events[0]['type']=='start' and events[-1]['type']=='done'
    assert events[-1]['response']=='Supported answer'
    assert events[-1]['tool_calls'][0]['agent']=='Researcher 1'
    assert len(client.get('/sessions/'+data['session_id']).json()['messages'])==4

def test_unretrieved_citation_and_unverified_limit_are_withheld(monkeypatch):
    ev=store.read_passage('mia-nyk-3')
    async def fake_worker(task,question,state,catalog):
        state.researchers+=1;state.register(ev)
        result={'findings':'Supported case','source_ids':['mia-nyk-3'],'gaps':[]}
        state.findings.append(result);return result
    async def fake_call(agent,prompt,state,turns=1,context=None):
        if agent.name=='Lead':
            return research.Plan(tasks=[research.Task(task='a',focus='NBA evidence'),research.Task(task='b',focus='coaching principles')]) if state.rounds==1 else research.Plan(done=True)
        if agent.name=='Writer':return research.Report(title='Brief',claims=[
            research.Claim(heading='Supported',text='A supported case.',kind='observation',source_ids=['mia-nyk-3']),
            research.Claim(heading='Invented',text='This must never display.',kind='observation',source_ids=['not-read'])],limitations=['The available quarter is missing.'])
        payload=json.loads(prompt)
        assert all('not-read' not in c['source_ids'] for c in payload['claims'])
        return research.Audit(verdicts=[research.Verdict(claim_index=0,supported=True,reason='supported'),research.Verdict(claim_index=1,supported=False,reason='The quarter exists; unqueried is not absent.')])
    monkeypatch.setattr(research,'worker',fake_worker);monkeypatch.setattr(research,'call',fake_call)
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    text,meta=asyncio.run(research.deep_research('specific question',state))
    assert 'This must never display' not in text and 'The available quarter is missing' not in text
    assert meta['withheld_claims']==2 and len(meta['citations'])==1

def test_interface_and_report_labels_are_english():
    import re
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for filename in ['index.html','app.js','context-panel.js','app.py','research.py']:
        assert not re.search(r'[\u4e00-\u9fff]',(root/filename).read_text()),filename
    assert 'Always write in English' in research.COMMON
    assert 'previous session expired' in (root/'app.js').read_text()
    ev=store.read_passage('mia-nyk-3')
    text,_=research.render_report('Brief',[research.Claim(heading='Case',text='A supported example.',kind='observation',source_ids=['mia-nyk-3'])],['Selected cases only.'],[],{'mia-nyk-3':ev})
    assert 'A supported example.' in text and '## Sources' in text and not re.search(r'[\u4e00-\u9fff]',text)

def test_malformed_audit_batch_does_not_crash_other_claims(monkeypatch):
    async def fake_call(agent,prompt,state,turns=1,context=None):
        items=json.loads(prompt)['claims']
        if items[0]['index']==0:raise research.ModelBehaviorError('Invalid JSON')
        return research.Audit(verdicts=[research.Verdict(claim_index=c['index'],supported=True,reason='Supported.') for c in items])
    monkeypatch.setattr(research,'call',fake_call)
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    result=asyncio.run(research.audit_claims({'claims':[{'index':i} for i in range(4)]},state))
    assert [v.supported for v in result.verdicts]==[False,False,False,True]
    assert any(t['name']=='audit_batch_unavailable' for t in state.traces)

def test_rate_limit_returns_actionable_english_response(monkeypatch):
    async def busy_model(question,state):
        raise app.RateLimitError(message='busy',llm_provider='vertex_ai',model='test')
    monkeypatch.setattr(app,'deep_research',busy_model)
    result=client.post('/chat',json={'message':'A precise question'})
    assert result.status_code==429
    assert result.json()['research']['status']=='rate_limited'
    assert 'temporarily busy' in result.json()['response']

def test_acb_counts_and_citations_match_raw_source():
    import acb
    with store.connect() as db:
        raw={'picks':[json.loads(r[0]) for r in db.execute("SELECT raw_json FROM acb_events WHERE game_id='114243' AND family='picks'")]}
    total=acb.action_counts('picks','114243')
    assert total['event_count']==len(raw['picks'])==135
    direct=acb.action_counts('picks','114243',direct='direct')
    indirect=acb.action_counts('picks','114243',direct='indirect')
    assert direct['event_count']==sum(x['direct'] for x in raw['picks'])
    assert direct['event_count']+indirect['event_count']==total['event_count']
    assert store.evidence(total['source_id'])==total
    examples=acb.action_events('handoffs','114243')['events']
    assert len(examples)==5
    assert store.evidence(examples[0]['source_id'])==examples[0]
    assert client.get(examples[0]['evidence_url']).status_code==200
    assert 'error' in acb.action_counts("picks' OR 1=1 --")
    assert 'error' in acb.action_counts('picks',team_id='999999')
    assert 'error' in acb.action_counts('picks',game_id='999999')

def test_acb_aggregate_provenance_and_no_total_duplicates():
    import acb
    result=acb.season_rows('picks',['handler_total_picks','handler_ppp'],limit=8)
    assert len(result['rows'])==8
    values=[x['row']['handler_total_picks'] for x in result['rows']]
    assert values==sorted(values,reverse=True)
    assert all(x['row']['team_name']!='total' for x in result['rows'])
    for ev in result['rows']:
        original=store.evidence(ev['source_id'])
        assert original['row']['handler_total_picks']==ev['row']['handler_total_picks']
        assert 'CSV line' in ev['locator']
    assert 'error' in acb.season_rows('picks',["made_up_metric"])
    assert 'error' in acb.season_rows('shots; DROP TABLE games', ['attempts'])

def test_acb_tool_calls_register_evidence_and_agent_field():
    state=research.RunState(PanelHooks(AgentContexts(),lambda x:None))
    worker=research.WorkerState(state,'Researcher ACB')
    out=asyncio.run(research.count_acb_actions.on_invoke_tool(
        ToolContext(context=worker,tool_name='count_acb_actions',tool_call_id='test',tool_arguments='{}'),json.dumps({'family':'picks','game_id':'114243'})))
    result=json.loads(out)
    assert result['source_id'] in state.evidence and result['source_id'] in worker.read_ids
    assert state.traces[-1]['agent']=='Researcher ACB'

def test_extended_catalog_and_full_manuals():
    c=store.catalog()
    assert len(c['acb']['games'])==10
    for level in (1,2,3):
        assert store.search(f'wabc-l{level}')['results']
    assert len(c['acb']['teams'])>10
    assert client.get('/manifest').json()['acb_aggregate_game_count']==293
