# CourtLab — From Film to Your Court

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

The deployed site uses the same Columbia-only IAP login as Project 1.

The landing page explains scope and offers three example questions. Reports and the interface are in English. Questions in other languages are accepted, with English responses.
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

The final interface, clarification questions and reports are English. Transient model rate limits return an actionable 429 response; citation audits run in bounded batches so malformed audit output cannot abort unrelated supported claims.

The baseline sends only the identical user question to the same model, with no system prompt and
no tools. `data/comparisons.json` includes both full answers, model name, timing and agent traces.
The following three samples include expected checks and actual results. Saved examples also receive a final evidence audit; their pre-audit answers and verdicts are retained for transparency. A format-only retry is bounded to one attempt when a no-tool agent returns invalid JSON.

## Cloud Run and GitHub continuous deployment

`Dockerfile` installs the frozen lock and packages the SQLite data. `cloudbuild.yaml` builds and
pushes an image, then deploys the separate `courtlab` service in `us-east1`, using a dedicated runtime
service account, one maximum instance, concurrency 3 and a 300-second request timeout. The runtime
service account requires Vertex AI invocation access; build/deploy permissions belong to the build
identity. No service account keys are committed.

A **GitHub main-branch push trigger** must actually exist; the YAML alone is not continuous
deployment. Deployment details and the verified URL belong in `submission.json` and
`data/deployment.json`. `submission.json` uses `path: "research"` and inherits `ts3733` from Project 1;
add any other team members before submission. The Cloud Run service is deployed. GitHub continuous deployment remains pending the Developer Connect app being granted access to this new repository; see data/deployment.json for the verified state.

## Research boundaries

Selected film-study examples cannot establish season-wide tactical frequencies. Event outcomes do
not identify all screens, cuts, coverages or causes. Missing search results do not prove a tactic was
absent. No complete modern player tracking, automated film understanding, live roster updates,
or measured amateur-team outcomes are supplied. NBA examples and WABC principles require judgment
before use under another league's rules and personnel. Insufficient evidence is an acceptable result.

<!-- COMPARISONS -->
## Three sample queries: expected checks and actual comparisons

### Sample 1

In Game 4 of the 2022 NBA Finals (game_id=0042100404), what were the Warriors’ field goals, three-pointers and turnovers? Use the official G4 film study to explain one supported late-game defensive sequence. Explain what play-by-play cannot establish.

Expected: GSW G4 FG 40/91, 3PT 15/43, 16 turnovers from events/game_id=0042100404. Tactical interpretation requires gsw-g4 passages, not PBP alone.

Model: `vertex_ai/gemini-3.5-flash`. Actual elapsed time including baseline: 58.21 seconds.

<details><summary>Actual outputs — same model, side by side</summary>

<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr><td>Based on the official box score and game analysis of Game 4 of the 2022 NBA Finals (Game ID: `0042100404`), here are the Golden State Warriors&#x27; team statistics, followed by a breakdown of a critical late-game defensive sequence and what standard play-by-play data fails to capture.<br><br>---<br><br>### **Warriors Team Statistics (Game 4)**<br>* **Field Goals:** **40-of-91** (44.0%)<br>* **Three-Pointers:** **1</td><td># Warriors Game 4 Defensive and Statistical Analysis<br><br>## Warriors Game 4 Team Shooting and Turnovers<br><br>**Evidence**<br><br>In Game 4 of the 2022 NBA Finals, the Golden State Warriors recorded 40 made field goals on 91 attempts (43.9%), 15 made three-pointers on 43 attempts (34.9%), and committed 16 turnovers. [1](/evidence/summary-0042100404-GSW-0)<br><br>## Late-Game Flare Screen Defense<br><br>**Evidence**<br><br>Midway through the fourth quarter of Game 4, Robert Williams III set a flare screen for Jayson Tatum that flattened Andrew Wiggins. Kevon Looney switched off Williams to contain Tatum&#x27;s baseline drive, while Jordan Poole provided timely help and Klay Thompson rotated down to Derrick White, forcing Tatum to reset. [2](/evidence/gsw-g4-3)<br><br>## Curry&#x27;s Switch and Shot-Clock Violation<br><br>**Evidence**<br><br>Following Tatum&#x27;s reset in the same possession, Marcus Smart set a screen to switch Stephen Curry onto Tatum. Curry successfully stayed in front of Tatum&#x27;s drive, forcing a tough step-back shot and a shot-clock violation. [2](/evidence/gsw-g4-3)<br><br>## Play-by-Play Data Limitations<br><br>**Evidence limit**<br><br>Play-by-play data records discrete events and outcomes like shots, turnovers, and fouls. However, it cannot establish complete off-ball movement, defensive coverages, switches, help rotations, or individual contests, such as the flare screen, Looney&#x27;s switch, Poole&#x27;s help, or Thompson&#x27;s rotation. [2](/evidence/gsw-g4-3)<br><br>## Limitations<br><br>- This analysis is limited to the scope of Game 4 of the 2022 NBA Finals and the provided film study documents.<br>- Play-by-play data does not capture off-ball movement or defensive coverages.<br><br>## Sources<br><br>1. [GSW game 0042100404, period all: event summary](https://www.nba.com/game/0042100404/play-by-play) — game_id=0042100404, team=GSW, period=0<br>2. [Finals Film Study: How Warriors won Game 4 to even the series](https://www.nba.com/news/2022-finals-film-study-game-4) — extracted passage 3</td></tr></table>

