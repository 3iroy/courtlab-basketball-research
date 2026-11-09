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
add any other team members before submission. A blank deploy_url means deployment is unfinished.

## Research boundaries

Selected film-study examples cannot establish season-wide tactical frequencies. Event outcomes do
not identify all screens, cuts, coverages or causes. Missing search results do not prove a tactic was
absent. No complete modern player tracking, automated film understanding, live roster updates,
or measured amateur-team outcomes are supplied. NBA examples and WABC principles require judgment
before use under another league's rules and personnel. Insufficient evidence is an acceptable result.

<!-- COMPARISONS -->
## Three sample queries: expected checks and actual comparisons

### Sample 1

在 2022 年总决赛 G4（game_id=0042100404），勇士全场投篮、三分球和失误分别是多少？结合官方 G4 解析，解释一个可核实的进攻调整，注明比赛事件不能证明的内容。

Expected: GSW G4 FG 40/91, 3PT 15/43, 16 turnovers from events/game_id=0042100404. Tactical interpretation requires gsw-g4 passages, not PBP alone.

Model: `vertex_ai/gemini-3.5-flash`. Actual elapsed time including baseline: 117.39 seconds.

<details><summary>Actual outputs — same model, side by side</summary>

<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr><td>在 2022 年 NBA 总决赛第四场（Game 4，Game ID: 0042100404）中，金州勇士队在客场以 107-97 击败了波士顿凯尔特人队，将大比分扳为 2-2 平。<br><br>以下是该场比赛中勇士队的具体数据、官方解析中的关键进攻调整，以及数据和事件本身无法证明的局限性。<br><br>---<br><br>### 一、 勇士队全场</td><td># 2022年总决赛G4勇士队数据及进攻调整分析简报<br><br>## 勇士队在2022年总决赛G4的投篮与失误数据<br><br>**Evidence / 证据**<br><br>在2022年总决赛G4（game_id=0042100404）中，金州勇士队全场投篮为91投40中（40/91），三分球为43投15中（15/43），全队共出现了16次失误。 [1](/evidence/summary-0042100404-GSW-0)<br><br>## 战术分析与数据获取的局限性<br><br>**Limit / 边界**<br><br>由于未检索到官方解析文档（gsw-g4）的完整内容（如第4段及之后的内容），无法全面获取和分析勇士队在G4中做出的其他系统性进攻战术调整（如具体的挡拆变化或空间拉开策略）。 [2](/evidence/gsw-g4-1) [3](/evidence/gsw-g4-2) [4](/evidence/gsw-g4-3)<br><br>## Limitations / 数据边界<br><br>- 本分析仅基于2022年总决赛G4的特定片段数据，无法代表整个系列赛或勇士队在其他季后赛场次中的整体战术表现。<br>- 由于缺乏完整的官方解析文本，无法对勇士队在G4中的所有进攻调整进行详尽的系统性梳理。<br><br>## Sources / 来源<br><br>1. [GSW game 0042100404, period all: event summary](https://www.nba.com/game/0042100404/play-by-play) — game_id=0042100404, team=GSW, period=0<br>2. [Finals Film Study: How Warriors won Game 4 to even the series](https://www.nba.com/news/2022-finals-film-study-game-4) — extracted passage 1<br>3. [Finals Film Study: How Warriors won Game 4 to even the series](https://www.nba.com/news/2022-finals-film-study-game-4) — extracted passage 2<br>4. [Finals Film Study: How Warriors won Game 4 to even the series](https://www.nba.com/news/2022-finals-film-study-game-4) — extracted passage 3</td></tr></table>

</details>

Full tool trace: `data/comparisons.json`, sample 1.

### Sample 2

根据 2023 年热火对尼克斯的官方比赛解析，尼克斯 top-block 射手时，热火有哪些反跑和假手递手应对？用资料中的具体案例解释，不推断赛季使用频率。

Expected: Heat–Knicks case evidence about top-blocking, backdoor cuts, Love shooting and Adebayo fake-handoff options in mia-nyk passages. No season-wide frequency claim.

