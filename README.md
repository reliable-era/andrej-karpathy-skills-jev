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

Terms used in the tables (internal artifact ids in parentheses, for tracing to `../eval_min/`):
**Ours** = this repo's skill (`karpathy-jev`; *initial* = v1, *fixed* = v2, *fixed + pipefail* = v3);
**Karpathy skill** = the upstream prompt-only skill; **A, B, C** = external voluntary skills
`karpathy-jev-guidelines` v1/v2/v3 (`kjg-v1/2/3`); **D, D′** = a later external voluntary bundle and its
mandatory-consultation revision (`v005`, `v005.1`).


**Table 1 — Main result. SWE-bench Verified, n = 20, k = 1. Pass v2 (fixed environment).**

| Harness / model | Type | Method | Resolved | False "done"¹ | Verified² | Outside-gold files³ | Size ratio³ | Jev calls | Time / task⁴ |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Code / Sonnet 5 | baseline | Native | 18/20 | 2 | 1/20 | 0 | 1.16 | — | 158 s |
| Claude Code / Sonnet 5 | prompt-only | Karpathy skill⁵ | 19/20 | 1 | 4/20 | 1 | 1.42 | — | 159 s |
| Claude Code / Sonnet 5 | **ours, hooks** | **Ours (enforced by hooks)** | **20/20** | **0** | **13/20** | **0** | **1.00** | 62 | 170 s |
| Codex / GPT-5.5 | baseline | Native | 16/20 | 4 | 20/20⁶ | 0 | 1.00 | — | 110 s |
| Codex / GPT-5.5 | prompt-only | Karpathy skill (read 20/20) | 16/20 | 4 | 20/20⁶ | 0 | 1.00 | — | 97 s |
| Codex / GPT-5.5 | **ours, voluntary** | **Ours (agent calls the router)** | **17/20** | **3** | 20/20⁶ | 0 | 1.00 | 55 | 160 s |

¹ Final message claims completion (blinded judge, hand-audited 20/20) and the task is not resolved.
² A test command with an unmasked exit 0 after the last edit (`| tail`-masked runs excluded).
³ Non-test files changed that the gold patch does not touch; changed non-test lines ÷ gold lines; medians.
⁴ Median agent wall time; ours vs native on Sonnet: +18 % total recorded time, +35 % estimated CLI cost.
⁵ The model never invoked the skill in any Sonnet run (0/20); this arm is native plus a skill listing.
⁶ Codex ran tests unpiped in every run; the verification column does not discriminate on Codex.

**Table 2 — Version history of ours (not an ablation; see §Ablation design). Same setting as Table 1.**

| Harness / model | Version | What changed | Resolved | False "done" | Verified | Push-backs / Jev calls | Runs ending blocked | Time / task |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Claude Code / Sonnet 5 | ours, initial | diff baseline failed silently; exit codes masked by pipes | 19/20 | 1 | n/a⁷ | 1 / 39 | 0 | 192 s |
| Claude Code / Sonnet 5 | **ours, fixed** | safe baseline, Py3.6, docs label, reproduction rule, 2 judged rounds | **20/20** | 0 | 13/20 | 32 / 62 | 10 | 170 s |
| Claude Code / Sonnet 5 | ours, fixed + pipefail | + Bash pipefail hook, output-summary reading | 18/20 | 2 | **17/20** | 30 / 59 | 11 | 183 s |
| Codex / GPT-5.5 | ours, fixed | voluntary routing | 17/20 | 3 | 20/20⁶ | 13 / 55 | 1 | 160 s |
| Codex / GPT-5.5 | ours, fixed + pipefail | voluntary routing | 14/20 | 6 | 20/20⁶ | 10 / 43 | 1 | 134 s |

⁷ The initial version's environment could not run `git stash` and its verification column counted masked runs; superseded.

**Table 3 — Adoption analysis of voluntary skills. Sonnet 5 and GPT-5.5; the condition changes.**
*Opened* = the model loaded the skill; *router* = runs with at least one live Jev request.

| Harness / model | Condition | Method | Opened | Router (runs) | Live Jev calls | Resolved | Time / task |
|---|---|---|---:|---:|---:|---:|---:|
| Claude Code / Sonnet 5 | as delivered | prompt-only Karpathy skill | 0/20 | — | — | 19/20 | 159 s |
| Claude Code / Sonnet 5 | as delivered | external stage-router skill A / B / phase-router skill C¹² | 0 / 0 / 0 | 0 | 0 | 18 / 18 / 19 | 204–222 s |
| Claude Code / Sonnet 5 | description names the task⁸ | external A / B / C | 16 / 17 / 15 | 0 | 0 | 18 / 18 / 19 | 131–136 s |
| Claude Code / Sonnet 5 | router required by prompt⁹ | external C | 20/20 | 20/20 | 55 | 17/20 | 381 s |
| Claude Code / Sonnet 5 | as delivered | external later bundle D¹² | 15/20 | 0 | 0 | 17/20 | n/a |
| Claude Code / Sonnet 5 | **hooks (ours)** | **Ours, fixed** | n/a¹⁰ | **20/20** | 62 | **20/20** | 170 s |
| Codex / GPT-5.5 | as delivered | external A / B / C | 3 / 6 / 20 | 0 / 1 / 0 | 0 / 1 / 0 | 16 / 16 / 15 | 170–230 s |
| Codex / GPT-5.5 | skill named in prompt⁹ | external A / B / C | 20 / 20 / 20 | 19 / 20 / 9 | 70 / 80 / 37 | 15 / 16 / 15 | 276–347 s |
| Codex / GPT-5.5 | as delivered | external later bundle D | 20/20 | 0 | 0 | 15/20 | n/a |
| Codex / GPT-5.5 | **voluntary (ours)** | **Ours, fixed** | 20/20 | 20/20 | 55 | **17/20** | 160 s |