</details>

Full tool trace: `data/comparisons.json`, sample 1.

### Sample 2

According to the official 2023 Heat–Knicks film study, how did Miami counter top-blocking with backdoor cuts and fake handoffs? Explain specific sourced cases without inferring season-wide frequency.

Expected: Heat–Knicks case evidence about top-blocking, backdoor cuts, Love shooting and Adebayo fake-handoff options in mia-nyk passages. No season-wide frequency claim.

Model: `vertex_ai/gemini-3.5-flash`. Actual elapsed time including baseline: 74.24 seconds.

<details><summary>Actual outputs — same model, side by side</summary>

<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr><td>In the official film studies and tactical breakdowns of the 2023 Eastern Conference Semifinals between the Miami Heat and the New York Knicks (most notably analyzed by Miami Heat official writer Couper Moorhead in his series film reviews, alongside broader NBA film analysts), the chess match of the series heavily revolved around how Miami countered the Knicks’ &quot;top-blocking&quot; defensive scheme.<br><br>To limit Miami’s highly effective dribble-handoff (DHO) game, Tom Thibodeau’s defense instructed perimeter defenders (such as Quentin Grimes, Josh Hart, and RJ Barrett) to &quot;top-block.&quot; This meant the defender positioned their body on the high side of the screen/handoff, physically blocking the Miami shooter (such as Duncan Robinson or Max Strus) from curling over the top of Bam Adebayo to receive the ball on the perimeter.<br><br>Miami neutralized this specific defensive pressure using two primary counters: **backdoor cuts (rejects)** and **fake handoffs (keepers)**. <br><br>---<br><br>### Counter 1: Backdoor Cuts (The Reject)<br>When a defender top-blocked, they effectively surrendered the path to the basket in exchange for denying the three-point line. Miami&#x27;s film studies highlighted how the Heat systematically exploited this over-aggression.<br><br>*   **The Mechanic:** Rather than fighting to get over the top of Bam Adebayo&#x27;s screen, the Heat shooter would plant their foot and &quot;reject&quot; the</td><td># Miami Heat Counters to Knicks Top-Blocking in the 2023 Playoffs<br><br>## Strus Rejecting a Screen for a Layup<br><br>**Evidence**<br><br>On a subsequent possession in the third quarter of Game 2, Max Strus countered the Knicks&#x27; overplay by rejecting a screen. He drove directly to the rim and scored a layup before either defender could recover. [1](/evidence/mia-nyk-3)<br><br>## Scope and Data Limitations of the Film Study<br><br>**Evidence limit**<br><br>This analysis is limited to the selected-case scope of the 2023 Heat–Knicks Eastern Conference Semifinals (specifically Game 2). Furthermore, the retrieved documents lack exact play-by-play event IDs, timestamps, and outcomes for certain plays, such as Adebayo&#x27;s fake handoff dunk and Love&#x27;s wing 3-pointer. [1](/evidence/mia-nyk-3)<br><br>## Limitations<br><br>- The analysis is limited to the selected-case scope of the 2023 Heat–Knicks Eastern Conference Semifinals, specifically Game 2.<br>- The retrieved documents lack exact play-by-play event IDs, timestamps, and outcomes for certain plays, such as Adebayo&#x27;s fake handoff dunk and Love&#x27;s wing 3-pointer.<br><br><br>3 draft claim(s) withheld after citation checks.<br><br>## Sources<br><br>1. [Playoffs Film Study: Heading into Game 3, Knicks and Heat present offensive contrast](https://www.nba.com/news/knicks-heat-game-3-offensive-contrast) — extracted passage 3</td></tr></table>