Model: `vertex_ai/gemini-3.5-flash`. Actual elapsed time including baseline: 99.4 seconds.

<details><summary>Actual outputs — same model, side by side</summary>

<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr><td>在2023年季后赛东部半决赛迈阿密热火对阵纽约尼克斯的系列赛中，尼克斯主帅锡伯杜针对热火的外线射手（如麦克斯·斯特鲁斯、邓肯·罗宾逊）采取了极其激进的**“上线阻绝”（Top-locking/Top-blocking）**防守策略——防守者不走掩护下方，而是直接站在射手与三分线之间，切断射手借助无球掩护或手递手（DHO）接球兜出投三分的路线。<br><br>根据联盟及热火官方的季后赛战术解析（如 Heat.com 的 Couper Moorhead 战术复盘及 NBA 官网 Film Session），热火主帅斯波尔斯特拉针对这一防守，利用以下具体的**反跑（Backcuts）**和**假手递手（Fake Hand-offs / Keeper）**进行了高效拆解。以下为战术解析中的具体案例：<br><br>---<br><br>### 一、 反跑应对（Backcuts / Backdoor Cuts）<br><br>当尼克斯防守者（如昆汀·格莱姆斯、约什·哈特）全力封锁射手向上线移动的路线时，他们的身体重心会完全偏向外线。热火射手利用这一重心偏置，直接反方向空切篮下。<br><br>#### 【具体案例 1：邓肯·罗宾逊的反跑（第三场/第四场）】<br>*   **战术落位与防守态势**：巴姆·阿德巴约在肘区（Elbow）持球，邓肯·罗宾逊从底角借助无球掩护准备向上线移动接球。防守罗宾逊的昆汀·格莱姆斯（Quentin Grimes）采用“Top-lock”站位，整个人卡在罗宾逊与三分线之间，完全背对篮圈，张开双臂阻绝接球。<br>*   **热火的应对行动**：罗宾逊并没有强行挤过掩护去接球，而是**顺应防守者的防守惯性，突然一个顿步，直接转朝底线和篮筐方向反跑（Backcut）**。<br>*   **传球与终结**：由于格莱姆斯防得太靠上，身后留下了巨大的空档。阿德巴约心领神会，利用高位策应能力，送出一记精准的击地传球，穿过防守，罗宾逊轻松完成空切上篮。<br><br>#### 【具体案例 2：麦克斯·斯特鲁斯的无球反跑（第一场）】<br>*   **战术落位与防守态势**：斯特鲁斯在侧翼，尼克斯防守者RJ·巴雷特（RJ Barrett）对其进行贴身“Top-lock”防守，试图断绝其与弧顶持球人（吉米·巴特勒）的传球路线。<br>*   **热火的应对行动**：斯特鲁斯做了一个虚晃向上线要球的假动作，引诱巴雷特重心进一步上提，随即**迅速向底线反跑**。巴特勒在高位直接将球吊向篮下，斯特鲁斯在防守人身后接球，并在尼克斯内线封盖不及前完成上篮或分球。<br><br>---<br><br>### 二、 假手递手应对（Fake Hand-offs / &quot;Keeper&quot; Plays）<br><br>由于尼克斯的防守者在防范手递手配合（DHO）时，往往会极其激进地挤过掩护或直接扑向射手（防守人会“跳”向手递手的交接点），这导致持球的内线球员（主要是阿德巴约）身前出现巨大的突击通道。<br><br>#### 【具体案例 1：阿德巴约的假手递手自留突破（第三场）】<br>*   **战术落位与防守态势**：阿德巴约在弧顶运球，麦克斯·斯特鲁斯从侧翼跑向阿德巴约，准备进行标准的手递手配合。防守斯特鲁斯的约什·哈特（Josh Hart）为了防止斯特鲁斯借掩护投三分，疯狂地向球的方向“扑”（Hard hedge/Top-block），试图切断两人的交接路线。<br>*   **热火的应对行动**：阿德巴约和斯特鲁斯上演了一出默契的“戏耍”。斯特鲁斯快速跑过阿德巴约身边，做出接球的假动作，吸引了哈特的防守注意力。**阿德巴约则做出了一个极其逼真的手递手假动作（Fake DHO），实际上将球扣在自己腰间（Keeper）**。<br>*   **传球与终结**：哈特被斯特鲁斯带走，而防守阿德巴约的尼克斯中锋米切尔·罗宾逊（Mitchell Robinson）因为要兼顾防范斯特鲁斯接球后的投篮，站位偏向外侧。阿德</td><td># 2023年热火对阵尼克斯季后赛反跑与假手递手应对策略研究简报<br><br>## 麦克斯·斯特鲁斯的后门反跑应对<br><br>**Evidence / 证据**<br><br>在2023年季后赛热火对阵尼克斯的第二场比赛（Game 2）第三节的第一次进攻中，尼克斯对热火射手进行 top-block（阻绝防守以阻止其绕过下掩护）。热火的第一个应对策略是后门反跑，麦克斯·斯特鲁斯（Max Strus）直接切入后门，在第三节11:43接阿德巴约（Bam Adebayo）助攻完成3英尺切入上篮得分。 [1](/evidence/mia-nyk-3) [2](/evidence/event-0042200202-344)<br><br>## 角色反转与掩护人外弹应对<br><br>**Evidence / 证据**<br><br>为了防范热火的后门切入，掩护人的防守者通常会选择在内线收缩。在第二场比赛第二节的最后一次进攻中，杰伦·布伦森（Jalen Brunson）对斯特鲁斯进行 top-block，而凯文·乐福（Kevin Love）的防守者乔什·哈特（Josh Hart）为了防止斯特鲁斯切后门而选择收缩。热火随即进行“角色反转”，由原本的射手斯特鲁斯担任掩护人，而让具有投篮能力的乐福外弹出三分线。在第二节0:06，乐福接阿德巴约助攻外弹命中25英尺空位三分。 [1](/evidence/mia-nyk-3) [3](/evidence/event-0042200202-331)<br><br>## 阿德巴约的假手递手应对<br><br>**Evidence / 证据**<br><br>在斯特鲁斯反跑切后门之后的几个回合中，热火利用防守者对射手接球投三分的警惕进行了假手递手应对。当时布伦森在后面追防未触球的射手，而米切尔·罗宾逊（Mitchell Robinson）扑得太高以防范三分球，阿德巴约虚晃手递手后直接突破，在第三节9:35完成扣篮得分。 [1](/evidence/mia-nyk-3) [4](/evidence/event-0042200202-362)<br><br>## 斯特鲁斯拒绝掩护直接突袭<br><br>**Evidence / 证据**<br><br>在阿德巴约假手递手扣篮的紧接着下一个回合中，热火采用了拒绝掩护的应对策略。斯特鲁斯直接拒绝掩护，在两名防守队员反应过来并恢复防守位置之前直插篮下，在第三节9:06完成1英尺突破上篮得分。 [1](/evidence/mia-nyk-3) [5](/evidence/event-0042200202-365)<br><br>## Limitations / 数据边界<br><br>- 本分析仅基于2023年季后赛热火对阵尼克斯第二场比赛（Game 2）的特定案例，无法推断这些战术在整个系列赛或赛季中的具体使用频率。<br>- 官方解析未指明阿德巴约假手递手扣篮回合中，具体是哪位热火射手充当了无球跑动吸引防守的诱饵。<br><br>## Sources / 来源<br><br>1. [Playoffs Film Study: Heading into Game 3, Knicks and Heat present offensive contrast](https://www.nba.com/news/knicks-heat-game-3-offensive-contrast) — extracted passage 3<br>2. [0042200202, Q3 11:43, event 344](https://www.nba.com/game/0042200202/play-by-play) — game_id=0042200202, event_id=344<br>3. [0042200202, Q2 0:06, event 331](https://www.nba.com/game/0042200202/play-by-play) — game_id=0042200202, event_id=331<br>4. [0042200202, Q3 9:35, event 362](https://www.nba.com/game/0042200202/play-by-play) — game_id=0042200202, event_id=362<br>5. [0042200202, Q3 9:06, event 365](https://www.nba.com/game/0042200202/play-by-play) — game_id=0042200202, event_id=365</td></tr></table>

