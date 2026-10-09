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

## 2. Results

All numbers are official-harness `resolved` counts unless stated. Rows marked **(ours)** are this
repo's skill; every other row is a baseline, a prompt-only skill, or an external bundle evaluated for
comparison. Setting of every table: 20 SWE-bench Verified tasks (seed 20260925), one attempt per task
and arm, same prompt for all arms, unless the caption says otherwise. Differences of 2–3 tasks are
within run-to-run noise (Table 6). Full data: `../eval_min/` (`result.md`, `report*.md`, `scores*.csv`).

**Table 1 — Main result. SWE-bench Verified, n = 20, k = 1. Pass v2 (fixed environment).**

| Harness / model | Type | Method | Resolved | False "done"¹ | Verified² | Outside-gold files³ | Size ratio³ | Jev calls | Time / task⁴ |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Code / Sonnet 5 | baseline | Native | 18/20 | 2 | 1/20 | 0 | 1.16 | — | 158 s |
| Claude Code / Sonnet 5 | prompt-only | Karpathy skill⁵ | 19/20 | 1 | 4/20 | 1 | 1.42 | — | 159 s |
| Claude Code / Sonnet 5 | **ours, hooks** | **Karpathy-Jev** | **20/20** | **0** | **13/20** | **0** | **1.00** | 62 | 170 s |
| Codex / GPT-5.5 | baseline | Native | 16/20 | 4 | 20/20⁶ | 0 | 1.00 | — | 110 s |
| Codex / GPT-5.5 | prompt-only | Karpathy skill (read 20/20) | 16/20 | 4 | 20/20⁶ | 0 | 1.00 | — | 97 s |
| Codex / GPT-5.5 | **ours, voluntary** | **Karpathy-Jev** | **17/20** | **3** | 20/20⁶ | 0 | 1.00 | 55 | 160 s |

¹ Final message claims completion (blinded judge, hand-audited 20/20) and the task is not resolved.
² A test command with an unmasked exit 0 after the last edit (`| tail`-masked runs excluded).
³ Non-test files changed that the gold patch does not touch; changed non-test lines ÷ gold lines; medians.
⁴ Median agent wall time; ours vs native on Sonnet: +18 % total recorded time, +35 % estimated CLI cost.
⁵ The model never invoked the skill in any Sonnet run (0/20); this arm is native plus a skill listing.
⁶ Codex ran tests unpiped in every run; the verification column does not discriminate on Codex.

**Table 2 — Ablation of ours. Same setting as Table 1; the skill version changes.**

| Harness / model | Version | What changed | Resolved | False "done" | Verified | Push-backs / Jev calls | Runs ending blocked | Time / task |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Claude Code / Sonnet 5 | v1 | first version (diff baseline failed silently, masked exit codes) | 19/20 | 1 | n/a⁷ | 1 / 39 | 0 | 192 s |
| Claude Code / Sonnet 5 | **v2** | safe baseline, Py3.6, docs label, repro rule, 2 rounds | **20/20** | 0 | 13/20 | 32 / 62 | 10 | 170 s |
| Claude Code / Sonnet 5 | v3 | + pipefail hook, output-summary reading | 18/20 | 2 | **17/20** | 30 / 59 | 11 | 183 s |
| Codex / GPT-5.5 | v2 | voluntary | 17/20 | 3 | 20/20⁶ | 13 / 55 | 1 | 160 s |
| Codex / GPT-5.5 | v3 | voluntary | 14/20 | 6 | 20/20⁶ | 10 / 43 | 1 | 134 s |

⁷ v1's environment could not run `git stash` and its verification column counted masked runs; superseded.

**Table 3 — Adoption analysis of voluntary skills. Sonnet 5 and GPT-5.5; the condition changes.**
*Opened* = the model loaded the skill; *router* = runs with at least one live Jev request.

| Harness / model | Condition | Method | Opened | Router (runs) | Live Jev calls | Resolved | Time / task |
|---|---|---|---:|---:|---:|---:|---:|
| Claude Code / Sonnet 5 | as delivered | prompt-only Karpathy skill | 0/20 | — | — | 19/20 | 159 s |
| Claude Code / Sonnet 5 | as delivered | external kjg-v1 / v2 / v3 | 0 / 0 / 0 | 0 | 0 | 18 / 18 / 19 | 204–222 s |
| Claude Code / Sonnet 5 | description names the task⁸ | external kjg-v1 / v2 / v3 | 16 / 17 / 15 | 0 | 0 | 18 / 18 / 19 | 131–136 s |
| Claude Code / Sonnet 5 | router required by prompt⁹ | external kjg-v3 | 20/20 | 20/20 | 55 | 17/20 | 381 s |
| Claude Code / Sonnet 5 | as delivered | external v005 | 15/20 | 0 | 0 | 17/20 | n/a |
| Claude Code / Sonnet 5 | **hooks (ours)** | **Karpathy-Jev v2** | n/a¹⁰ | **20/20** | 62 | **20/20** | 170 s |
| Codex / GPT-5.5 | as delivered | external kjg-v1 / v2 / v3 | 3 / 6 / 20 | 0 / 1 / 0 | 0 / 1 / 0 | 16 / 16 / 15 | 170–230 s |
| Codex / GPT-5.5 | skill named in prompt⁹ | external kjg-v1 / v2 / v3 | 20 / 20 / 20 | 19 / 20 / 9 | 70 / 80 / 37 | 15 / 16 / 15 | 276–347 s |
| Codex / GPT-5.5 | as delivered | external v005 | 20/20 | 0 | 0 | 15/20 | n/a |
| Codex / GPT-5.5 | **voluntary (ours)** | **Karpathy-Jev v2** | 20/20 | 20/20 | 55 | **17/20** | 160 s |

