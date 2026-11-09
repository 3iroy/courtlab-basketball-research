# CourtLab — 从比赛到你的球场

CourtLab helps basketball fans study selected Golden State Warriors (2021–22) and Miami Heat
(2022–23) playoff cases, then develop **proposed adaptations for adult amateur five-on-five teams**.
It combines actual game events, official film-study text, and WABC coaching guidance.
It does not automatically watch video or infer tactical labels from box scores.

## Run locally

```bash
uv sync
cp .env.example .env
gcloud auth application-default login
uv run app.py
```

Open http://localhost:8080. `PORT=8082 uv run app.py` uses an alternate port.
Set `GOOGLE_CLOUD_PROJECT` to a project with Vertex AI access. The example retains the course
project used by the existing Project 1. Never commit credentials. `GEMINI_MODEL`,
`RESEARCHER_MODEL` and `VERTEX_LOCATION` are configurable.

The landing page explains scope and offers three example questions. Ask in Chinese or English.
For amateur advice, describe personnel, shooting/passing abilities, opponent defense and practice
time. The Lead asks questions when essential details are missing. Follow up in the same chat.
The site streams research activity, shows tool records, opens citation evidence in a drawer,
and preserves the starter's per-agent context viewer behind a button.

## Data and provenance

The shipped SQLite database contains 45 playoff games (22 GSW, 23 MIA), 20,372 PBP events,
seven official film-study articles, and selected text pages from the WABC Level 2 manual.
`data/manifest.json` records source URLs, retrieval time, SHA-256 checksums and indexed PDF pages.
The exact passage count is in the manifest and displayed in the UI.

- [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data): archived stats.nba.com events.
  `nbastats_po_2021.tar.xz` is the **2021–22** season; `nbastats_po_2022.tar.xz` is **2022–23**.
  Archive years are season START years. Game IDs are restored to ten characters.
  Select all games where the target team appears, then retain BOTH teams' events for each game.
- [NBA Film Study](https://www.nba.com/news/2022-finals-film-study-game-4): selected 2022 Finals
  G1/G2/G4/G5 and 2023 Heat–Knicks / Heat–Nuggets analyses. Exact URLs are in the manifest.
  Article text is chunked with stable passage IDs; author/footer recommendations are excluded.
- [FIBA/WABC](https://about.fiba.basketball/en/wabc-documents): Level 2 coaching manual pages
  mentioning relevant defensive/offensive tactics, screening, handoffs and motion. Locators use
  **PDF viewer page numbers**, which may differ from the printed page. Text extraction does not
  interpret diagrams. Cite the source PDF page and inspect it for diagram details.

`store.py` opens SQLite read-only and uses parameterized queries and FTS5 search. It supplies:
`list_catalog`, `search_sources` (retrieves full top passages), `read_source`, `get_game_events`,
and `summarize_game`. A summary computes makes/attempts and turnovers from event types and
3PT description tags. It does **not** calculate play-type efficiency or estimate possessions.

To rebuild from the actual upstream files:

```bash
uv run scripts/build_data.py
```

Raw downloads stay in ignored `.downloads/`. The extracted SQLite database is committed and
shipped with the deployment, so no external data download is needed at startup. The build script
never executes downloaded code or blindly extracts archive paths. See `data/NOTICE.md` for attribution.

## Deep Research implementation

1. **Lead** returns one structured plan with 2–3 independent assignments, or requests clarification.
2. All assignments from that plan run concurrently with `asyncio.gather`. Each **Researcher**
   receives a fresh prompt and its own `WorkerState`: question, assignment and catalog only.
   No Lead or sibling transcript is passed to a Researcher.
3. Lead reviews findings and contradictions and requests targeted gap-driven follow-up research.
   Code caps the process at **3 planning rounds, 7 Researchers, 4 exploration turns plus at most 1 no-tool notes turn, and 10 data calls per
   Researcher**. An overall 240-second timeout also cancels in-flight work.
4. **Writer** sees question, findings and retrieved evidence. Observations, proposed adaptations
   and limitations have distinct labels. Adaptations are not claims of tested effectiveness.
5. **Evidence audit** checks each draft claim against its attached passages. Unknown citations
   fail deterministic validation; unsupported or missing audit verdicts are withheld. This is a
   conservative model-assisted check, not a guarantee of correctness; source drawers permit review.

The initial dispatch, follow-up plans and every sub-agent data call appear in `tool_calls` with
`agent`, `name`, `args`, `result`. Contexts show actual model messages, not private reasoning.

## API compatibility

`POST /chat` accepts `{"message":"...","session_id":null}` and preserves Project 1 fields:

```json
{
  "response": "Markdown report or clarification question",
  "session_id": "server-created UUID",
  "tool_calls": [
    {"agent": "Researcher 1 · NBA evidence", "name": "read_source", "args": {}, "result": {}}
  ],
  "research": {"status": "complete", "rounds": 2, "researchers": 3, "citations": []}
}
```

`research` is additive. `POST /run` streams the same final object over SSE plus activity/tool events.
`GET /evidence/{source_id}` returns exact passage text or reproducible event/summary data.
`GET /sessions/{session_id}` restores history; `DELETE` resets a finished chat.
Sessions are process-local, expire after one hour idle, and disappear on restart. A chat is capped at
20 user turns, with only the latest 8 messages supplied to the Lead; repeat older essential constraints.
There are at most 100 sessions and 3 active research runs per instance. Run one worker.

## Validation

```bash
uv run pytest -q
node --check app.js
node --check context-panel.js
```

Tests cover event arithmetic, period/team filters, evidence page locators, input/API shape,
parallel execution with independent worker contexts, gap follow-ups, clarification without dispatch,
and per-worker tool caps. Live same-model comparisons are generated, not invented:

```bash
uv run scripts/compare_models.py
```

The baseline sends only the identical user question to the same model, with no system prompt and
no tools. `data/comparisons.json` includes both full answers, model name, timing and agent traces.
The following three samples include expected checks and actual results after generation.

## Cloud Run and GitHub continuous deployment

`Dockerfile` installs the frozen lock and packages the SQLite data. `cloudbuild.yaml` builds and
pushes an image, then deploys the separate `courtlab` service in `us-east1`, using a dedicated runtime
service account, one maximum instance, concurrency 3 and a 300-second request timeout. The runtime
service account requires Vertex AI invocation access; build/deploy permissions belong to the build
identity. No service account keys are committed.

A **GitHub main-branch push trigger** must actually exist; the YAML alone is not continuous
deployment. Deployment details and the verified URL belong in `submission.json` and
`data/deployment.json`. `submission.json` uses `path: "research"` and inherits `ts3733` from Project 1;
add any other team members before submission. A blank deploy_url means deployment is unfinished.

## Research boundaries

Selected film-study examples cannot establish season-wide tactical frequencies. Event outcomes do
not identify all screens, cuts, coverages or causes. Missing search results do not prove a tactic was
absent. No complete modern player tracking, automated film understanding, live roster updates,
or measured amateur-team outcomes are supplied. NBA examples and WABC principles require judgment
before use under another league's rules and personnel. Insufficient evidence is an acceptable result.
