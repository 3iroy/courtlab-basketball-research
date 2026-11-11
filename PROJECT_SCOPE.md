# CourtLab — Basketball Tactics Research Agent

**Audience:** amateur players, student teams and developing coaches.

**Research question:** How can coaching principles and annotated game evidence support a practical tactical plan for a specific amateur roster?

CourtLab explains how an action works, retrieves real game examples or descriptive statistics,
and proposes an adaptation when the user supplies personnel and practice constraints.
Warriors and Heat cases remain optional examples; the project is not limited to the NBA.

## Evidence

1. FIBA/WABC Levels 1–3: substantive extracted text pages, cited by original PDF viewer page.
2. SkillCorner ACB 2025–2026: ten selected games, 4,586 model-derived action annotations across
   seven families; shots, chances and possessions are also available in the database.
3. SkillCorner season aggregates: 946 player-team-season rows across shots, drives and picks,
   covering 293 of 327 ACB games. Detailed events and season aggregates have different populations.
4. Supplemental NBA evidence: 45 Warriors/Heat playoff games, 20,372 event rows and seven official film studies.

The retrieval index has 1,437 passages, including manuals, film studies and data documentation.
Source URLs, hashes, retrieval dates and the SkillCorner commit are recorded in the manifest.
No raw tracking frames or automated video analysis are supplied by this app.

## Research workflow

- Lead clarifies vague goals or missing roster constraints, then issues 2–3 assignments in one plan.
- Researchers run in parallel in fresh contexts. They query actual documents or data tools.
- Lead requests targeted research when a material evidence gap remains: at most three planning
  rounds and seven Researchers, with per-worker exploration/tool limits and an overall timeout.
- Writer defaults to 2–3 concise sections with accurate inline citations. Proposals are labeled.
- An evidence audit withholds unsupported claims. A separate coverage review checks that requested parts survive; one bounded rewrite is allowed and remaining incomplete answers are labeled partial. Citation drawers expose the original passage,
  event or reproducible computation. Sources and tool traces are collapsed by default. Tactical answers can include an evidence-checked static half-court SVG illustration, with schematic positions and cited principles.

If the data cannot establish an answer, the report says so. Ten-game action counts cannot prove
which tactic is more effective, full team playbooks, whole-season frequency, causality or amateur win-rate benefits.

## Course requirements and verification

| Requirement | Implementation / evidence |
|---|---|
| At least three agent jobs | Lead, Researchers, Writer; additional evidence audit |
| Same-turn parallel fan-out, fresh contexts | Structured initial plan, asyncio.gather, distinct WorkerState; automated concurrency/context test |
| Gap-driven follow-up with turn cap | Bounded orchestration; automated test and real coaching run with a follow-up Researcher |
| Clarify vague input | Lead clarification with no worker dispatch; automated test |
| Access unfamiliar data through real tools | Read-only SQLite/FTS queries over pinned evidence; actual ACB comparison |
| Supported, accurately cited claims | Source registry, deterministic ID checks, audit and clickable evidence drawer |
| State data limitations | Explicit population/annotation limits; distinguish observed evidence from proposed adaptations |
| Preserve /chat shape and sub-agent attribution | response, session_id, tool_calls; every trace includes agent; API contract test |
| Customized frontend | English audience, scope, examples, concise report, source and trace views |
| No-tools comparison | README and data/acb-comparison.json; original NBA examples retained as historical runs |
| Submission configuration | submission.json uses path: research |
| Cloud Run | Existing protected CourtLab service; release status in data/deployment.json |
| GitHub continuous deployment | Developer Connect repository link and enabled `courtlab-main` push trigger in `us-east1` |

Twenty-eight automated tests pass. A real ACB run reproduced original-file counts of 1,520 picks
and 417 handoffs, and identified the top season player-team pick row as Marcelinho Huertas,
Lenovo Tenerife, 664. The no-tools model guessed ranges and alternatives. A separate browser run
combined WABC instructions with a concrete ACB off-ball screen, including clickable record evidence.

This document does not certify uniqueness against classmates' registrations. The user handles any
course list entry; final course submission and additional team-member details are outside the completed implementation.
