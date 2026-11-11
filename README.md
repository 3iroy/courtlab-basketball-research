# CourtLab — From Film to Your Court

CourtLab helps amateur players, student teams and developing coaches research basketball tactics,
connect coaching principles to real game evidence, and develop a practical plan for their roster.
Its core sources are **WABC Levels 1–3** and **SkillCorner ACB 2025–26 annotations and offensive aggregates**.
Selected Warriors and Heat playoff cases provide additional examples. It does not watch video,
reconstruct full team playbooks, or promise that an amateur adaptation will improve win rates.

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

The deployed site uses the same Columbia-only IAP login as Project 1.

The landing page explains scope and offers three example questions. Reports and the interface are in English. Questions in other languages are accepted, with English responses.
For amateur advice, describe personnel, shooting/passing abilities, opponent defense and practice
time. The Lead asks questions when essential details are missing. Follow up in the same chat.
Press Enter to send; Shift+Enter inserts a new line. Confirming an IME composition does not submit.
The site streams research activity, shows tool records, opens citation evidence in a drawer,
and preserves the starter's per-agent context viewer behind a button.

## Data and provenance

The shipped SQLite database contains full extracted text from WABC Levels 1–3;
10 ACB games with model-derived annotations for seven action families, plus shots, chances and possessions;
and three player-team-season aggregate tables covering 293 of 327 ACB games. It also retains 45 NBA playoff games,
20,372 PBP events and seven official film-study articles. Exact counts are in `data/manifest.json` and the UI.
The manifest records source URLs, retrieval times, SHA-256 checksums and the pinned SkillCorner commit.

