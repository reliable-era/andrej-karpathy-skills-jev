# karpathy-jev

The [Karpathy coding guidelines](https://github.com/multica-ai/andrej-karpathy-skills) as a **skill bundle with
a decision router**. The agent does the work. At fixed moments in each turn, the router checks the
guidelines instead of the agent grading itself, using [TypeSafe Jev](https://docs.typesafe.ai) for the
judgments and code for everything else:

```
moment ──► 1. identify ──► 2. construct ──► Jev ──► 3. respond ──► proceed | revise
           which decisions    one request: routing   typed      gates + thresholds
           apply (code)       + branch questions,    answers    in code, one verdict
                              declared evidence only            with concrete actions
```

| Moment | Decisions | Guideline |
|---|---|---|
| `before_first_edit` | `ambiguity` | Think before coding |
| `before_done` | `simplicity` | Simplicity first |
| | `scope` (five Nouls per hunk) | Surgical changes |
| | `verification`, gated out when P(non-code task) ≥ 0.6 | Goal-driven execution |
| | `repro_test`, only when P(bug fix) ≥ 0.6 | Goal-driven execution |

## Bundle layout

```
skills/karpathy-jev/            ← the skill (copy this folder into any agent's skills directory)
  SKILL.md                      generated: what the router does, when to call it, how to respond
  decisions.jev.json            the registry: moments, routing questions, decisions, gates, thresholds, messages
  scripts/router.py             identify → construct → respond; hook entry and agent CLI
  scripts/evidence.py           observed evidence: transcripts, git diff since turn start, recorded runs
  scripts/jev_client.py         one POST to /v1/systemone; offline fake; typed readers
  scripts/build_skill.py        renders SKILL.md and references/decisions.md from the registry
  references/decisions.md       generated: every question, criterion, gate and threshold
  references/design.md          stage contracts, adding a decision, TypeSafe guidance mapping, limits
hooks/hooks.json                UserPromptSubmit / PreToolUse / Stop → router.py hook
.claude-plugin/                 plugin + marketplace manifests
eval/                           EXAMPLES.md turned into 21 labeled cases, run through the full router
tests/                          42 offline tests
```

The registry is the single source of truth. To change a question, gate, threshold or message, edit
`decisions.jev.json` and run `python3 skills/karpathy-jev/scripts/build_skill.py`. The tests fail if the
generated files are stale.

## Install

You need a TypeSafe key with Jev access (`export TYPESAFE_API_KEY=apikey_...`, or put the key in
`~/.karpathy-jev/key`) and Python 3.9+. Only the standard library is used.
To use another Jev endpoint, set `KARPATHY_JEV_API_URL` (e.g. OpenCode Zen, `https://opencode.ai/zen/v1/systemone`)
and `KARPATHY_JEV_MODEL` (Zen's free model is `jev-1.13-free`). Secret-shaped strings are masked before sending.

- **Claude Code (enforced):** install this repo as a plugin. The hooks call the router at every moment.
- **Codex:** add the `Stop` entry from `hooks/hooks.json` to `~/.codex/hooks.json`, pointing at `router.py hook`.
  The `before_done` moment works from Codex transcripts. `UserPromptSubmit` and `PreToolUse` are unverified
  on Codex.
- **Any other agent (voluntary):** copy `skills/karpathy-jev/` into its skills folder. SKILL.md tells the
  agent to call `router.py start / decide / run` at the same moments. This is weaker than hooks, because the
  agent chooses when to call.

Check the setup with `python3 skills/karpathy-jev/scripts/router.py check`. Modes: `KARPATHY_JEV_MODE=enforce`
(default), `shadow` (log only), or `off`.

## Evaluate and calibrate

```bash
python3 eval/run_eval.py --dry                      # identify + construct every case, no API call
TYPESAFE_API_KEY=... python3 eval/run_eval.py --output eval/results_<fresh-name>.jsonl  # per-decision catches and false alarms
python3 skills/karpathy-jev/scripts/router.py replay   # re-decide logged moments under edited thresholds
python3 -m pytest -q tests
```

The thresholds are starting points, fitted on nothing but the bundled fixtures. They have been exercised
in the pilot below but not calibrated on held-out tasks: label the `review` outcomes in
`~/.karpathy-jev/log.jsonl` and refit before trusting them elsewhere.

## Current conclusion: v2 evidence audit (2026-10-04)

**K-Jev shows a small observed task-success gain, at higher cost and latency; it is not yet a
proven overall winner.** The strongest recorded result is for **hook-enforced Claude routing**,
not simply installing a voluntary skill. The sample is small, the paired tests are underpowered,
and the full historical evidence audit remains incomplete.

### Recorded v2 results

Twenty SWE-bench Verified tasks, seed `20260925`, one attempt per task and arm (`k=1`). Each
harness is a **separate 60-run condition**: Claude Code with primary Sonnet 5 and enforced Jev
hooks; Codex with GPT-5.5 and voluntary router calls. Do not pool these conditions or substitute
the later 36-attempt expanded development pilot. These results describe the historical v2
condition, not an independently verified result for the current working skill version.

| Harness / arm | Resolved | Automatic false-completion claims¹ | Median outside-gold files² | Median patch-size ratio² | Mean recorded time/task | Mean CLI-estimated cost/task |
|---|---:|---:|---:|---:|---:|---:|
| Claude / native (`naive`) | 18/20 (90%) | 2 | 0 | 1.155 | 190.7 s | $0.544 |
| Claude / original Karpathy | 19/20 (95%) | 1 | 1 | 1.417 | 179.3 s | $0.590 |
| Claude / K-Jev v2 | 20/20 (100%) | 0 | 0 | 1.000 | 225.5 s | $0.733 |
| Codex / native (`naive`) | 16/20 (80%) | 4 | 0 | 1.000 | 120.2 s | Unknown |
| Codex / original Karpathy | 16/20 (80%) | 4 | 0 | 1.000 | 117.5 s | Unknown |
| Codex / K-Jev v2 | 17/20 (85%) | 3 | 0 | 1.000 | 159.2 s | Unknown |

¹ Saved automatic-label counts, **not independently accepted manual calibration**.
² Production changes compared with the gold patch; these are scope proxies, not proof that a
non-gold change is inappropriate. Cost values are CLI list-cost estimates, not invoices or all-in
Jev/infrastructure costs. Recorded run durations exclude unaccounted experiment overhead; they
must not be called full experiment wall time. Codex dollar costs are unavailable under subscription
accounting.

Compared with native, K-Jev records **two additional Claude successes (+10 percentage points)**
with **34.9% more estimated CLI cost** and **18.2% more recorded time**. Codex records **one
additional success (+5 percentage points)** with **32.5% more recorded time**. Time comparisons
use totals (equivalently means for equal-sized arms), not duration medians.

| Comparison against matched native arm | Paired success wins / losses / ties | Exact two-sided sign-test p |
|---|---:|---:|
| Claude / original Karpathy | 1 / 0 / 19 | 1.00 |
| Claude / K-Jev v2 | 2 / 0 / 18 | 0.50 |
| Codex / original Karpathy | 1 / 1 / 18 | 1.00 |
| Codex / K-Jev v2 | 3 / 2 / 15 | 1.00 |

These comparisons do **not** establish statistical significance, equivalence, or causation.

### Interpretation and limitations

- **Success (E1):** descriptively consistent with the pre-registered task-success preservation
  criterion, not a proven no-harm effect.
- **False completion (E2):** recorded automatic counts favor K-Jev, but acceptance remains
  **inconclusive** without the original manual calibration records.
- **Scope discipline (E3):** **inconsistent with the full pre-registered hypothesis** that both
  skill arms improve both scope metrics. Original Karpathy's Claude medians are worse than
  native; Codex medians tie. K-Jev's tighter Claude patch-size ratio alone does not satisfy E3.
- The original Karpathy target skill was not detected as opened in the Claude runs. That arm
  does not demonstrate guideline adoption; the Claude K-Jev result measures enforced hooks.
  Enforced Claude and voluntary Codex differ in both primary model and harness and are not
  interchangeable. This historical secondary adaptation is Codex, not agy.
- `n=20`, `k=1`, public development tasks and reuse after earlier-condition exposure limit
  generalization and causal claims. Jev thresholds are uncalibrated and ambiguity handling is
  weakly exercised. Primary-model labels do not exclude recorded ancillary model use.
- Recorded verification counts are not yet fully reconciled against complete post-final-mutation
  behavioral audits. A successful focused check or a router `proceed` is not proof of correctness.

A reviewed counterexample is **Codex/Pylint6386**: native passed all eight official tests, while
K-Jev passed seven and failed the required short-verbose test. Jev prompted a genuine failing-then-
passing reproduction, but focused local checks missed the missing verbose output. This is a
**paired loss despite a verification-workflow improvement**, not proof that Jev caused the wrong
implementation. See the [source-linked worked example](../eval_min/original_goal_examples/pylint6386_review.md).

**Evidence status:** score arithmetic, patch/prediction consistency and scope calculations have
been checked, but full raw grader/transcript/gate acceptance is unfinished. Matching historical v2
Jev/runner sources and original manual-calibration provenance remain missing. Therefore this is a
qualified retrospective summary, **not a completion certificate**. See the
[current audit report](../eval_min/original_goal_report_audit.md),
[requirement checklist](../eval_min/GOAL_SOURCE_AUDIT.md), and
[recorded scores](../eval_min/scores_v2.csv).

## Later passes and current state (as of 2026-10-09)

Everything measured after v2 points the same way as the audit above; none of it is a controlled
Jev-only effect. Reports live in `../eval_min/` (`result.md` is the consolidated table).

| Pass | Condition | Outcome |
|---|---|---|
| v3 | this bundle with pipefail hook + reproduction rule, Sonnet / Codex | 18/20, 14/20; no change in `resolved`, more real verification |
| v4 / v5 / v4d | three external voluntary skills (`karpathy-jev-guidelines` v1–v3) | as delivered: 1 Jev call in 120 runs; Sonnet never opens a voluntary skill (0/112) unless its description names the task; forced by prompt: 37–80 Jev calls per 20 runs, 2–3× time, no gain |
| v005 / v005.1 | later voluntary bundle (`andrej-karpathy-skills-jev_v005`), Sonnet / Codex / Qwen3.8-27B | v005: 17/20, 15/20, 16/20 with zero Jev calls; v005.1 (consultation required) on Qwen: 17/20 vs 16/20 historical, 27 live replies, +13 % time |
| expanded pilot | Terminal-Bench, SWE-bench Multilingual, SWE-bench Pro, LiveCodeBench; 3 tasks × 3 arms each, Qwen | all 36 attempts finished on gpu02; raw grader passes naive 7/12, karpathy 7/12, karpathy-jev 9/12; only 22/36 audited locally (9 primary / 12 raw); unfinished since 2026-10-04 |

Root causes written up: `../eval_min/skill_loading_rootcause.md` (why Sonnet-class models never open a
voluntary skill under a mild prompt; description × prompt threshold) and
`../eval_min/router_nonadoption_rootcause.md` (why an opened skill's router still does not run).

This bundle's skill is at v3.1 plus the description fix (`skills/karpathy-jev` sha256 `3bbe90eabfe29fef…`):
hooks on UserPromptSubmit, PreToolUse (edit tools and Bash, the latter prepending `set -o pipefail;`)
and Stop; two judged rounds per turn; reproduction required for bug fixes; masked exit codes read from
the runner's own summary; `.git` baseline that never writes into the repo; Python 3.6 compatible.

## Results so far (SWE-bench Verified pilot, September 2026)

The following historical summary is preserved for context. It covers additional conditions not
re-audited by the v2 review above; its behavioral and causal interpretations are not blanket
accepted findings of the current audit.

A minimal pilot, not a study: **20 SWE-bench Verified tasks, one run each**, three arms per harness
(`naive` = no skill, `karpathy` = the prompt-only guidelines, `karpathy-jev` = this bundle), on **Claude Code
with Sonnet 5** (hooks enforce the router) and **Codex with GPT-5.5** (the agent calls the router itself).
Graded with the official harness. Full reports, scores and reproduction commands are in
`../eval_min/` (`report.md`, `report_v2.md`, `report_v3.md`, `jev_proposals.md`).

Three versions of the router were measured on the same tasks:

- **v1** — as first written. The router almost never acted (2 push-backs in 76 checks): the diff baseline
  silently failed whenever the agent could not write `.git`, the router did not run on Python 3.6, the
  scope questions did not cover docs/changelog edits, and half of all "verified" test runs were
  `pytest … | tail`, whose exit code is `tail`'s.
- **v2** — those fixed, plus a `repro_test` decision that blocks a bug fix with no check observed failing
  on the unfixed code, a second judged round after a push-back, and masked exit codes recognised.
- **v3** — a PreToolUse hook that prepends `set -o pipefail;` to piped commands (Claude Code only) and
  reads the test runner's own summary when a status is masked. v3 reran only the `karpathy-jev` arm.

| Claude Code / Sonnet 5 | naive | karpathy | karpathy-jev v2 | karpathy-jev v3 |
|---|---:|---:|---:|---:|
| Resolved (of 20) | 18 | 19 | 20 | 18 |
| False "done" claims | 2 | 1 | 0 | 2 |
| Verified by a plain (unmasked) test run | 1 | 4 | 13 | 17 |
| Median size ratio vs gold / files outside gold | 1.16 / 0 | 1.42 / 1 | 1.00 / 0 | 1.00 / 0 |
| Median agent time | 158 s | 159 s | 170 s | 183 s |
| Jev push-backs / runs ending on `revise` | – | – | 32 / 10 | 30 / 11 |

| Codex / GPT-5.5 (voluntary router) | naive | karpathy | karpathy-jev v2 | karpathy-jev v3 |
|---|---:|---:|---:|---:|
| Resolved (of 20) | 16 | 16 | 17 | 14 |
| False "done" claims | 4 | 4 | 3 | 6 |
| Median agent time | 110 s | 97 s | 160 s | 134 s |
| Jev push-backs / runs ending on `revise` | – | – | 13 / 1 | 10 / 1 |

What this supports, and what it does not:

- **Task success is unchanged within noise.** Every task that flips between versions also flips between
  runs of the same version; with n = 20 and k = 1 a difference of 2–3 tasks is not a signal. Strong models
  are near ceiling on this benchmark, and the router's decisions never judge correctness against the
  hidden tests, so `resolved` was never its lever.
- **The router does change behaviour.** On Claude it now pushes back on nearly every task, and agents
  respond: verification by a real, unmasked test run went from 1/20 (naive) to 17/20, patches are the
  tightest of the three arms, and false "done" claims are lowest or tied. The cost is 10–20 % more agent
  time and, on Codex, 30–45 %.
- **Most remaining blocks are about observability, not wrongness.** Agents reproduce by printing wrong
  output, or hide a failing exit code behind `| tail`, `; echo "EXIT: $?"` or `; git stash pop`. Each
  version removed one such shape; the design keeps the bar at an observed non-zero exit rather than
  accepting narrated success.
### Three external voluntary skills (v4, v5, v4d — September 26–30, 2026)

Three separately built voluntary skills (`karpathy-jev-guidelines` v1, v2, v3: no hooks, the agent
must build a state JSON and call the bundled router) were run on the same 20 tasks, isolated and in
parallel. Full reports: `../eval_min/report_v4.md`, `report_v5.md`, `report_v4d.md`; root cause of the
adoption problem: `../eval_min/skill_loading_rootcause.md`.

| Pass | Condition | Skill opened | Live Jev calls (60 runs) | Resolved /20 (v1, v2, v3) | vs same-harness naive |
|---|---|---:|---:|---|---|
| v4 | as delivered, Sonnet 5 | 0 / 60 | 0 | 18, 18, 19 | 18 |
| v4 | as delivered, Codex | 3, 6, 20 of 20 | 1 | 16, 16, 15 | 16 |
| v5 | description names bug fixes / issue resolution, Sonnet 5 | 16, 17, 15 of 20 | 0 | 18, 18, 19 | 18 |
| v4d | prompt names the skill (separate condition), Codex | 20 / 20 each | 70, 80, 37 | 15, 16, 15 | 16 |

- As delivered, the three skills produced **one Jev call in 120 runs**: Sonnet never opened them (a
  description × prompt threshold: their descriptions do not name the task the benchmark poses; see the
  root-cause note), and Codex with v3 opened the skill every time but ran only its deterministic `finish`
  stage. Fixing the descriptions makes Sonnet *read* the skills (v5) but it still never runs their routers.
  Only an explicit instruction (v4d) produces Jev traffic, at 2.5–3× the agent time and no gain in
  `resolved`; every unresolved task in v4d was also a false "done" claim.
- Contrast: the hook-enforced router in this bundle made 55–62 Jev calls per 20 runs without the agent
  choosing to, which is the enforced-vs-voluntary difference the original question asked about.

- **Erratum (2026-09-26): on Claude Code the prompt-only skill was never loaded.** Claude Code exposed the
  `Skill` tool and listed the project skill in every run, but Sonnet 5 invoked it in 0 of 61 runs under the
  prompt "Use any available skills that are relevant". So in the Claude tables the `karpathy` arm is
  effectively `naive` plus a skill listing, and `karpathy-jev` measures the **hooks alone**: its push-backs
  are what changed the agent's behaviour, not the skill text. Codex read `SKILL.md` in 20/20 runs of both
  arms, so the Codex rows stand as labelled. The earlier "skill-loaded rate 20/20" came from matching the
  skill's name in the transcript, which the system listing satisfies; it has been re-scored.
- **Caveats.** v2 and v3 were designed after reading v1/v2 logs on these same 20 tasks, so their numbers
  are optimistic. Claude Code (enforced) and Codex (voluntary) are different harnesses and models. The
  ambiguity decision never fired: SWE-bench issues are pre-filtered to be unambiguous. A benchmark that
  rewards the guidelines (scope-bait repos, under-specified issues) is the right next measurement.

## Credits

Guidelines and examples: [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
(MIT, commit 2c60614), from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876).
Question design follows [typesafe-ai/skills](https://github.com/typesafe-ai/skills) (MIT, commit 65a39f3). Hook
and transcript patterns follow [limpet](https://github.com/noplan-inc/limpet).