⁸ One-line change to the skill's `description` (fair arm, same prompt). ⁹ Prompt differs from the
other arms: a separate condition, not comparable to Table 1 baselines. ¹⁰ Hooks run regardless of
whether the model opens the skill text. ¹² A, B: `karpathy-jev-guidelines` v1/v2, a voluntary skill whose
router runs pre/clarify/select/post stages on an agent-written state file and rejects non-ASCII requests;
C: its v3, a phase router (think/design/criteria/diff/finish); D: a later voluntary bundle (`v005`), and
D′ its revision that makes Jev consultation mandatory before the first edit and at verification (`v005.1`).

**Table 4 — Replication with an open-weight model. SWE-bench Verified, Claude Code / Qwen3.8-27B-FP8, n = 20.**

| Type | Method | Resolved | Live Jev calls | Verified | Time / task (median) |
|---|---|---:|---:|---:|---:|
| baseline | Native | 17/20 | 0 | 15/20 | 1412 s |
| **ours, hooks** | **Ours, fixed + pipefail** | 16/20 | 80 | **19/20** | 2247 s |
| baseline | Native (later pass) | 16/20 | 0 | 17/20 | n/a |
| external | later bundle D, as delivered | 16/20 | 0 | 17/20 | +3.6 % vs native |
| external | D′, consultation mandatory | 17/20 | 27 | 20/20 (audited) | +13 % vs native |

**Table 5 — Cross-benchmark pilot. Claude Code / Qwen3.8-27B-FP8; 3 tasks per benchmark per arm; raw grader pass.**
The Jev arm here is the external bundle D′ (consultation mandatory), not ours. 36/36 attempts finished; 22 audited.

| Benchmark | Native | Karpathy (prompt-only) | external D′ (Jev) |
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
| Sonnet 5 | **Ours (enforced)** | **2 / 0 / 18** | 0.50 | **2 / 0 / 18** |
| GPT-5.5 | Karpathy skill (prompt-only) | 1 / 1 / 18 | 1.00 | 1 / 1 / 18 |
| GPT-5.5 | **Ours (voluntary)** | **3 / 2 / 15** | 1.00 | 3 / 2 / 15 |

| Expectation (pre-registered in `../goal.md`) | Verdict |
|---|---|
| E1 — no skill arm loses more than 2 tasks vs native | consistent |
| E2 — false "done" claims ordered Jev ≤ Karpathy ≤ Native | consistent (Sonnet 0 ≤ 1 ≤ 2; Codex 3 ≤ 4 ≤ 4), on automatic labels |
| E3 — both skill arms tighter in scope than native, Jev tightest | **inconsistent**: the prompt-only arm is looser than native on Sonnet (1 / 1.42 vs 0 / 1.16); ours is tightest |


### Ablation design (planned; Table 2 is a version history, not an ablation)

The full system has separable parts, and each can be removed while everything else stays fixed:

| Ablation | What is removed | What it isolates |
|---|---|---|
| no-Jev router | Jev answers replaced by a deterministic judge (constant `proceed`, and separately a rule-based judge) | Jev's own contribution vs. the hook/evidence plumbing |
| no enforcement | hooks removed; agent calls the router voluntarily | enforced vs. voluntary (the effect this repo rests on) |
| − `repro_test` / − `verification` / − `scope` / − `simplicity` / − `ambiguity` | one decision at a time | which guideline carries the behaviour change |
| − output tails / − pipefail hook / − masked-exit rule | one evidence source at a time | how much each piece of observability matters |
| 1 judged round (vs 2) | re-judging the revision | the cost/benefit of the second round |
| description fix only | router disabled, description kept | whether reading the skill text alone does anything |

Protocol that would make it rigorous, unlike the passes above: a **held-out** task set never used for
development (and ideally one that rewards the guidelines: under-specified issues, scope-bait repos);
**k ≥ 3** attempts per cell with randomized arm order; the same prompt, model, harness and container
image for every cell; paired bootstrap CIs per metric with a Holm correction across hypotheses; and the
behavioural metrics (verification, false "done", scope, Jev push-backs accepted vs. argued) reported
alongside `resolved`, since `resolved` is at ceiling for strong models on SWE-bench Verified. Power: for a
true 10-point gain in a 20-task set, k = 3 gives roughly 60 % power; 50 tasks × 3 is the minimum for the
contrasts above. None of this has been run; the tables report version history and comparison passes.

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