- [SkillCorner basketball open data](https://github.com/SkillCorner/opendata-basketball):
  pinned to `4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66`. Seven action families: picks,
  handoffs, off-ball screens, drives, isolations, posts and closeouts. These are model-derived actions,
  not human-verified full team systems. The app does not ingest raw tracking frames.
  Season aggregates cover 293 games; detailed event files cover ten. Never treat these as the same population.
  Picks aggregates count direct picks only. Traded players have team rows and extra total rows;
  our season tool excludes total rows to prevent combining both. Publisher nulls remain null.
  See `data/SKILLCORNER-LICENSE.txt`, the indexed data dictionary and known issues.
- [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data): archived stats.nba.com events.
  `nbastats_po_2021.tar.xz` is the **2021–22** season; `nbastats_po_2022.tar.xz` is **2022–23**.
  Archive years are season START years. Game IDs are restored to ten characters.
  Select all games where the target team appears, then retain BOTH teams' events for each game.
- [NBA Film Study](https://www.nba.com/news/2022-finals-film-study-game-4): selected 2022 Finals
  G1/G2/G4/G5 and 2023 Heat–Knicks / Heat–Nuggets analyses. Exact URLs are in the manifest.
  Article text is chunked with stable passage IDs; author/footer recommendations are excluded.
- [FIBA/WABC](https://about.fiba.basketball/en/wabc-documents): extracted text from all
  substantive pages of Level 1, 2 and 3 manuals. Locators use **PDF viewer page numbers**,
  which may differ from printed pages. Text extraction does not interpret diagrams.

`store.py` and `acb.py` open SQLite read-only with parameterized queries and allowlisted identifiers.
Tools: `list_catalog`, `search_sources`, `read_source`, `get_game_events`, `summarize_game`,
`count_acb_actions`, `get_acb_actions`, `get_acb_season`.
Action count citations reproduce exact filters and coverage/location breakdowns; example searches are capped
and never used as counts. Season citations identify original CSV lines and metric values.
There is no arbitrary model-written SQL or claim of causal tactical efficiency.

### Optional live web search

Set `TAVILY_API_KEY` in the server environment to enable public web research. The Lead can
assign a Researcher to search when explicitly requested, when a team or season is outside the
local corpus, or when a follow-up finds a gap. The search tool sends short public basketball
queries to Tavily, with up to three requests per answer and a 12-second deadline per request.
Named publishers can be used as a search filter. Bounded excerpts from those pages supplement the search snippets.
The Lead can assign a separate search for published film studies, scouting reports, or coach and
analyst breakdowns. When a passage explains a relevant action, it can accompany official match
reports and is independently checked for its tactical content and attribution. The report names
the writer or publisher and preserves the game and competition scope.
For current Germany men's questions, the Lead can also dispatch a Researcher to read the latest
completed World Cup qualifiers on the German federation's senior men's team page. Team-tactic
reports are audited for source-backed schemes and coordinated setups. Incomplete tactical answers retain
verified observations, state the missing evidence, and ask one focused follow-up question in
the same chat. If no tactic is verified, an optional video lookup can recommend up to two matching
clips in a separate **Video links** section. These are viewing resources and remain separate from
the textual citations and tactical claims. One video-focused search may supplement the evidence
searches, subject to the same request deadline. The response includes that question in the optional research metadata field
`follow_up_question`. A finish can illustrate a tactic when its source describes the setup. Observed examples and measured frequencies are reported separately.
The Writer and evidence audit use the retrieved passages. Numbered web citations open the
original page, and the Research trace shows the excerpt, URL, and Researcher that retrieved it.
Examples from articles do not establish season-wide play frequencies. Search failures leave the
local tools available. The source index shows whether this deployment has search configured.

For Cloud Run, store the key in Secret Manager, grant the CourtLab runtime account accessor
permission on that secret, and map it to `TAVILY_API_KEY` on the service. GitHub builds preserve
the service's secret binding. Keep the key out of Git and browser code.

To rebuild from the actual upstream files:

```bash
uv run scripts/build_data.py
uv run scripts/expand_data.py
```

Raw downloads stay in ignored `.downloads/`. The extracted SQLite database is committed and
shipped with the deployment, so no external data download is needed at startup. The build script
never executes downloaded code or blindly extracts archive paths. See `data/NOTICE.md` for attribution.

## Three sample queries

These are actual runs from 2026-11-11, using `vertex_ai/gemini-3.5-flash` in both columns. Each prompt went to a fresh `POST /chat` session and directly to the same Gemini model as a single user message with no tools or system prompt. The expected answers were checked against the tool data.

### 1. Liga ACB picks and handoffs

> Across the ten annotated 2025–26 Liga ACB games in SkillCorner's open dataset, how many picks and handoffs were logged? In the separate season aggregates, which player-team row led in direct picks as the ball handler and with how many? Use three short bullets.

**Expected answer.** **1,520 picks** and **417 handoffs** across the ten annotated games. In the separate 293-game offensive season aggregates, **Marcelinho Huertas (Lenovo Tenerife)** leads player-team rows with **664 direct picks as the ball handler**.

**Data.** `data/courtlab.sqlite` tables `acb_events` (count `picks` and `handoffs` across all ten games) and `acb_season` (rank the `picks` rows by `handler_total_picks`). Huertas is on line 174 of `data/aggregates/acb_picksaggregates_20252026.csv` in the pinned upstream repository. [Annotated matches](https://github.com/SkillCorner/opendata-basketball/tree/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/data/matches) · [Season CSV row](https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/data/aggregates/acb_picksaggregates_20252026.csv#L174).

<details>
<summary>Actual answers side by side</summary>

<table>
<tr><th>CourtLab with tools</th><th>Same model with no tools or system prompt</th></tr>
<tr>
<td valign="top">
<strong>SkillCorner 2025-26 Liga ACB Pick and Handoff Analysis</strong><br>
<br>
<strong>Annotated Picks Count</strong><br>
<br>
Across the ten annotated 2025-26 Liga ACB games in SkillCorner&#x27;s open dataset, a total of 1,520 picks were logged. <a href="https://courtlab-avomiaf4aq-ue.a.run.app/evidence/acbcount-picks-all-all-all">1</a><br>
<br>
<strong>Annotated Handoffs Count</strong><br>
<br>
Across the same ten annotated games, a total of 417 handoffs were logged. <a href="https://courtlab-avomiaf4aq-ue.a.run.app/evidence/acbcount-handoffs-all-all-all">2</a><br>
<br>
<strong>Season Leader in Direct Picks</strong><br>
<br>
In the separate 293-game offensive season aggregates, Marcelinho Huertas of Lenovo Tenerife led all player-team rows as the ball handler with 664 direct picks across 27 games played. <a href="https://courtlab-avomiaf4aq-ue.a.run.app/evidence/acbseason-picks-174">3</a><br>
<br>
<strong>Evidence limit</strong><br>
<br>
• The ten annotated games represent a small, selected sample of the season and do not reflect overall team playbook frequencies.<br>
• The season aggregates cover 293 of 327 total games, meaning some games are missing from the season-long totals.<br>
<br>
<strong>Sources</strong><br>
<br>
1. <a href="https://github.com/SkillCorner/opendata-basketball/tree/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/data/matches">ACB picks: 1520 annotated actions</a> — family=picks; game=all; offTeamId=all; direct=all<br>
2. <a href="https://github.com/SkillCorner/opendata-basketball/tree/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/data/matches">ACB handoffs: 417 annotated actions</a> — family=handoffs; game=all; offTeamId=all; direct=all<br>
3. <a href="https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/data/aggregates/acb_picksaggregates_20252026.csv">ACB picks: Marcelinho Huertas, Lenovo Tenerife</a> — CSV line 174 (header line 1); player_id=59122; team_id=1333
</td>
<td valign="top">
Here are the details from SkillCorner’s open basketball dataset (noting that the released open dataset covers the <strong>2022–23 Liga ACB season</strong>, rather than 2025–26):<br>
<br>
• <strong>Total Logs:</strong> Across the ten annotated games, a total of <strong>1,811</strong> picks and handoffs were logged.<br>
• <strong>Category Leader:</strong> <strong>Marcelinho Huertas (Lenovo Tenerife)</strong> led the league in direct picks as the ball handler in the season aggregates.<br>
• <strong>Total Direct Picks:</strong> Huertas led the category with <strong>972</strong> direct picks as the ball handler.
</td>
</tr>
</table>

</details>

### 2. 2022 NBA Finals Game 4 box-score totals

> In Game 4 of the 2022 NBA Finals (game ID 0042100404), what were Golden State's field goals and three-pointers made and attempted, and how many turnovers did they commit? Use one short bullet per statistic.

**Expected answer.** Golden State made **40 of 91 field goals** and **15 of 43 three-pointers**, and committed **16 turnovers**.

**Data.** `data/courtlab.sqlite`, table `events`, with `game_id='0042100404'` and `team='GSW'` across all periods. The archived input is `nbastats_po_2021.tar.xz`. [CourtLab event summary](https://courtlab-avomiaf4aq-ue.a.run.app/evidence/summary-0042100404-GSW-0) · [NBA play-by-play](https://www.nba.com/game/0042100404/play-by-play).

<details>
<summary>Actual answers side by side</summary>

<table>
<tr><th>CourtLab with tools</th><th>Same model with no tools or system prompt</th></tr>
<tr>
<td valign="top">
<strong>Golden State Warriors Game 4 Box Score Statistics</strong><br>
<br>
<strong>Warriors Game 4 Shooting and Turnover Totals</strong><br>
<br>
In Game 4 of the 2022 NBA Finals (game ID 0042100404), the Golden State Warriors recorded the following team statistics: <em> Field goals made: 40 </em> Field goals attempted: 91 <em> Three-pointers made: 15 </em> Three-pointers attempted: 43 * Turnovers committed: 16 <a href="https://courtlab-avomiaf4aq-ue.a.run.app/evidence/summary-0042100404-GSW-0">1</a><br>
<br>
<strong>Evidence limit</strong><br>
<br>
• The statistics are derived from the official play-by-play event summary and do not include player-specific tracking or shot-clock details.<br>
<br>
<strong>Sources</strong><br>
<br>
1. <a href="https://www.nba.com/game/0042100404/play-by-play">GSW game 0042100404, period all: event summary</a> — game_id=0042100404, team=GSW, period=0
</td>
<td valign="top">
Here are the Golden State Warriors&#x27; statistics for Game 4 of the 2022 NBA Finals:<br>
<br>
• <strong>Field goals made:</strong> 40<br>
• <strong>Field goals attempted:</strong> 91<br>
• <strong>Three-pointers made:</strong> 15<br>
• <strong>Three-pointers attempted:</strong> 43<br>
• <strong>Turnovers committed:</strong> 16
</td>
</tr>
</table>

</details>

### 3. Gapping and flashing against a zone

> For an adult recreational team facing a 2–3 zone, what does the WABC Level 2 Coaches Manual mean by gapping the zone, and when and where should a player flash from behind it? Give two short coaching cues and cite the manual page.

**Expected answer.** Position yourself between two zone defenders. When the defender turns toward the ball, flash from behind that defender toward the ball and into the opening near the free-throw line.

**Data.** `data/courtlab.sqlite`, table `passages`, passage `wabc-l2-p324-1`. WABC Level 2 Coaches Manual, section 2.4.1, printed page 322 (PDF page 324). [WABC manual page](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=324).

<details>
<summary>Actual answers side by side</summary>

<table>
<tr><th>CourtLab with tools</th><th>Same model with no tools or system prompt</th></tr>
<tr>
<td valign="top">
<strong>WABC Zone Offense Principles: Gapping and Flashing</strong><br>
<br>
<strong>Gapping the Zone and Flashing Mechanics</strong><br>
<br>
According to the WABC Level 2 Coaches Manual, &quot;gapping the zone&quot; means to stand in between two defenders rather than directly opposite one, such as positioning between defenders x2 and x4. A player should flash from &quot;behind the zone&quot;—defined as being further away from the ball than the defender—when defenders turn to focus on the player with the ball. The player should flash towards the ball or to a gap at the free throw line. <a href="https://courtlab-avomiaf4aq-ue.a.run.app/evidence/wabc-l2-p324-1">1</a><br>
<br>
<strong>Coaching Cues and Manual Citation</strong><br>
<br>
The manual outlines two short coaching cues to guide players: &quot;Gap the Zone&quot; to remind players to stand between defenders, and &quot;If you can see the back of a defender’s head, they cannot see you!&quot; to trigger the flash cut. These principles and cues are detailed on page 322 of the WABC Level 2 Coaches Manual. <a href="https://courtlab-avomiaf4aq-ue.a.run.app/evidence/wabc-l2-p324-1">1</a><br>
<br>
<strong>Evidence limit</strong><br>
<br>
• The WABC Level 2 Coaches Manual provides simplified diagrams of these movements but does not detail specific adjustments if defenders actively bump or match up to deny the flash cut.<br>
<br>
<strong>Sources</strong><br>
<br>
1. <a href="https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=324">WABC Level 2 Coaches Manual</a> — PDF page 324
</td>
<td valign="top">
Based on the <strong>WABC (World Association of Basketball Coaches) Level 2 Coaches Manual</strong>, here is how to apply these concepts to help your adult recreational team break a 2–3 zone:<br>
<br>
<strong>1. What is &quot;Gapping the Zone&quot;?</strong><br>
&quot;Gapping the zone&quot; means positioning your offensive players in the <strong>seams or spaces between the defenders</strong>, rather than standing directly in front of them.<br>
• <strong>Why it works:</strong> If an offensive player stands directly in front of a defender, they are easy to guard. By sitting in the &quot;gaps&quot; (e.g., between the top guard and the wing defender), you force two defenders to make a decision on who should guard you. This distorts the zone, opens up clean passing lanes, and creates quick catch-and-shoot or drive opportunities.<br>
<br>
<strong>2. Flashing From Behind the Zone: When and Where?</strong><br>
&quot;Flashing&quot; refers to a sudden, hard cut into an open space to receive the ball.<br>
• <strong>Where to flash:</strong> A player should flash from <strong>behind the baseline, the short corner, or the weak-side low post</strong> (behind the backline of the 2–3 zone) up into the <strong>high post or the center of the key</strong> (the &quot;heart&quot; of the zone).<br>
• <strong>When to flash:</strong> The player should flash <strong>as the ball is passed to the wing</strong> or when the defenders shift their heads to look at the ball. <br>
• <strong>Why it works:</strong> Because the cutter starts behind the defensive line, they are in the defenders&#x27; &quot;blind spots.&quot; Defenders cannot watch both the ball on the wing and the player cutting from behind them at the same time.<br>
<br>
<hr><br>
<br>
<strong>Two Short Coaching Cues</strong><br>
1. <strong>&quot;Find the gaps, not the jerseys!&quot;</strong> <em>(Reminds players to stand in the spaces between defenders, not right in front of them).</em><br>
2. <strong>&quot;Cut from the blind spot!&quot;</strong> <em>(Reminds players to flash to the high post from behind the defenders&#x27; backs as soon as the ball moves).</em><br>
<br>
<hr><br>
<br>
<strong>Citation</strong><br>
• <strong>Source:</strong> <em>WABC Level 2 Coaches Manual</em>, Chapter 3: Team Offence, Section 3.4 &quot;Zone Offence&quot; (specifically under &quot;Principles of Zone Offence&quot;), <strong>Page 174</strong>.
</td>
</tr>
</table>

</details>

## Deep Research implementation

1. **Lead** returns one structured plan with 2–3 independent assignments, or requests clarification.
2. All assignments from that plan run concurrently with `asyncio.gather`. Each **Researcher**
   receives a fresh prompt and its own `WorkerState`: question, assignment and catalog only.
   No Lead or sibling transcript is passed to a Researcher.
3. Lead reviews findings and contradictions and requests targeted gap-driven follow-up research.
   Code caps the process at **3 planning rounds, 7 Researchers, 4 exploration turns plus at most 1 no-tool notes turn, and 10 data calls per
   Researcher**. An overall 240-second timeout also cancels in-flight work.
4. **Writer** sees question, findings and retrieved evidence. Reports default to 2–3 short sections (about 150–220 words), with explicit labels for proposed adaptations and evidence limits. Sources and tool traces are collapsed in the frontend; API reports retain the full bibliography. Adaptations are not claims of tested effectiveness.
5. **Evidence audit** checks each draft claim against its attached passages. Unknown citations
   fail deterministic validation; unsupported or missing audit verdicts are withheld. This is a
   conservative model-assisted check, not a guarantee of correctness; source drawers permit review.

Questions are tagged with an explicit answer goal. After citation checks, a separate Answer review
checks direct responsiveness, preserved constraints and every explicit requested part. Practical advice
must retain a supported proposed adaptation. A missing part triggers one bounded Writer rewrite
with audit and coverage feedback; a remaining incomplete answer is marked `partial`.
Sweeping assertions that an entire WABC manual lacks guidance are rejected deterministically; adding a citation to a selective passage does not prove absence across the manual.
Zone-attack searches require zone/offense content and bridge British/American spelling.

The initial dispatch, follow-up plans and every sub-agent data call appear in `tool_calls` with
`agent`, `name`, `args`, `result`. Contexts show actual model messages, not private reasoning.

## Static tactic diagrams

Tactical answers can include one static SVG half-court diagram beneath the text. The Writer emits
bounded player positions and pass/run/screen arrows; it never emits SVG or HTML. Server validation
rejects duplicate/overlapping markers, absent arrow origins and unaccepted claim links. A separate
bounded evidence check compares the diagram with its accepted claim; a failed check omits only
the optional image. The frontend renders typed data with SVG DOM elements and textContent.
Every figure is labeled as a concept or proposed adaptation, links its underlying principles,
and states that positions are illustrative rather than measured tracking. Statistics-only answers
and clarification questions need no diagram. The optional data lives in `research.diagram`;
Project 1's response/session_id/tool_calls fields remain unchanged. There is no animation or video.

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
and per-worker tool caps.

The screenshot-driven zone-attack regression is saved in
[`data/zone-regression.json`](data/zone-regression.json). It uses a reconstructed scenario.
Earlier comparisons and tool traces are available in
[`data/comparisons.json`](data/comparisons.json) and
[`data/acb-comparison.json`](data/acb-comparison.json).
Run `uv run scripts/compare_models.py` or `uv run scripts/compare_acb.py` to replay those historical prompts.

The final interface, clarification questions and reports are English. Transient model rate limits return an actionable 429 response; citation audits run in bounded batches so malformed audit output cannot abort unrelated supported claims.

## Cloud Run and GitHub continuous deployment

`Dockerfile` installs the frozen lock and packages the SQLite data. `cloudbuild.yaml` builds and
pushes an image, then deploys the separate `courtlab` service in `us-east1`, using a dedicated runtime
service account, one maximum instance, concurrency 3 and a 300-second request timeout. The runtime
service account requires Vertex AI invocation access; build/deploy permissions belong to the build
identity. No service account keys are committed.

A **GitHub main-branch push trigger** must actually exist; the YAML alone is not continuous
deployment. Deployment details and the verified URL belong in `submission.json` and
`data/deployment.json`. `submission.json` uses `path: "research"` and inherits `ts3733` from Project 1;
add any other team members before submission. The Cloud Run service is deployed. Developer Connect links this repository to Cloud Build in `us-east1`. The `courtlab-main` trigger runs `cloudbuild.yaml` for pushes to `main` and deploys to the existing CourtLab service. See `data/deployment.json` for the trigger and service identifiers.

## Research boundaries

Selected film-study examples cannot establish season-wide tactical frequencies. Event outcomes do
not identify all screens, cuts, coverages or causes. Missing search results do not prove a tactic was
absent. No complete modern player tracking, automated film understanding, live roster updates,
or measured amateur-team outcomes are supplied. NBA examples and WABC principles require judgment
before use under another league's rules and personnel. Insufficient evidence is an acceptable result.
