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
            return research.Plan(answer_goal='team_tactics', tactical_phases=['defense'], tasks=[
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
                kind='observation', tactical_phase='defense', source_ids=[source_id],
            )], limitations=[])
        assert data['answer_goal'] == 'team_tactics'
        if agent.name == 'Answer review':
            return research.AnswerReview(adequate=True, missing_requirements=[])
        assert agent.name == 'Evidence audit'
        return research.Audit(verdicts=[research.Verdict(
            claim_index=claim['index'], supported=True, reason='DBB match report confirms the tactic.',
        ) for claim in data['claims']])

    monkeypatch.setattr(research, 'call', fake_call)
    response = TestClient(app.app).post('/chat', json={'message': 'What defensive adjustment did Germany use against Poland?'})
    assert response.status_code == 200
    data = response.json()
    assert data['research']['status'] == 'complete'
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