⁸ One-line change to the skill's `description` (fair arm, same prompt). ⁹ Prompt differs from the
other arms: a separate condition, not comparable to Table 1 baselines. ¹⁰ Hooks run regardless of
whether the model opens the skill text.

**Table 4 — Replication with an open-weight model. SWE-bench Verified, Claude Code / Qwen3.8-27B-FP8, n = 20.**

| Type | Method | Resolved | Live Jev calls | Verified | Time / task (median) |
|---|---|---:|---:|---:|---:|
| baseline | Native | 17/20 | 0 | 15/20 | 1412 s |
| **ours, hooks** | **Karpathy-Jev (v3)** | 16/20 | 80 | **19/20** | 2247 s |
| baseline | Native (later pass) | 16/20 | 0 | 17/20 | n/a |
| external | v005, as delivered | 16/20 | 0 | 17/20 | +3.6 % vs native |
| external | v005.1, consultation required | 17/20 | 27 | 20/20 (audited) | +13 % vs native |

**Table 5 — Cross-benchmark pilot. Claude Code / Qwen3.8-27B-FP8; 3 tasks per benchmark per arm; raw grader pass.**
The Jev arm here is the external v005.1 bundle, not ours. 36/36 attempts finished; 22 audited.

| Benchmark | Native | Karpathy (prompt-only) | external v005.1 (Jev) |
|---|---:|---:|---:|
| SWE-bench Multilingual | 3/3 | 3/3 | 3/3 |
| SWE-bench Pro v1 | 2/3 | 1/3 | 2/3 |
| LiveCodeBench v6 | 0/3 | 0/3 | 1/3¹¹ |
| Terminal-Bench 2.0 | 2/3 | 3/3 | 3/3 |
| **All (raw)** | **7/12** | **7/12** | **9/12** |

¹¹ Passed the grader but exceeded the solve budget; counts as 0 under the primary metric (reward 1 and
normal completion), which is known only for the 22 audited attempts (9 primary of 12 raw).

**Table 6 — Paired comparisons against the same-harness native arm (Table 1 setting) and
pre-registered expectations.**

| Harness | Method vs Native | Resolved won / lost / tied | Sign-test p | False "done" better / worse / tied |
|---|---|---:|---:|---:|
| Sonnet 5 | Karpathy skill (prompt-only) | 1 / 0 / 19 | 1.00 | 1 / 0 / 19 |
| Sonnet 5 | **Karpathy-Jev (ours)** | **2 / 0 / 18** | 0.50 | **2 / 0 / 18** |
| GPT-5.5 | Karpathy skill (prompt-only) | 1 / 1 / 18 | 1.00 | 1 / 1 / 18 |
| GPT-5.5 | **Karpathy-Jev (ours)** | **3 / 2 / 15** | 1.00 | 3 / 2 / 15 |

| Expectation (pre-registered in `../goal.md`) | Verdict |
|---|---|
| E1 — no skill arm loses more than 2 tasks vs native | consistent |
| E2 — false "done" claims ordered Jev ≤ Karpathy ≤ Native | consistent (Sonnet 0 ≤ 1 ≤ 2; Codex 3 ≤ 4 ≤ 4), on automatic labels |
| E3 — both skill arms tighter in scope than native, Jev tightest | **inconsistent**: the prompt-only arm is looser than native on Sonnet (1 / 1.42 vs 0 / 1.16); ours is tightest |

### Summary of findings

1. **Task success:** no method, on any benchmark or model, changes `resolved` beyond run-to-run noise
   (Tables 1, 4, 5, 6).
2. **Behaviour:** the hook-enforced router (ours) is the only treatment that changes it: on Sonnet,
   real verification 1/20 → 13–17/20, unverified "done" claims 18 → 3–7, the tightest patches, at
   +10–20 % agent time (Tables 1, 2).
3. **Adoption:** Sonnet-class models never open a voluntary skill under a neutral prompt; a
   task-naming description makes them read it but not run its router; only an explicit instruction
   produces Jev traffic, at 2–3× the time and no gain (Table 3; root causes in
   `../eval_min/skill_loading_rootcause.md` and `router_nonadoption_rootcause.md`).
4. **Limitations:** n = 20, k = 1; the same 20 tasks reused across passes, so later passes are
   optimistic; enforced Claude and voluntary Codex differ in model and harness; Jev thresholds are
   uncalibrated; ambiguity handling is never exercised by SWE-bench; the 2026-10-04 audit found the
   manual judge-calibration records incomplete (`../eval_min/original_goal_report_audit.md`).
