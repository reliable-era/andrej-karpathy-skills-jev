# karpathy-jev

## 1. Purpose, design, and how it is evaluated

### Purpose

[Andrej Karpathy's four coding guidelines](https://x.com/karpathy/status/2015883857489522876) — think
before coding, simplicity first, surgical changes, goal-driven execution — exist as a prompt-only skill
([multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)) in which the
coding agent judges its own compliance. This repo asks whether moving those judgments out of the agent
and into a **decision router backed by TypeSafe Jev** changes what the agent actually does — task
success, false "done" claims, scope discipline — and at what cost.

### Design

The agent does the work; it does not decide whether it followed the guidelines. At three fixed moments
of a turn, code identifies which decisions apply, builds **one typed Jev request from observed
evidence only**, and turns the answers into a verdict:

| Moment | Hook | Decisions routed to Jev |
|---|---|---|
| `turn_start` | UserPromptSubmit | none; records the request and a git baseline |
| `before_command` | PreToolUse (Bash) | none; prepends `set -o pipefail;` so piped checks report their own exit status |
| `before_first_edit` | PreToolUse (edit tools) | `ambiguity` |
| `before_done` | Stop | `simplicity`, `scope`, `verification`, `repro_test` |

Evidence is what the router can observe, never what the agent says: the diff since the turn started,
the commands run before the first non-test edit and after the last edit with their real exit codes and
output tails. Jev answers narrow typed questions (Noul / Choice / Score, with explicit true/false
criteria); thresholds and gates live in code; the verdict is `proceed` or `revise` with concrete
actions, and `unchecked` if Jev is unreachable (fail open, never fail silent).

What is unique about it, relative to a prompt-only skill or a voluntary skill:

- **Enforced, not voluntary.** In Claude Code the hooks run whether or not the model chooses to load
  the skill. This turned out to be decisive: Sonnet-class models never open a voluntary skill under a
  neutral prompt (0 of 112 runs), so prompt-only and voluntary skills measured as no-ops.
- **Observable compliance.** A bug fix must show a check *failing on the unfixed code* and passing
  after; a "done" claim needs a passing test after the last edit; exit codes hidden by `| tail`,
  `; echo "$?"` or `; git stash pop` are detected and recovered from the output.
- **Code decides, Jev judges.** Jev is only asked semantic questions it can answer from the evidence
  (does this hunk touch docs the request did not ask for; does this failing command reproduce the
  request); counting, thresholds, exit codes and rounds are deterministic.
- **One judged revision.** After a push-back the agent's revision is judged once more, then the turn
  ends; a false alarm costs one sentence.
- Standard library only; runs under Python 3.6+ inside benchmark containers; 70 offline tests plus a
  live fixture eval (`eval/run_eval.py`).

Install: copy `skills/karpathy-jev/` into a project's `.claude/skills/` and `hooks/hooks.json` into its
settings (Claude Code, enforced), or install the skill folder alone and call `scripts/router.py`
yourself (any agent, voluntary). Needs `TYPESAFE_API_KEY` or `~/.karpathy-jev/key`. Check with
`python3 skills/karpathy-jev/scripts/router.py check`. Current skill sha256 `3bbe90eabfe29fef…`.

### Evaluation protocol

- **Primary benchmark:** SWE-bench Verified, 20 tasks drawn with seed 20260925 stratified by
  repository, one attempt per task per arm (`k=1`), graded with the official harness. The same 20
  tasks were reused for every later pass, so later passes are development evidence, not held-out data.
- **Harnesses:** Claude Code with Sonnet 5 (hooks enforce the router) and Codex with GPT-5.5 (the agent
  calls the router itself); a Qwen3.8-27B-FP8 replication through Claude Code; and a 36-attempt pilot
  on Terminal-Bench 2.0, SWE-bench Multilingual, SWE-bench Pro and LiveCodeBench (3 tasks × 3 arms each).
- **Arms:** `naive` (no skill), `karpathy` (the prompt-only skill), `karpathy-jev` (this repo, ★
  below), plus external voluntary bundles evaluated for comparison (`karpathy-jev-guidelines` v1–v3,
  a later `v005`/`v005.1` bundle). Same prompt for every arm; skill installed per project; fresh
  container per run.
- **Metrics:** `resolved` (official harness); false "done" claim = final message claims completion
  (blinded judge, hand-audited) ∧ not resolved; verified = a test command with an unmasked exit 0 after
  the last edit; files outside the gold patch and changed-line ratio vs gold (scope); live Jev calls
  and push-backs; agent wall time. Paired won/lost/tied vs the same-harness naive arm with exact sign
  tests, which at n=20 are underpowered: differences of 2–3 tasks are run-to-run noise.

Sources: [typesafe-ai/skills](https://github.com/typesafe-ai/skills) for question design;
[limpet](https://github.com/noplan-inc/limpet) for hook and transcript patterns (both MIT).

## 2. Results by benchmark (★ = this repo's skill)

Full reports, per-run scores and audits: `../eval_min/` (`result.md`, `report*.md`, `scores*.csv`,
`original_goal_report_audit.md`).

### SWE-bench Verified, Claude Code + Sonnet 5 (20 tasks)

| Arm | Resolved | False "done" | Verified by unmasked test | Files outside gold / size ratio (med.) | Live Jev calls | Time / task |
|---|---:|---:|---:|---|---:|---:|
| naive | 18/20 | 2 | 1/20 | 0 / 1.16 | – | 158 s |
| karpathy, prompt-only (never loaded by the model) | 19/20 | 1 | 4/20 | 1 / 1.42 | – | 159 s |
| ★ **karpathy-jev, hooks (v2)** | **20/20** | **0** | 13/20 | **0 / 1.00** | 62 | 170 s |
| ★ karpathy-jev, hooks + pipefail + reproduction rule (v3) | 18/20 | 2 | **17/20** | 0 / 1.00 | 30 push-backs | 183 s |
| external kjg-v1 / v2 / v3, as delivered (never opened) | 18 / 18 / 19 | 2 / 2 / 1 | 18 / 17 / 17 | 0–1 / 1.0–1.2 | 0 | 204–222 s |
| external kjg-v1 / v2 / v3, descriptions fixed (opened, routers never run) | 18 / 18 / 19 | 2 / 2 / 1 | 17 / 16 / 15 | 0 / 1.00 | 0 | 131–136 s |
| external kjg-v3, router required by prompt (separate condition) | 17/20 | 3 | 5/20 | – | 55 | 381 s |
| external v005, as delivered | 17/20 | – | – | – | 0 | – |
| naive, fresh pass (Claude Code 2.1.283) | 18/20 | 2 | 19/20 | 0 / 1.00 | – | 186 s |
| upstream `CLAUDE.md`, prompt-only always in context | 17/20 | 3 | 16/20 | 0 / 1.00 | – | 170 s |

Paired vs naive: ★ v2 won 2 / lost 0 / tied 18 (sign p = 0.5). Pre-registered expectations: E1 (no harm)
consistent; E2 (fewer false claims: jev ≤ karpathy ≤ naive) consistent on the automatic labels;
E3 (scope lowest for jev *and* lower for both skills) **inconsistent**, because the prompt-only arm's
scope was worse than naive. ★ v2 vs naive costs +35 % estimated CLI dollars and +18 % recorded time.

### SWE-bench Verified, Codex + GPT-5.5 (20 tasks; voluntary routing only)

| Arm | Resolved | False "done" | Live Jev calls | Time / task |
|---|---:|---:|---:|---:|
| naive | 16/20 | 4 | – | 110 s |
| karpathy, prompt-only (read 20/20) | 16/20 | 4 | – | 97 s |
| ★ **karpathy-jev, voluntary (v2)** | **17/20** | **3** | 55 | 160 s |
| ★ karpathy-jev, voluntary (v3) | 14/20 | 6 | 10 push-backs | 134 s |
| external kjg-v1 / v2 / v3, as delivered | 16 / 16 / 15 | 4 / 4 / 5 | 0 / 1 / 0 | 170–230 s |
| external kjg-v1 / v2 / v3, skill named in prompt (separate condition) | 15 / 16 / 15 | 5 / 4 / 5 | 70 / 80 / 37 | 276–347 s |
| external v005, as delivered | 15/20 | – | 0 | – |

Paired vs naive: ★ v2 won 3 / lost 2 / tied 15 (p = 1.0).

### SWE-bench Verified, Claude Code + Qwen3.8-27B-FP8 (20 tasks, local endpoint)

| Arm | Resolved | Live Jev calls | Time / task (median) |
|---|---:|---:|---:|
| native | 17/20 | 0 | 1412 s |
| ★ karpathy-jev, hooks | 16/20 | 80 | 2247 s |
| native (later pass) / external v005 | 16/20 / 16/20 | 0 / 0 | – |
| external v005.1, consultation required | 17/20 | 27 | +13 % vs native |

### Terminal-Bench 2.0, SWE-bench Multilingual, SWE-bench Pro, LiveCodeBench (Qwen; 3 tasks × 3 arms per benchmark)

Pilot run 2026-10-04 on gpu02; all 36 attempts finished, 22 audited locally. The Jev arm here is the
external v005.1 bundle, **not this repo's skill**. Raw grader passes:

| Benchmark | naive | karpathy | external v005.1 (Jev) |
|---|---:|---:|---:|
| SWE-bench Multilingual | 3/3 | 3/3 | 3/3 |
| SWE-bench Pro | 2/3 | 1/3 | 2/3 |
| LiveCodeBench | 0/3 | 0/3 | 1/3 (timed out; primary 0) |
| Terminal-Bench 2.0 | 2/3 | 3/3 | 3/3 |
| **Total raw** | 7/12 | 7/12 | 9/12 |

Primary success (reward 1 *and* normal completion) is known only for the 22 audited attempts: 9 primary
of 12 raw passes. This pilot is incomplete and descriptive.

### Reading all of it

- No arm, on any benchmark, moves `resolved` beyond run-to-run noise.
- ★ The hook-enforced router is the only treatment that changed behaviour: on Sonnet, real
  verification 1/20 → 13–17/20, unverified "done" claims 18 → 3–7, tightest patches, at +10–20 % time.
- Voluntary and prompt-only skills changed nothing on Sonnet because the model never loads them
  under a neutral prompt (`../eval_min/skill_loading_rootcause.md`); when forced, they still rarely run
  their routers (`../eval_min/router_nonadoption_rootcause.md`), and forcing costs 2–3× the time.
- Limitations: n = 20, k = 1; the same tasks reused across passes; enforced Claude and voluntary Codex
  are different models and harnesses; Jev thresholds uncalibrated; ambiguity never exercised on
  SWE-bench; the 2026-10-04 audit found the manual judge-calibration records incomplete.
