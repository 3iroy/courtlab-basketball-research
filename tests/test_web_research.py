import asyncio
import json

import httpx
from agents.tool_context import ToolContext
from fastapi.testclient import TestClient

import app
import research
import web_sources
from context_panel import AgentContexts, PanelHooks


def state():
    return research.RunState(PanelHooks(AgentContexts(), lambda event: None))


async def search_as(worker, query, domain=''):
    return json.loads(await research.search_web.on_invoke_tool(
        ToolContext(context=worker, tool_name='search_web', tool_call_id='test', tool_arguments='{}'),
        json.dumps({'query': query, 'domain': domain}),
    ))


def test_chat_audits_and_cites_retrieved_web_passages(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-token')
    queries = []
    article = {
        'url': 'https://www.nba.com/news/test-(game)',
        'title': 'Test game analysis',
        'published_date': '2024-06-10',
        'content': 'In this game, Boston used a guard-to-guard screen to create a switch.',
        'raw_content': 'Boston repeated the screen after the timeout, setting it between the defenders '
                       'on the wing to clear a driving lane for the guard after the switch.',
    }

    def respond(request):
        assert str(request.url) == web_sources.SEARCH_URL
        assert request.headers['Authorization'] == 'Bearer test-token'
        data = json.loads(request.content)
        assert data['include_answer'] is False
        assert data['include_domains'] == ['nba.com']
        assert data['include_raw_content'] == 'text'
        queries.append(data['query'])
        return httpx.Response(200, json={'results': [
            article,
            {'url': 'javascript:alert(1)', 'title': 'Invalid', 'content': 'Invalid'},
            {'url': 'https://example.com/other', 'title': 'Other source', 'content': 'Outside the named publisher.'},
        ]})

    client_factory = httpx.AsyncClient
    monkeypatch.setattr(web_sources.httpx, 'AsyncClient',
                        lambda **kwargs: client_factory(transport=httpx.MockTransport(respond), **kwargs))

    async def fake_call(agent, prompt, run, turns=1, context=None):
        data = json.loads(prompt)
        if agent.name == 'Lead':
            assert data['catalog']['web_search_available'] is True
            if run.rounds > 1:
                return research.Plan(done=True)
            return research.Plan(web_requested=True, tasks=[
                research.Task(task='Search for a specific Celtics example', focus='web search'),
                research.Task(task='Look up coaching principles', focus='coaching principles'),
            ])
        if agent.name.startswith('Researcher'):
            has_search = any(tool.name == 'search_web' for tool in agent.tools)
            if data['assignment']['focus'] != 'web search':
                assert not has_search
                return research.Notes(findings='No relevant local case.', source_ids=[], gaps=[])
            assert has_search
            assert [tool.name for tool in agent.tools] == ['search_web']
            result = await search_as(context, 'Boston Celtics guard to guard screen', 'nba.com')
            assert len(result['passages']) == 1
            return research.Notes(findings='A guard-to-guard screen in one game.',
                                  source_ids=[result['passages'][0]['source_id']], gaps=[])
        if agent.name == 'Writer':
            source_id, passage = next(iter(data['evidence'].items()))
            assert passage['text'] == article['content'] + '\n\n[...]\n\n' + article['raw_content']
            return research.Report(title='Boston game example', claims=[research.Claim(
                heading='Screen to create a switch', text='Boston used a guard-to-guard screen in this game.',
                kind='observation', source_ids=[source_id],
            )], limitations=[])
        if agent.name == 'Answer review':
            return research.AnswerReview(adequate=True, missing_requirements=[])
        assert agent.name == 'Evidence audit'
        claim = data['claims'][0]
        assert next(iter(claim['evidence'].values()))['text'].startswith(article['content'])
        return research.Audit(verdicts=[research.Verdict(claim_index=claim['index'],
                                                      supported=True, reason='Directly supported.')])

    monkeypatch.setattr(research, 'call', fake_call)
    response = TestClient(app.app).post('/chat', json={'message': 'Search NBA.com for a Celtics tactic example.'})
    assert response.status_code == 200
    data = response.json()
    assert {'response', 'session_id', 'tool_calls'} <= data.keys()
    assert data['research']['status'] == 'complete'
    citation, = data['research']['citations']
    assert citation['url'] == citation['evidence_url'] == 'https://www.nba.com/news/test-%28game%29'
    assert 'published 2024-06-10' in citation['locator']
    assert f"[1]({citation['url']})" in data['response']
    trace, = [call for call in data['tool_calls'] if call['name'] == 'search_web']
    assert trace['agent'] == 'Researcher 1 · web search'
    assert trace['result']['passages'][0]['source_id'] == citation['source_id']
    assert queries == ['Boston Celtics guard to guard screen']
    assert 'test-token' not in response.text


def test_web_search_budget_is_shared_across_parallel_researchers(monkeypatch):
    queries = []

    async def search(query, domain):
        queries.append(query)
        await asyncio.sleep(0)
        return {'passages': []}

    monkeypatch.setattr(web_sources, 'search', search)
    run = state()

    async def do_searches():
        return await asyncio.gather(*(search_as(research.WorkerState(run, f'Researcher {index}'),
                                                f'Public query {index}') for index in range(5)))

    results = asyncio.run(do_searches())
    assert len(queries) == web_sources.MAX_WEB_SEARCHES
    assert sum('error' in result for result in results) == 2
    assert len(run.traces) == 5


def test_unconfigured_and_failed_web_search_have_safe_fallbacks(monkeypatch):
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    assert not TestClient(app.app).get('/catalog').json()['web_search_available']
    assert asyncio.run(web_sources.search('Celtics')) == {'error': 'Web search is not configured.'}
    assert research.web_search_notice(state(), False) == 'Web search is not configured for this deployment.'

    monkeypatch.setenv('TAVILY_API_KEY', 'test-token')
    client_factory = httpx.AsyncClient
    monkeypatch.setattr(web_sources.httpx, 'AsyncClient', lambda **kwargs: client_factory(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, text='test-token')),
        **kwargs,
    ))
    run = state()
    result = asyncio.run(search_as(research.WorkerState(run, 'Researcher 1'), 'Celtics'))
    assert result == {'error': 'Web search is temporarily unavailable.'}
    assert research.web_search_notice(run, True) == 'Web search was unavailable for this answer.'
    assert 'test-token' not in json.dumps(run.traces)