</details>

Full tool trace: `data/comparisons.json`, sample 2.

### Sample 3

We are an adult amateur five-on-five team with one 60-minute practice per week, no tall center, two reliable open shooters and one passing big. We mostly face man-to-man defense. Use Warriors and Heat evidence to propose one simplified action, with execution steps, failure conditions and citations. Clearly label it as a proposed adaptation.

Expected: a clearly labeled proposal matched to the supplied adult amateur roster and weekly practice constraint, grounded in WABC/NBA passages. No invented success rate.

Model: `vertex_ai/gemini-3.5-flash`. Actual elapsed time including baseline: 84.25 seconds.

<details><summary>Actual outputs — same model, side by side</summary>

<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr><td>### Proposed Adaptation: The &quot;Miami-Golden State&quot; Elbow Split<br><br>For an adult amateur team with limited practice time (one 60-minute session per week), running complex, multi-option sets is unrealistic. Instead, you need a high-yield **conceptual trigger** that requires only one basic action but naturally creates three high-percentage options based on how the man-to-man defense reacts. <br><br>This adaptation merges the **Golden State Warriors&#x27; &quot;Post-Split&quot; action** (using a playmaker to facilitate for shooters screening for one another) with the **Miami Heat&#x27;s &quot;Delay&quot; series** (utilizing a mobile, playmaking big at the top of the key to open up the paint).<br><br>---<br><br>### The Setup<br>* **Alignment:** 5-Out or High-Post 1-4.<br>* **The Hub (Player 5):** Your passing big. They start at the top of the key or the elbow.<br>* **The Shooters (Players 2 &amp; 3):** Positioned on the wings/corners.<br>* **The Ball Handler (Player 1):** Starts at the top.<br><br>```<br>       [Basket]<br>  <br>  (3)            (4)<br>  <br>     (2)      [5] &lt;--- (Passing Big at Elbow)<br>          ^<br>          | (Pass)<br>         (1) &lt;--- (Ball Handler)<br>```<br><br>---<br><br>### Execution Steps<br><br>#### Step 1: The Entry<br>Player 1 passes to the Passing Big (5) at the elbow or top of the key. 5 catches the ball facing the basket, keeping their eyes on the floor (acting as the &quot;Hub&quot;).<br><br>#### Step 2: The Split Trigger<br>Immediately after passing, Player 1 does not stand still. They sprint directly toward the nearest shooter (Player 2) on the wing and set an off-ball down-screen. <br><br>#### Step 3: The Read (The &quot;Split&quot;)<br>Player 2 (Shooter) uses Player 1&#x27;s screen. They have two options based on their defender:<br>* **Option A (Curl):** If the defender fights over the top of the screen, Player 2 curls tight around the screen toward Player 5 for a handoff or quick pass, shooting a catch-and-shoot jumper or driving.<br>* **Option B (Pop):** If the defender sags into the paint to prevent the drive, Player 2 flares out to the three-point line. Player 1 (the screener) then turns and seals their defender, or slips to the basket.<br><br>#### Step 4: The Weakside Distraction<br>To prevent weakside help from collapsing on the action, the second shooter (Player 3) and the remaining player (Player 4) exchange positions on the opposite side of the court. This keeps their defenders occupied and prevents them from helping in the paint.<br><br>---<br><br>### Failure Conditions &amp; Countermeasures<br><br>Because amateur defenders often play undisciplined man-to-man defense (over-aggressive denying, switching poorly, or grabbing), you must prepare for these three failure conditions:<br><br>#### Failure 1: The defense overplays and denies the entry pass to the Passing Big (5).<br>* **The Cheat:** The defender denies the pass to the top of the key.<br>* **The Counter:** Player 5 immediately back-cuts to the rim for a layup. If that is guarded, Player 1 dribbles toward Shooter 2 to initiate a Dribble Hand-Off (DHO) instead, bypassing the big.<br><br>#### Failure 2: The defender over-pursues (locks and trails) Shooter 2 over the screen.<br>* **The Cheat:** The defender anticipates the screen and cheats to the high side to stop the three-pointer.<br>* **The Counter (The &quot;Backcut&quot;):** Shooter 2 fake-steps toward the screen, then immediately plants their foot and cuts backdoor to the basket. Player 5 (the passing big) delivers a bounce pass for a layup. <br><br>#### Failure 3: The defense switches the screen (Player 1&#x27;s defender takes Shooter 2).<br>* **The Cheat:** Amateur teams often yell &quot;Switch!&quot; to cover up poor off-ball defense.<br>* **The Counter (The &quot;Slip&quot;):** The moment Player 1&#x27;s defender commits to switching onto Shooter 2, Player 1 abandons the screen and dives directly to the rim (&quot;slips&quot; the screen). Player 5 delivers a quick pass to Player 1 for an easy layup.<br><br>---<br><br>### Evidence and Tactical Citations<br><br>#### 1. The Golden State Warriors (The &quot;Split Action&quot;)<br>Under Steve Kerr, the Warriors popularized the &quot;post-split&quot; or &quot;elbow-split.&quot; When Draymond Green (a non-traditional, passing big) catches the ball in the post or elbow, perimeter players do not stand still. Instead, the passer immediately screens away for a shooter (often Stephen Curry or Klay Thompson). <br><br>* **Tactical Alignment:** According to basketball analyst Gibson Pyper (*Half Court Hoops*), the Warriors&#x27; split cuts exploit the natural urge of man-to-man defenders to watch the ball. By screening off the ball while the defender of the passer is relaxed, it creates defensive miscommunication, resulting in open layups or uncontested threes.<br><br>#### 2. The Miami Heat (The &quot;Delay&quot; Series)<br>Erik</td><td># High-Post Split and Handoff Adaptation for Amateur Teams<br><br>## Proposed Adaptation: High-Post Split and Handoff<br><br>**Proposed adaptation**<br><br>For an amateur team with limited practice time, we propose a simplified High-Post Split and Handoff action. The passing big sets up at the high post or elbow, while two shooters occupy the wings or corners to stretch the defense. A shooter passes to the big and immediately runs to set an off-ball screen for the second shooter. The second shooter curls tight around the screen toward the big. The big pivots to face away from the cutter, widening their stance to obstruct the defender. The big then executes a close handoff to the curling shooter. If the defender overplays or top-blocks the handoff, the cutter rejects the screen and cuts backdoor to the basket. If the defender jumps out high to stop the shooter, the big fakes the handoff and drives to the rim. [1](/evidence/wabc-l2-p281-1) [2](/evidence/wabc-l2-p282-1) [3](/evidence/wabc-l2-p303-1) [4](/evidence/gsw-g5-5) [5](/evidence/mia-nyk-3)<br><br>## Limitations of the Tactical Analysis<br><br>**Evidence limit**<br><br>This tactical brief is limited to the selected playoff games of the Golden State Warriors (2021-22) and Miami Heat (2022-23), alongside the WABC Level 2 Coaches Manual. It does not analyze full-season tracking data, other playoff series, or different defensive coverages such as zone defenses. Furthermore, the proposed adaptation is a simplified model designed for amateur personnel and has not been tested under competitive amateur league rules or conditions. [4](/evidence/gsw-g5-5) [6](/evidence/mia-g2-3) [5](/evidence/mia-nyk-3) [7](/evidence/mia-nyk-4) [8](/evidence/wabc-l2-p334-1)<br><br>## Limitations<br><br>- Limited to selected GSW 2021-22 and MIA 2022-23 playoff games.<br>- The proposed adaptation is untested in amateur league settings.<br><br><br>4 draft claim(s) withheld after citation checks.<br><br>## Sources<br><br>1. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=281) — PDF page 281<br>2. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=282) — PDF page 282<br>3. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=303) — PDF page 303<br>4. [Finals Film Study: Warriors execute on both ends of the floor in Game 5](https://www.nba.com/news/finals-film-study-game-5) — extracted passage 5<br>5. [Playoffs Film Study: Heading into Game 3, Knicks and Heat present offensive contrast](https://www.nba.com/news/knicks-heat-game-3-offensive-contrast) — extracted passage 3<br>6. [Finals Film Study: Heat catch fire with help from the Nuggets in Game 2](https://www.nba.com/news/finals-film-study-nuggets-heat-game-2) — extracted passage 3<br>7. [Playoffs Film Study: Heading into Game 3, Knicks and Heat present offensive contrast](https://www.nba.com/news/knicks-heat-game-3-offensive-contrast) — extracted passage 4<br>8. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=334) — PDF page 334</td></tr></table>

</details>

Full tool trace: `data/comparisons.json`, sample 3.