</details>

Full tool trace: `data/comparisons.json`, sample 2.

### Sample 3

我们是成年业余五人制球队，每周训练一次 60 分钟，没有高大中锋，有两个稳定空位投手和一个能传球的内线，主要面对人盯人。结合勇士和热火资料，提出一个可以先练的简化配合，明确标为改编建议，给执行步骤、失败条件和来源。

Expected: a clearly labeled proposal matched to the supplied adult amateur roster and weekly practice constraint, grounded in WABC/NBA passages. No invented success rate.

Model: `vertex_ai/gemini-3.5-flash`. Actual elapsed time including baseline: 138.32 seconds.

<details><summary>Actual outputs — same model, side by side</summary>

<table><tr><th>No tools / no system prompt</th><th>CourtLab</th></tr><tr><td>针对你们“每周60分钟训练、无高大中锋、有传球内线和双投手、面对人盯人”的特点，最适合你们的是融合了**勇士队“高位策应分流（Post Split）”**与**热火队“高位手递手/延迟进攻（Delay Series）”**的简化版战术。<br><br>这套配合不需要身体对抗优势，完全利用空间、传球视眼和投篮威慑力来撕开人盯人防守。<br><br>以下是专为你们定制的简化配合方案：<br><br>---<br><br>### 🏆 改编建议：高位“引力”手递手与反切 (Elbow Delay &amp; Split)<br><br>**核心逻辑：** 避开篮下肉搏，将对方防守人拉出禁区。利用能传球的内线做轴，两位投手做交叉掩护，创造空位三分或空切上篮机会。<br><br>#### 📋 场上初始站位 (1-4 站位)<br>*   **4号位/5号位（传球内线）**：站在罚球线右侧肘区（Elbow）。<br>*   **1号位（控卫）**：弧顶持球。<br>*   **2号位（投手A）**：右侧翼（Wing）或底角。<br>*   **3号位（投手B）**：左侧翼或底角（拉开空间）。<br>*   **其他球员**：弱侧（左侧）底角拉开，带走防守人。<br><br>---<br><br>### 🔄 执行步骤（只需3步，极易上手）<br><br>```<br>      [ 篮 筐 ]<br>    3           <br>              5 (内线持球)<br>              ↑ (传球)<br>1 (持球) ───→ 1 (传球后跑向2)<br>              ↓ (掩护)<br>            2 (投手A，借掩护切出或反切)<br>```<br><br>##### 第一步：落位与喂球<br>*   1号位在弧顶将球传给站在罚球线肘区的传球内线（5号位）。<br>*   5号位接球后，背对篮筐（或侧身），双手持球于胸前，做好传球准备。<br><br>##### 第二步：勇士标志性“分流”掩护 (Split Screen)<br>*   传球后，1号位**绝对不能原地站立**，他必须立刻跑向右侧翼的2号位（投手A），给2号位做一个**无球下掩护（Down Screen）**（用身体挡住2号位的防守人）。<br>*   此时，2号位（投手A）借助1号位的掩护，迅速向5号位（传球内线）移动。<br><br>##### 第三步：二选一终结（热火/勇士核心读秒）<br>传球内线（5号位）观察2号位防守人的位置，进行简单判断：<br><br>*   **选择 A（手递手三分 - 热火式）：** 如果2号位的防守人被1号位挡住，2号位直接冲向5号位。5号位将球**手递手（DHO）**递给2号位，顺势用身体再做一次墙。2号位接球直接起跳投三分。<br>*   **选择 B（反切空上 - 勇士式）：** 如果2号位的防守人为了防三分，极其激进地绕过掩护去堵截2号位。2号位心领神会，**立刻反跑（Backdoor Cut）**直插篮下。5号位心领神会，一个击地传球送入禁区，2号位轻松上篮。<br><br>*注：如果1/2号位的掩护换防了，1号位（掩护者）在2号位切出后，立刻转身往篮下切（Slip），5号位也可以传给1号位上篮。*<br><br>---<br><br>### ❌ 失败条件（出现以下情况，立刻终止配合，启动备用方案）<br><br>为了避免在30秒进攻时间（或业余比赛节奏）中死磕战术，一旦出现以下三种情况，必须立即“Reset（重置）”：<br><br>1.  **传球路线被断（第一步失败）：** 对方防守极凶，5号位在罚球线根本接不到1号位的球。<br>    *   *解除条件：* 5号位立刻放弃接球，直接下顺给持球的1号位做高位挡拆（Pick &amp; Roll）。<br>2.  **掩护人被推挤死（第二步失败）：** 1号位去给2号位掩护时，两人撞在一起，或者防守人直接用小动作把掩护推开。<br>    *   *解除条件：* 5号位（传球内线）不要死等，立刻运球朝向弱侧的3号位（另一个投手B），做一次简单的手递手配合。<br>3.  **内线持球超过3秒（终结失败）：** 5号位拿球后，1、2号位跑位结束，但防守跟得很紧，没有出手机会。<br>    *   *解除条件：* 5号位直接将球传回给弧顶的1号位，5号位顺势下顺，转为最基础的局部多打少或个人单打。<br><br>---<br><br>### 📚 战术来源与灵感<br><br>1.  **金州勇士队（Golden State Warriors）- &quot;Post Split Action&quot;**：<br>    *   科尔体系的核心。当追梦格林（Draymond Green）或博古特在高位持球时</td><td># 业余五人制球队高位战术改编与研究简报<br><br>## 简化版高位手递手与反切配合<br><br>**Proposed adaptation / 改编建议**<br><br>【改编建议】针对无高大中锋、有两名投手和一名传球内线的业余队，建议采用高位手递手与反切配合。执行步骤：1. 传球内线（5号位）在高位接球作为压力释放点；2. 侧翼投手向5号位跑动，5号位背对防守者持球以身体宽度做墙；3. 若防守正常跟随，投手接手递手球直接投篮或突破；若防守者采取前顶防守（Top-blocking）阻截，投手立即反切（Backdoor Cut）直插篮下接5号位传球。失败条件：1. 5号位未用身体背对防守者，无法形成有效掩护；2. 5号位与投手没有贴身交接球，而是采用中距离短传，易被抢断；3. 投手反切时防守收缩，而进攻方未能及时通过外弹拉开空间。 [1](/evidence/wabc-l2-p281-1) [2](/evidence/wabc-l2-p282-1) [3](/evidence/wabc-l2-p284-1) [4](/evidence/wabc-l2-p289-1) [5](/evidence/mia-nyk-3)<br><br>## Limitations / 数据边界<br><br>- 由于缺乏业余球队实际防守轮转速度的数据，无法确定防守方是否会采用换防（Switching）来应对此简化配合<br>- 未获取热火队在高位策应配合中的具体跑位成功率统计<br>- 未检索到当防守方不采取标准人盯人而是混合联防时，该高位配合的具体演变方案<br>- 缺乏业余球队在每周仅60分钟训练时间下执行该配合的实际成功率统计<br><br><br>2 draft claim(s) withheld after citation checks. / 已隐藏未通过证据核查的草稿结论。<br><br>## Sources / 来源<br><br>1. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=281) — PDF page 281<br>2. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=282) — PDF page 282<br>3. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=284) — PDF page 284<br>4. [WABC Level 2 Coaches Manual](https://assets.fiba.basketball/image/upload/documents-corporate-wabc-coaching-manual-level-2-eng.pdf#page=289) — PDF page 289<br>5. [Playoffs Film Study: Heading into Game 3, Knicks and Heat present offensive contrast](https://www.nba.com/news/knicks-heat-game-3-offensive-contrast) — extracted passage 3</td></tr></table>

</details>

Full tool trace: `data/comparisons.json`, sample 3.