def test_dbb_match_report_supports_concrete_tactics_through_chat(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-token')
    report_url = 'https://www.basketball-bund.de/world-cup-qualifier-herren-test/'
    official_page = f"""
    <div class="teaser-post" data-link="https://www.basketball-bund.de/vorschau/">
      <h4 class="teaser-post__title">DBB-Herren: World Cup Qualifier gegen Polen</h4>
      <p class="teaser-post__excerpt">Polen kommt nach Frankfurt. Das Hinspiel endete 96:94.</p>
      <span class="teaser-post__date">24/09/2026</span>
    </div>
    <div class="teaser-post" data-link="{report_url}">
      <h4 class="teaser-post__title">World Cup Qualifier Herren: DBB-Team siegt in Polen</h4>
      <p class="teaser-post__excerpt">Das deutsche Team gewann gegen Polen 96:94.
        Im zweiten Viertel wechselte Deutschland zur Zonenverteidigung.</p>
      <span class="teaser-post__date">30/08/2026</span>
    </div>
    <div class="teaser-post" data-link="https://example.org/unverified/">
      <h4 class="teaser-post__title">World Cup Qualifier Herren: DBB-Team siegt</h4>
      <p class="teaser-post__excerpt">Das Team gewann 93:90.</p>
      <span class="teaser-post__date">31/08/2026</span>
    </div>
    """

    def respond(request):
        assert request.method == 'GET'
        assert str(request.url) == web_sources.DBB_TEAM_URL
        return httpx.Response(200, text=official_page)

    client_factory = httpx.AsyncClient
    monkeypatch.setattr(web_sources.httpx, 'AsyncClient', lambda **kwargs: client_factory(
        transport=httpx.MockTransport(respond), **kwargs,
    ))

    async def fake_call(agent, prompt, run, turns=1, context=None):
        data = json.loads(prompt)
        if agent.name == 'Lead':
            if run.rounds > 1:
                return research.Plan(done=True)
            return research.Plan(answer_goal='team_tactics', tactical_phases=['defense'],
                                 video_query='Germany Poland basketball match highlights', tasks=[
                research.Task(task='Find Germany game actions', focus='DBB match reports'),
                research.Task(task='Check official FIBA evidence', focus='web search'),
            ])
        if agent.name.startswith('Researcher'):
            if data['assignment']['focus'] == 'DBB match reports':
                assert [tool.name for tool in agent.tools] == ['read_dbb_match_reports']
                output = json.loads(await agent.tools[0].on_invoke_tool(
                    ToolContext(context=context, tool_name='read_dbb_match_reports',
                                tool_call_id='test', tool_arguments='{}'), '{}',
                ))
                passage, = output['passages']
                assert passage['url'] == report_url
                assert 'Zonenverteidigung' in passage['text']
                return research.Notes(findings='Zone defense in the second quarter against Poland.',
                                      source_ids=[passage['source_id']], gaps=[])
            return research.Notes(findings='', source_ids=[], gaps=[])
        if agent.name == 'Writer':
            assert data['answer_goal'] == 'team_tactics'
            source_id, = data['evidence']
            return research.Report(title='Germany against Poland', claims=[research.Claim(
                heading='Second-quarter zone', text='Germany switched to a zone in the second quarter against Poland.',
                kind='observation', tactical_phase='defense', tactical_setup='Switch to zone defense',
                source_ids=[source_id],
            )], limitations=[], follow_up_question='Which game would you like to examine next?')
        assert data['answer_goal'] == 'team_tactics'
        if agent.name == 'Answer review':
            return research.AnswerReview(adequate=True, missing_requirements=[])
        assert agent.name == 'Evidence audit'
        return research.Audit(verdicts=[research.Verdict(
            claim_index=claim['index'], supported=True, tactical_supported=True,
            reason='DBB match report confirms the tactic.',
        ) for claim in data['claims']])

    monkeypatch.setattr(research, 'call', fake_call)
    response = TestClient(app.app).post('/chat', json={'message': 'What defensive adjustment did Germany use against Poland?'})
    assert response.status_code == 200
    data = response.json()
    assert data['research']['status'] == 'complete'
    assert 'follow_up_question' not in data['research']
    assert '## Follow-up' not in data['response']
    assert 'video_links' not in data['research']
    assert data['research']['citations'][0]['url'] == report_url
    assert 'switched to a zone in the second quarter' in data['response']
    trace, = [call for call in data['tool_calls'] if call['name'] == 'read_dbb_match_reports']
    assert trace['agent'] == 'Researcher 1 · DBB match reports'



def test_team_tactics_cannot_complete_with_a_missing_requested_phase():
    defense = research.Claim(
        heading='Zone adjustment', text='Germany switched to a zone against Poland.',
        kind='observation', tactical_phase='defense', source_ids=['web-test'],
    )
    result = asyncio.run(research.review_answer(
        'What tactics does Germany use?', [defense], state(), answer_goal='team_tactics',
        tactical_phases=('offense', 'defense'),
    ))
    assert not result.adequate
    assert result.missing_requirements == ['An evidence-backed offense example from a relevant game is missing.']


def test_tactical_audit_rejects_a_supported_finish_without_a_setup(monkeypatch):
    run = state()
    source_id = 'web-match-recap'
    run.register({
        'source_id': source_id,
        'text': 'Schröder assisted da Silva on an alley-oop. Germany later switched to zone defense.',
    })
    finish = research.Claim(
        heading='Alley-oop', text='Schröder passed to da Silva for an alley-oop.',
        kind='observation', tactical_phase='offense', tactical_setup='Lob pass', source_ids=[source_id],
    )
    zone = research.Claim(
        heading='Zone defense', text='Germany switched to a zone defense.',
        kind='observation', tactical_phase='defense', tactical_setup='Switch to zone defense',
        source_ids=[source_id],
    )

    async def audit(payload, _state):
        return research.Audit(verdicts=[
            research.Verdict(claim_index=claim['index'], supported=True,
                             tactical_supported=claim['heading']=='Zone defense', reason='Verified event.')
            for claim in payload['claims']
        ])

    monkeypatch.setattr(research, 'audit_claims', audit)
    report = research.Report(title='Game tactics', claims=[finish, zone], limitations=[])
    accepted, _, rejected = asyncio.run(research.validate_report(
        report, 'What tactics did Germany use?', {'scope':'match recap'}, run, 'team_tactics',
    ))
    assert accepted == [zone]
    assert rejected == ['The cited evidence does not establish a team scheme or coordinated setup for this claim.']


def test_incomplete_tactics_keeps_citations_and_asks_one_targeted_follow_up(monkeypatch):
    source_id = 'web-match'
    url = 'https://example.com/game-report'
    cited = {
        'source_id': source_id, 'title': 'Qualifying game report', 'text': 'Germany switched to a zone.',
        'url': url, 'evidence_url': url, 'kind': 'official_match_report',
    }
    question = 'Can you share a written breakdown of the offensive setup in that game?'
    tasks = [research.Task(task='Check game coverage', focus='web search'),
             research.Task(task='Read the official report', focus='DBB match reports')]

    async def worker(task, original, run, catalog):
        run.researchers += 1
        if task.focus == 'DBB match reports':
            run.register(cited)
        run.findings.append({'source_ids':[source_id], 'findings':'A zone is documented.', 'gaps':['Offense']})

    async def call(agent, prompt, run, turns=1, context=None):
        data = json.loads(prompt)
        if agent.name == 'Lead':
            return (research.Plan(answer_goal='team_tactics', tasks=tasks)
                    if run.rounds == 1 else research.Plan(done=True))
        if agent.name == 'Writer':
            return research.Report(title='Germany tactics', claims=[research.Claim(
                heading='Zone defense', text='Germany switched to a zone.', kind='observation',
                tactical_phase='defense', tactical_setup='Zone coverage', source_ids=[source_id],
            )], limitations=[], follow_up_question=question if 'missing_requirements' in data else '')
        assert agent.name == 'Evidence audit'
        return research.Audit(verdicts=[research.Verdict(
            claim_index=0, supported=True, tactical_supported=True, reason='The report describes the scheme.',
        )])

    monkeypatch.setattr(research,'worker',worker)
    monkeypatch.setattr(research,'call',call)
    response=TestClient(app.app).post('/chat',json={'message':'How did Germany attack and defend against Poland?'})
    data=response.json()
    assert data['research']['status']=='partial'
    assert data['research']['follow_up_question']==question
    assert data['response'].count(question)==1
    assert data['response'].index('## Follow-up') < data['response'].index('## Sources')
    assert 'An evidence-backed offense example' in data['response']
    assert f'[1]({url})' in data['response']


def test_no_tactical_sources_asks_for_evidence_after_gap_research(monkeypatch):
    searched=[]
    tasks=[research.Task(task='Search the match report',focus='web search'),
           research.Task(task='Search the competition archive',focus='web search')]
    follow_up_task=research.Task(task='Find a breakdown of the exact possession',focus='web search')

    async def worker(task, original, run, catalog):
        run.researchers+=1
        searched.append(task.task)
        run.findings.append({'source_ids':[], 'findings':'No tactical evidence retrieved.', 'gaps':['Setup']})

    async def call(agent, prompt, run, turns=1, context=None):
        assert agent.name=='Lead'
        if run.rounds==1:
            return research.Plan(answer_goal='team_tactics',tactical_phases=['offense'],tasks=tasks)
        if run.rounds==2:
            assert len(json.loads(prompt)['findings'])==2
            return research.Plan(tasks=[follow_up_task])
        return research.Plan(done=True)

    monkeypatch.setattr(research,'worker',worker)
    monkeypatch.setattr(research,'call',call)
    response=TestClient(app.app).post('/chat',json={'message':'How did Germany set up the first-quarter lob against the Netherlands?'})
    data=response.json()
    assert searched==[task.task for task in [*tasks,follow_up_task]]
    assert data['research']['status']=='insufficient_evidence'
    assert data['response'].endswith(data['research']['follow_up_question'])
    assert data['response'].count('?')==1
    assert 'written match report' in data['research']['follow_up_question']


def test_specific_match_gap_withholds_other_match_and_only_requests_written_evidence(monkeypatch):
    source_id='web-poland'
    report={
        'source_id':source_id, 'title':'Germany vs. Poland', 'text':'Germany used pick-and-roll against Poland.',
        'url':'https://example.com/poland', 'evidence_url':'https://example.com/poland',
        'kind':'official_match_report',
    }
    tasks=[research.Task(task='Read German federation reports',focus='DBB match reports'),
           research.Task(task='Search for a breakdown',focus='web search')]

    async def worker(task, original, run, catalog):
        run.researchers+=1
        run.register(report)
        run.findings.append({'source_ids':[source_id], 'findings':'Poland pick-and-roll is documented.', 'gaps':[]})

    async def call(agent, prompt, run, turns=1, context=None):
        if agent.name=='Lead':
            return (research.Plan(answer_goal='team_tactics',tactical_phases=['offense'],tasks=tasks)
                    if run.rounds==1 else research.Plan(done=True))
        if agent.name=='Writer':
            return research.Report(title='Germany tactics',claims=[research.Claim(
                heading='Poland pick-and-roll', text=report['text'], kind='observation',
                tactical_phase='offense', tactical_setup='Pick-and-roll', source_ids=[source_id],
            )],limitations=[],follow_up_question='Can you share a video link or a report?')
        if agent.name=='Answer review':
            assert json.loads(prompt)['audited_answer'][0]['index']==0
            return research.AnswerReview(adequate=False,missing_requirements=['The requested game was against the Netherlands.'],
                                         out_of_scope_claim_indices=[0])
        assert agent.name=='Evidence audit'
        return research.Audit(verdicts=[research.Verdict(
            claim_index=0,supported=True,tactical_supported=True,reason='The event is described by the source.',
        )])

    monkeypatch.setattr(research,'worker',worker)
    monkeypatch.setattr(research,'call',call)
    response=TestClient(app.app).post('/chat',json={
        'message':'How did Germany set up its alley-oop against the Netherlands on August 27, 2026?',
    })
    data=response.json()
    assert data['research']['status']=='insufficient_evidence'
    assert data['research']['citations']==[]
    assert 'Poland' not in data['response']
    assert 'video' not in data['response']
    assert 'written match report' in data['research']['follow_up_question']
    assert data['response'].count('?')==1


def test_published_analysis_survives_official_report_filter(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-token')
    analyst_url='https://analysis.example.com/germany-finland-film-study'
    official_url='https://www.basketball-bund.de/test-match-report/'
    official={
        'source_id':'web-official', 'kind':'official_match_report', 'title':'Match report',
        'url':official_url, 'evidence_url':official_url, 'text':'Germany used zone defense against Finland.',
    }
    analysis_body=(
        'Germany turned ball recoveries into transition attacks against Finland by pushing the ball '
        'up the middle while the outside players sprinted to the corners before the defense set up.'
    )

    async def dbb():
        return {'passages':[official]}

    def respond(request):
        data=json.loads(request.content)
        assert data['include_raw_content']=='text'
        assert data['max_results']==8
        recaps=[{'url':f'https://recap.example.com/game-{i}', 'title':'Final score',
                 'content':'Germany faced Finland.'} for i in range(3)]
        return httpx.Response(200,json={'results':[*recaps,{
            'url':analyst_url, 'title':'Film study of Germany vs. Finland', 'content':'Germany faced Finland.',
            'raw_content':'By Jane Analyst\n\n'+analysis_body,
        }]})

    factory=httpx.AsyncClient
    monkeypatch.setattr(web_sources,'recent_dbb_qualifiers',dbb)
    monkeypatch.setattr(web_sources.httpx,'AsyncClient',lambda **kwargs:factory(
        transport=httpx.MockTransport(respond),**kwargs,
    ))

    async def call(agent,prompt,run,turns=1,context=None):
        payload=json.loads(prompt)
        if agent.name=='Lead':
            if run.rounds>1:
                return research.Plan(done=True)
            return research.Plan(answer_goal='team_tactics',analysis_requested=True,tasks=[
                research.Task(task='Read the match report',focus='DBB match reports'),
                research.Task(task='Find a published film study',focus='tactical analysis'),
            ])
        if agent.name.startswith('Researcher'):
            if payload['assignment']['focus']=='tactical analysis':
                response=await search_as(context,'Germany Finland transition film study')
                source=response['passages'][0]
                assert source['url']==analyst_url
                assert 'By Jane Analyst' in source['text']
                assert analysis_body in source['text']
                return research.Notes(findings='Film study documents transition lanes.',
                                      source_ids=[source['source_id']],gaps=[],
                                      analysis_source_ids=[source['source_id'],'not-retrieved'])
            tool=agent.tools[0]
            await tool.on_invoke_tool(ToolContext(
                context=context,tool_name=tool.name,tool_call_id='test',tool_arguments='{}',
            ),'{}')
            return research.Notes(findings='The report documents zone defense.',source_ids=['web-official'],gaps=[])
        if agent.name=='Writer':
            analyst_id,=payload['analysis_source_ids']
            assert set(payload['evidence'])=={'web-official',analyst_id}
            assert payload['analysis_requested']
            return research.Report(title='Germany against Finland',claims=[
                research.Claim(heading='Early transition',text='Jane Analyst describes Germany filling the corners in transition against Finland.',
                               kind='observation',tactical_phase='offense',tactical_setup='Fill the corners in transition',
                               analysis_source_id=analyst_id,source_ids=[analyst_id]),
                research.Claim(heading='Zone defense',text='Germany used zone defense against Finland.',
                               kind='observation',tactical_phase='defense',tactical_setup='Zone defense',
                               source_ids=['web-official']),
            ],limitations=[])
        if agent.name=='Answer review':
            return research.AnswerReview(adequate=True,missing_requirements=[])
        assert agent.name=='Evidence audit'
        return research.Audit(verdicts=[research.Verdict(
            claim_index=c['index'], supported=True, tactical_supported=True,
            analysis_supported=bool(c['analysis_source_id']), reason='The cited text supports the claim.',
        ) for c in payload['claims']])

    monkeypatch.setattr(research,'call',call)
    response=TestClient(app.app).post('/chat',json={'message':'How did Germany play, and has an analyst explained it?'})
    data=response.json()
    assert data['research']['status']=='complete'
    assert {citation['url'] for citation in data['research']['citations']}=={analyst_url,official_url}
    assert 'Jane Analyst describes' in data['response']
    assert any(entry['agent']=='Researcher 2 · tactical analysis' and entry['args'].get('analysis')
               for entry in data['tool_calls'])


def test_official_observation_alone_cannot_satisfy_requested_analysis():
    claim=research.Claim(heading='Zone defense',text='Germany used zone defense.',
                         kind='observation',tactical_phase='defense',tactical_setup='Zone defense',
                         source_ids=['web-match'])
    review=asyncio.run(research.review_answer(
        'How did a published analyst explain Germany’s defense?', [claim], state(),
        answer_goal='team_tactics',tactical_phases=('defense',),analysis_requested=True,
    ))
    assert not review.adequate
    assert review.missing_requirements==['No published tactical analysis of the requested scope was verified.']



def test_tactical_analysis_search_preserves_assignment_details():
    query=web_sources.focused_analysis_query(
        'Deutschland Finnland Basketball', 'sportschau.de',
        'Find a breakdown of Germany’s transition offense against Finland in the 2025 EuroBasket semifinal.',
    )
    assert query=='Deutschland Finnland Basketball 2025 Halbfinale Analyse Tempo Schnellangriffe'


def test_video_results_stay_separate_from_written_evidence(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY','test-token')
    official_clip='https://www.youtube.com/watch?v=EQXRQXqofT0'
    written='https://example.com/qualifiers/game-report'

    def respond(request):
        return httpx.Response(200,json={'results':[
            {'url':'https://youtu.be/EQXRQXqofT0?si=tracking', 'title':'Germany vs Netherlands highlights',
             'content':'Channel: FIBA Basketball', 'published_date':'2026-08-28'},
            {'url':official_clip, 'title':'Germany vs Netherlands highlights', 'content':'Same video'},
            {'url':written, 'title':'Written game report', 'content':'Germany used a zone.'},
        ]})

    factory=httpx.AsyncClient
    monkeypatch.setattr(web_sources.httpx,'AsyncClient',lambda **kwargs:factory(
        transport=httpx.MockTransport(respond),**kwargs,
    ))
    result=asyncio.run(web_sources.search('Germany Netherlands highlights'))
    assert [source['url'] for source in result['passages']]==[written]
    assert [item['url'] for item in result['videos']]==[official_clip]


def test_missing_tactical_evidence_can_show_a_verified_video_link(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY','test-token')
    url='https://www.youtube.com/watch?v=EQXRQXqofT0'
    title='Germany v Netherlands | Extended Highlights | FIBA Qualifiers'
    question='How did Germany set up the alley-oop against the Netherlands on August 27, 2026?'
    query='Germany Netherlands FIBA qualifiers August 27 2026 basketball highlights'

    def respond(request):
        payload=json.loads(request.content)
        assert payload['query']==query
        assert payload['include_domains']==['youtube.com']
        return httpx.Response(200,json={'results':[{
            'url':url,'title':title,'content':'FIBA Basketball extended highlights.',
            'published_date':'2026-08-28',
        }]})

    factory=httpx.AsyncClient
    monkeypatch.setattr(web_sources.httpx,'AsyncClient',lambda **kwargs:factory(
        transport=httpx.MockTransport(respond),**kwargs,
    ))

    async def worker(task, original, run, catalog):
        run.researchers+=1

    async def call(agent, prompt, run, turns=1, context=None):
        if agent.name=='Lead':
            return (research.Plan(answer_goal='team_tactics',video_query=query,tasks=[
                research.Task(task='Find the tactical setup',focus='web search'),
                research.Task(task='Read the match report',focus='DBB match reports'),
            ]) if run.rounds==1 else research.Plan(done=True))
        assert agent.name=='Video review'
        data=json.loads(prompt)
        assert question in data['question']
        assert data['candidates'][0]['url']==url
        return research.VideoSelection(indices=[0,0,12,-1])

    monkeypatch.setattr(research,'worker',worker)
    monkeypatch.setattr(research,'call',call)
    result=TestClient(app.app).post('/chat',json={'message':question}).json()
    assert result['research']['status']=='insufficient_evidence'
    assert result['research']['video_links']==[{'title':title,'url':url}]
    assert result['research']['citations']==[]
    assert '## Video links' in result['response']
    assert f'[{title}]({url})' in result['response']
    assert result['tool_calls'][-2]['agent']=='Video research'
    assert result['tool_calls'][-2]['name']=='search_videos'
