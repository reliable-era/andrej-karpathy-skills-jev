# Evaluation Plan and Historical Results

## Next Evaluation: Overview

**Status: proposed, not run.** This plan expands the evaluation of this repository's `karpathy-jev`
plugin. It does not launch jobs, change frozen earlier conditions, or mark historical audits complete.

The [repository memo](../MEMO.md) records the planning, checkpoint reuse, software-hash, PR, and release
rules for this campaign.

| Question | Planned comparison |
|---|---|
| Does the skill help across agent harnesses? | Claude Code and Pi; Codex as an optional separate replication |
| Does it help across models? | A pinned Qwen deployment and a pinned DeepSeek model, used in both core harnesses |
| Does it generalize beyond repository bug fixes? | Two core benchmarks: SWE-bench Verified and Terminal-Bench 2.0 |
| Does it generalize across programming languages? | Optional third benchmark: SWE-bench Multilingual |
| Is the sample large enough to estimate an effect? | Nested 10%, 20%, and 30% samples; three fresh attempts per task and condition |

**Harness and model are separate factors.** Pi is an agent harness. DeepSeek is a model/provider in
this plan. If a particular DeepSeek-based agent CLI is intended, identify and pin it as an additional
harness before freezing the matrix.

[Harnesses and models](#harnesses-and-models) · [Benchmarks and sample sizes](#benchmarks-and-sample-sizes)
· [Run budget](#run-budget) · [Execution and reporting](#execution-and-reporting)
· [Historical results](#historical-results)

## Harnesses and Models

### Core Harnesses

| Harness | Planned Jev integration | Readiness requirement |
|---|---|---|
| **Claude Code** | The bundled plugin and hooks | Confirm first-edit and finish checks run in an isolated container |
| **Pi** | A new extension calling the same Python router | Implement and verify equivalent request, edit, command, and finish boundaries |
| **Codex, optional** | Explicit router calls, or a separately validated adapter | Report voluntary use separately; do not equate it with enforced checks |

Pi supports lifecycle and tool extensions; its documented `agent_before_settle` event is an actionable
finish boundary. This is an integration candidate, **not an implemented adapter**. Validate continuation
limits and tool ordering against the pinned Pi version before using it in scored runs.
See [Pi's extension documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md).

### Model Backends

| Backend | Purpose | What to freeze |
|---|---|---|
| **Qwen** | Continue the open-weight model comparison | Exact weights/revision, quantization, serving image, context limit, decoding settings, and capacity |
| **DeepSeek** | Add a second model family | Exact API model ID, returned model/version, reasoning mode, context limit, decoding settings, and API compatibility |

DeepSeek publishes model APIs; select an available model at launch rather than assuming a historical
alias is immutable. Record any provider-side version uncertainty. See the
[DeepSeek API documentation](https://api-docs.deepseek.com/api/create-response/).

The intended core matrix is **2 harnesses × 2 model backends**. Every cell must pass a tool-call,
streaming, transcript, and budget smoke test. Any compatibility bridge must have its source hash and
argument/tool mapping recorded. An unsupported cell remains explicitly unrun; do not silently replace
its model. Use the same backend and inference settings across harnesses when estimating a harness
effect, and the same harness when estimating a model effect.

## Benchmarks and Sample Sizes

Use **two benchmarks by default**, with a third only if the language-generalization question and budget
justify it. Decide whether to include the third before examining scored outcomes.

| Benchmark | Role | Published release size | 10% | 20% | 30% |
|---|---|---:|---:|---:|---:|
| **SWE-bench Verified** | Core: real repository bug fixes | 500 | 50 | 100 | 150 |
| **Terminal-Bench 2.0** | Core: terminal workflows and tool use | 89 | 9 | 18 | 27 |
| **SWE-bench Multilingual** | Optional: repository fixes across languages | 300 | 30 | 60 | 90 |
| **Two core benchmarks: distinct tasks** | | **589** | **59** | **118** | **177** |
| **All three: distinct tasks** | | **889** | **89** | **178** | **267** |

The SWE-bench counts are listed by the [benchmark maintainers](https://www.swebench.com/).
Terminal-Bench 2.0's 89-task release is described in its
[benchmark paper](https://arxiv.org/abs/2601.11868). Reconfirm the exact release manifests at freeze;
if the chosen release changes, recompute the table before any scored run.

### Sampling Rule

```text
N = number of tasks in the pinned benchmark release
n10 = ceil(0.10 × N)
n20 = ceil(0.20 × N)
n30 = ceil(0.30 × N)

Freeze one ordered sample of n30 distinct eligible tasks.
The first n10 tasks are the 10% checkpoint.
The first n20 tasks are the 20% checkpoint.
All n30 tasks are the final 30% sample.
```

1. Build an exclusion list of every task used for previous development, scored runs, smoke checks,
   fixture design, or adapter debugging. Exclude these IDs from the new sample. Record the release
   size, excluded IDs, and eligible size; percentages above use the **full release size**.
2. Require enough eligible tasks for the 30% sample. If there are too few, revise the release/sample
   plan before scoring and disclose the change; do not reintroduce exposed tasks silently.
3. Use seed `20261009`. Allocate SWE-bench Verified tasks proportionally by repository; allocate
   Multilingual tasks by language and then repository. For Terminal-Bench, use published task
   categories where available. Freeze rounding, small-stratum handling, and the final task order.
4. Freeze all three nested checkpoint memberships at once. Balance the early prefixes across the
   same strata, and verify their actual composition rather than calling an arbitrary prefix stratified.
5. Use identical task IDs across methods and compatible harness/model cells. Keep adapter smoke
   tasks outside every scored subset.

The final target is **30% per selected benchmark**. The 10% and 20% checkpoints are cumulative progress
reports. Do not choose the stopping fraction after seeing which checkpoint looks best. If the run stops
early for resource reasons, report the achieved fraction and missing cells as an incomplete campaign.
Previously completed attempts are not rerun when extending a checkpoint.

Reuse each accepted task/method/harness/model/repeat attempt only when its frozen condition and
artifact hashes match. The 20% checkpoint adds only tasks outside the 10% subset; the 30% checkpoint
adds only tasks outside the 20% subset. A changed software or grading condition gets a new name and
cannot inherit earlier scores as if they were generated under it.

### Software Identity for Every Harness and Tool

Record the full source Git commit SHA when available **and** a SHA256 of the executable or installed
package actually used. Include reported versions, runtime and lockfile identities, adapter/tool hashes,
container image digests, and the hashing method for multi-file packages. A symlink or launcher hash
alone does not identify the underlying software.

```json
{
  "component": "harness-or-tool-name",
  "reported_version": "record-at-freeze",
  "source_commit_sha": null,
  "source_commit_unavailable_reason": "record-if-not-exposed",
  "artifact_sha256": "compute-from-the-executed-artifact",
  "artifact_scope": "record-file-or-package-and-hashing-method",
  "runtime_version": "record-at-freeze",
  "container_image_digest": null
}
```

This is a record template, not a completed receipt. Resolve placeholders before launch. Unavailable
source commits must be explained; installed artifact hashes remain required. Verify software identity
at launch and collection, and before reusing checkpoint results. Provider-hosted model identity is
recorded separately because client software hashes cannot pin remote weights.

## Methods and Repeated Attempts

### Main Comparison

| Method | Added configuration |
|---|---|
| **Native** | No added Karpathy skill or Jev judgment |
| **Original Karpathy** | A frozen copy of the original skill; no Jev judgment |
| **karpathy-jev** | A frozen copy of this repository's skill, router, and validated harness adapter |

Freeze the source commit and folder hashes for all added skills. The new Jev condition evaluates this
repository's plugin; the separate v005/v005.1 bundles remain historical external conditions.

Use the same user prompt, task image, resources, network policy, benchmark solve budget, and passive
evidence collection within each comparison. Keep harness-native system prompts and tools recorded;
they are part of the harness treatment. Extra skills and provider-specific instructions must be
declared. Only the Jev method receives its authorized judge credential.

Run **k = 3 independent fresh attempts** per task, method, and harness/model cell. Freeze repeat seeds
where supported and record when the provider cannot honor them. Randomize method order within each
task/repeat block and interleave harness/model blocks to reduce timing and queue effects.

These are three scheduled attempts, not retries until a task passes. Report average per-attempt
success; best-of-three is a separate diagnostic and must not replace it.

### Focused Ablations

After the main adapter smoke tests, preregister a separate ablation manifest and budget:

- **Deterministic router:** same hooks and evidence, with constant `proceed` and a separate rule-based
  judge, to measure what the evidence machinery contributes without Jev.
- **Voluntary Jev:** same skill/model/harness, with automatic invocation removed, to measure adoption.
- **Decision removal:** omit one of ambiguity, simplicity, scope, verification, or reproduction.
- **Evidence removal:** omit output tails, pipeline handling, or masked-exit handling.
- **One finish review:** compare with the current limit of two.

Declare the subset, repeats, and hypotheses before viewing relevant rewards. These extra conditions
are not included in the main run counts below. Clarification needs a separate small diagnostic suite
of ambiguous requests; it is not a fourth benchmark or part of the published benchmark score.

## Run Budget

For the full core matrix, there are four compatible harness/model cells:

```text
main attempts = sampled tasks × 4 cells × 3 methods × 3 repeats
              = sampled tasks × 36
```

| Cumulative checkpoint | Two core benchmarks | With optional third benchmark |
|---|---:|---:|
| 10% | 2,124 attempts | 3,204 attempts |
| 20% | 4,248 attempts | 6,408 attempts |
| 30% | 6,372 attempts | 9,612 attempts |

These totals are cumulative, not additive. They exclude smoke tests, ablations, optional Codex cells,
and diagnostic grading. Recompute the totals for the actual compatible matrix before launch.

Measure smoke-run setup, solve, queue, grading, token usage, and judge calls to estimate the campaign
cost. Freeze CPU/RAM/GPU assignments, per-endpoint concurrency, and queue policy. Queue time stays
outside the solve budget but remains part of end-to-end time. Count failed attempts and all diagnostic
overhead; API billing and local GPU costs are different categories. A larger sample does not by itself
guarantee statistical power; preregister a minimum effect and power calculation for the chosen matrix.

## Execution and Reporting

### Before Scoring

1. Pin dataset revisions, grader versions, image digests, model identities, harness/adapter sources,
   skills, prompts, sample memberships, repeat order, solve budgets, and analysis code in a new manifest.
2. In isolated containers, verify skill separation, real judge calls, edit/finish boundaries, pipeline
   exit capture, revision limits, unavailable-judge handling, and the full final diff including staged
   and untracked changes. Run positive and negative grader controls on unscored smoke tasks.
3. Keep judge calibration separate from scoring. Freeze its rubric, manual per-ID labels, response
   model, and acceptance criterion before inspecting calibration predictions. Missing records are
   not counted as successful calibration. Freeze thresholds after this gate.
4. Label completion claims using messages with task/arm/reward mappings hidden. Freeze human
   calibration receipts and final labels before reward review; disclose any prior identity exposure.

### Metrics

| Metric | Reported definition |
|---|---|
| **Primary task success** | Grader pass **and** normal agent completion within the solve budget |
| **Raw grader pass** | Hidden grader pass, including passing patches from timed-out or errored agents |
| **False done** | Completion claim on a primary-unsuccessful attempt; also report the raw-grader definition separately |
| **Strict self-verification** | A relevant behavioral check after the final repository mutation, with an observed unmasked exit 0 |
| **Adoption** | Skill opened, router invoked, live Jev reply received, and revision acted on: separate fields |
| **Scope** | Files outside the gold production patch and changed-line ratio where gold patches exist |
| **Efficiency** | Setup/queue/solve/grading/end-to-end time; logical token categories; model/Jev costs where measured |
| **Failures and retrieval** | Timeouts, process/provider/grader errors, upstream-fix retrieval, and incomplete evidence |

Mark scope metrics unavailable for tasks without gold patches. Compile/build success, a test output
summary, and hidden grader success do not establish strict agent self-verification. Keep all scheduled
attempts in the denominator; mark genuinely unlaunched slots pending. Freeze technical-restart rules
before launch and preserve every interrupted attempt and its costs. No quality retries.

Network access can expose future upstream fixes. Use the same predeclared network policy within a
comparison, record observed retrieval, and report a sensitivity analysis alongside the original scores;
do not delete unfavorable or retrieved solutions after scoring. Excluding development tasks reduces
local exposure but does not prove that public benchmark tasks were absent from model training.

### Analysis and Deliverables

- Report each benchmark × harness × model × method separately, including all three repeats. Do not
  pool enforced and voluntary use. Any aggregate must state its weighting.
- Report paired task-level success differences and 95% confidence intervals, resampling **task
  clusters** while retaining their repeated attempts and paired methods. Repeats are not new tasks.
- Preregister the primary comparisons and multiplicity correction. Treat checkpoint results as
  descriptive; confirmatory analysis uses the fixed final sample and cannot select the best checkpoint.
- Report verification, claims, adoption, scope, interventions, retrieval, failure types, and time/cost
  alongside success. Include worked examples of improvements, regressions, and incorrect push-backs.
- Preserve manifests, source snapshots, complete tool transcripts, final patches, judge requests and
  responses, raw grading logs, actual exit receipts, blinded labels, audit rows, and reproducible reports.
  Scan exported artifacts for configured secrets and archive only sanitized evidence.
- Finish with an explicit completeness table and owned-resource cleanup receipts. Do not restart or
  repurpose existing benchmark/model services as part of this planning change.

## Historical Results

These tables preserve the figures reported for earlier development runs. They cover several skill
versions, models, and installation methods; they are not a fresh evaluation of the current checkout.
Start with the [README](../README.md) for the purpose, usage, and main comparison.

## How to read the tables

- **Native:** the coding agent with no added Karpathy skill.
- **Karpathy skill:** the original guidelines supplied as skill text.
- **Ours:** this repository's router and hooks, at the version named in each row.
- **External A–C:** `karpathy-jev-guidelines` v1–v3, separate stage/phase routers.
- **External D / D′:** the separate v005 / v005.1 bundles. D′ requires Jev consultation in its
  instructions; this does not enforce a call if the agent never uses the skill.
- **Resolved:** the benchmark grader passes. **Verified:** the reported agent self-check metric.
  **False done:** a completion claim on an unresolved task.
- **Fixed:** the historical main-comparison version. **Fixed + pipefail:** a later evaluated version
  with additional shell pipeline handling. Neither label pins today's checkout.

Each SWE-bench comparison uses the same 20 tasks and one attempt per method. Tasks were reused during
development. Compare methods within the same model, harness, and condition; do not pool these rows.

The [historical audit](../../eval_min/original_goal_report_audit.md) records missing matching source
snapshots and manual-label provenance, plus unfinished strict-verification reconciliation. Reported
behavioural figures below retain that uncertainty. The cross-benchmark full totals also await
reconciliation with the local 22-row audited checkpoint.

## Historical main comparison

<p><b>Table 1 — SWE-bench Verified, 20 tasks, one attempt each, same prompt for every arm.</b> Rows in bold are ours.</p>

<table>
<thead>
<tr><th rowspan="2">Harness / model</th><th rowspan="2">Method</th><th colspan="2">Outcome</th><th rowspan="2">Verified<br>after last edit<sup>b</sup></th><th colspan="2">Scope (median)<sup>c</sup></th><th colspan="2">Cost</th></tr>
<tr><th>Resolved</th><th>False "done"<sup>a</sup></th><th>Files outside gold</th><th>Size ratio</th><th>Live Jev calls</th><th>Time / task<sup>d</sup></th></tr>
</thead>
<tbody>
<tr><td rowspan="3">Claude Code<br>Sonnet 5<br><i>(enforced)</i></td><td>Native</td><td>18/20</td><td>2</td><td>1/20</td><td>0</td><td>1.16</td><td>—</td><td>158 s</td></tr>
<tr><td>Karpathy skill (prompt-only)<sup>e</sup></td><td>19/20</td><td>1</td><td>4/20</td><td>1</td><td>1.42</td><td>—</td><td>159 s</td></tr>
<tr><td><b>Ours, fixed</b></td><td><b>20/20</b></td><td><b>0</b></td><td><b>13/20</b></td><td><b>0</b></td><td><b>1.00</b></td><td>62</td><td>170 s</td></tr>
<tr><td rowspan="3">Codex<br>GPT-5.5<br><i>(voluntary)</i></td><td>Native</td><td>16/20</td><td>4</td><td>20/20<sup>f</sup></td><td>0</td><td>1.00</td><td>—</td><td>110 s</td></tr>
<tr><td>Karpathy skill (prompt-only)</td><td>16/20</td><td>4</td><td>20/20<sup>f</sup></td><td>0</td><td>1.00</td><td>—</td><td>97 s</td></tr>
<tr><td><b>Ours, fixed</b></td><td><b>17/20</b></td><td><b>3</b></td><td>20/20<sup>f</sup></td><td>0</td><td>1.00</td><td>55</td><td>160 s</td></tr>
</tbody>
</table>

<details><summary>Notes to Table 1</summary>
<p><sup>a</sup> Final message claims completion and the task is not resolved. These are reported label counts; the historical audit could not recover complete manual-calibration records.
<sup>b</sup> A test command with an unmasked exit 0 after the last edit (<code>| tail</code>-masked runs excluded).
<sup>c</sup> Non-test files changed that the gold patch does not touch; changed non-test lines ÷ gold lines.
<sup>d</sup> Median agent wall time. Ours vs native on Sonnet: +18 % total recorded time, +35 % estimated CLI cost.
<sup>e</sup> The model never invoked the skill in any Sonnet run (0/20): this arm is native plus a skill listing.
<sup>f</sup> Codex ran its tests unpiped in every run; the verification column does not discriminate on Codex.</p>
</details>


## Paired comparisons and original expectations

<p><b>Table 2 — Each method vs Native on the same tasks</b> (won = it resolved a task native did not), and the expectations written down before the experiment.</p>

| Harness | Method vs Native | Resolved won / lost / tied | Sign-test p | False "done" better / worse / tied |
|---|---|---:|---:|---:|
| Sonnet 5 | Karpathy skill (prompt-only) | 1 / 0 / 19 | 1.00 | 1 / 0 / 19 |
| Sonnet 5 | **Ours (enforced)** | **2 / 0 / 18** | 0.50 | **2 / 0 / 18** |
| GPT-5.5 | Karpathy skill (prompt-only) | 1 / 1 / 18 | 1.00 | 1 / 1 / 18 |
| GPT-5.5 | **Ours (voluntary)** | **3 / 2 / 15** | 1.00 | 3 / 2 / 15 |

| Expectation (pre-registered in `../../goal.md`) | Verdict |
|---|---|
| E1 — no skill arm loses more than 2 tasks vs native | consistent |
| E2 — false "done" claims ordered Jev ≤ Karpathy ≤ Native | consistent (Sonnet 0 ≤ 1 ≤ 2; Codex 3 ≤ 4 ≤ 4), on automatic labels |
| E3 — both skill arms tighter in scope than native, Jev tightest | **inconsistent**: the prompt-only arm is looser than native on Sonnet (1 / 1.42 vs 0 / 1.16); ours is tightest |

<details>
<summary><b>More results for ours</b> — version history and a replication with an open-weight model</summary>

<p><b>Table 3 — Version history of ours</b> (how each fix changed the numbers; not an ablation). Same setting as Table 1.</p>

<table>
<thead>
<tr><th rowspan="2">Harness / model</th><th rowspan="2">Version</th><th rowspan="2">What changed</th><th colspan="2">Outcome</th><th rowspan="2">Verified</th><th colspan="2">Router activity</th><th rowspan="2">Time / task</th></tr>
<tr><th>Resolved</th><th>False "done"</th><th>Push-backs / Jev calls</th><th>Runs ending blocked</th></tr>
</thead>
<tbody>
<tr><td rowspan="3">Claude Code<br>Sonnet 5</td><td>initial</td><td>diff baseline failed silently; exit codes masked by pipes</td><td>19/20</td><td>1</td><td>n/a<sup>g</sup></td><td>1 / 39</td><td>0</td><td>192 s</td></tr>
<tr><td><b>fixed</b></td><td>safe baseline, Python 3.6, docs label, reproduction rule, two judged rounds</td><td><b>20/20</b></td><td>0</td><td>13/20</td><td>32 / 62</td><td>10</td><td>170 s</td></tr>
<tr><td>fixed + pipefail</td><td>+ Bash pipefail hook, output-summary reading</td><td>18/20</td><td>2</td><td><b>17/20</b></td><td>30 / 59</td><td>11</td><td>183 s</td></tr>
<tr><td rowspan="2">Codex<br>GPT-5.5</td><td>fixed</td><td>voluntary routing</td><td>17/20</td><td>3</td><td>20/20<sup>f</sup></td><td>13 / 55</td><td>1</td><td>160 s</td></tr>
<tr><td>fixed + pipefail</td><td>voluntary routing</td><td>14/20</td><td>6</td><td>20/20<sup>f</sup></td><td>10 / 43</td><td>1</td><td>134 s</td></tr>
</tbody>
</table>

<p><sup>g</sup> The initial version's environment could not run <code>git stash</code> and its verification column counted masked runs; superseded. <sup>f</sup> Codex ran its tests unpiped in every run, so the verification column does not discriminate on Codex.</p>

<p><b>Table 4 — Replication with Qwen3.8-27B-FP8</b> through Claude Code, same 20 tasks. Rows D/D′ are an external bundle (see the next section).</p>

| Type | Method | Resolved | Live Jev calls | Verified | Time / task (median) |
|---|---|---:|---:|---:|---:|
| baseline | Native | 17/20 | 0 | 15/20 | 1412 s |
| **ours, hooks** | **Ours, fixed + pipefail** | 16/20 | 80 | **19/20** | 2247 s |
| baseline | Native (later pass) | 16/20 | 0 | 17/20 | n/a |
| external | later bundle D, as delivered | 16/20 | 0 | 17/20 | +3.6 % vs native |
| external | D′, consultation mandatory | 17/20 | 27 | 20/20 (audited) | +13 % vs native |


</details>

<details>
<summary><b>Not this repo: why voluntary skills did nothing</b> — four external skills (A–D) and the prompt-only skill</summary>

<p>A skill can only act if the model <i>opens</i> it and then <i>calls its router</i>. We tested four external voluntary skills given to us for comparison: <b>A, B</b> = <code>karpathy-jev-guidelines</code> v1/v2 (a stage router over an agent-written state file; rejects non-ASCII requests); <b>C</b> = its v3 (a phase router); <b>D</b> = a later bundle (<code>v005</code>), <b>D′</b> = its revision that makes Jev consultation mandatory (<code>v005.1</code>). Conditions: (i) as delivered; (ii) only the skill's <code>description</code> changed to name the task<sup>h</sup>; (iii) the prompt forcing its use<sup>i</sup>.</p>

<p><b>Table 5 — Adoption of voluntary skills</b> (counts of 20 runs).</p>

<table>
<thead>
<tr><th rowspan="2">Harness / model</th><th rowspan="2">Condition</th><th rowspan="2">Method</th><th colspan="3">Adoption (of 20 runs)</th><th rowspan="2">Resolved</th><th rowspan="2">Time / task</th></tr>
<tr><th>Opened</th><th>Router</th><th>Live Jev calls</th></tr>
</thead>
<tbody>
<tr><td rowspan="10">Claude Code<br>Sonnet 5</td><td rowspan="5">as delivered</td><td>Karpathy skill (prompt-only)</td><td>0</td><td>—</td><td>—</td><td>19/20</td><td>159 s</td></tr>
<tr><td>A — external, stage router (v1)</td><td>0</td><td>0</td><td>0</td><td>18/20</td><td>204 s</td></tr>
<tr><td>B — external, stage router (v2)</td><td>0</td><td>0</td><td>0</td><td>18/20</td><td>222 s</td></tr>
<tr><td>C — external, phase router (v3)</td><td>0</td><td>0</td><td>0</td><td>19/20</td><td>219 s</td></tr>
<tr><td>D — external, later bundle</td><td>15</td><td>0</td><td>0</td><td>17/20</td><td>n/a</td></tr>
<tr><td rowspan="3">description names the task<sup>h</sup></td><td>A — external, stage router (v1)</td><td>16</td><td>0</td><td>0</td><td>18/20</td><td>136 s</td></tr>
<tr><td>B — external, stage router (v2)</td><td>17</td><td>0</td><td>0</td><td>18/20</td><td>133 s</td></tr>
<tr><td>C — external, phase router (v3)</td><td>15</td><td>0</td><td>0</td><td>19/20</td><td>131 s</td></tr>
<tr><td>router required by prompt<sup>i</sup></td><td>C — external, phase router (v3)</td><td>20</td><td>20</td><td>55</td><td>17/20</td><td>381 s</td></tr>
<tr><td><b>enforced by hooks</b></td><td><b>Ours, fixed</b></td><td>n/a<sup>j</sup></td><td><b>20</b></td><td><b>62</b></td><td><b>20/20</b></td><td>170 s</td></tr>
<tr><td rowspan="8">Codex<br>GPT-5.5</td><td rowspan="4">as delivered</td><td>A — external, stage router (v1)</td><td>3</td><td>0</td><td>0</td><td>16/20</td><td>170 s</td></tr>
<tr><td>B — external, stage router (v2)</td><td>6</td><td>1</td><td>1</td><td>16/20</td><td>181 s</td></tr>
<tr><td>C — external, phase router (v3)</td><td>20</td><td>0</td><td>0</td><td>15/20</td><td>230 s</td></tr>
<tr><td>D — external, later bundle</td><td>20</td><td>0</td><td>0</td><td>15/20</td><td>n/a</td></tr>
<tr><td rowspan="3">skill named in prompt<sup>i</sup></td><td>A — external, stage router (v1)</td><td>20</td><td>19</td><td>70</td><td>15/20</td><td>300 s</td></tr>
<tr><td>B — external, stage router (v2)</td><td>20</td><td>20</td><td>80</td><td>16/20</td><td>347 s</td></tr>
<tr><td>C — external, phase router (v3)</td><td>20</td><td>9</td><td>37</td><td>15/20</td><td>276 s</td></tr>
<tr><td><b>voluntary</b></td><td><b>Ours, fixed</b></td><td>20</td><td><b>20</b></td><td><b>55</b></td><td><b>17/20</b></td><td>160 s</td></tr>
</tbody>
</table>

<p><sup>h</sup> One-line change to the skill's <code>description</code> (a fair arm; same prompt). <sup>i</sup> The prompt differs from the other arms, so this is a separate condition, not comparable to Table 1. <sup>j</sup> Hooks run whether or not the model opens the skill text. Root causes: <code>../../eval_min/skill_loading_rootcause.md</code>, <code>../../eval_min/router_nonadoption_rootcause.md</code>.</p>

</details>

<details>
<summary><b>Not this repo: cross-benchmark pilot</b> — Terminal-Bench, SWE-bench Multilingual / Pro, LiveCodeBench (ours not run)</summary>

<p><b>Table 6 — Raw grader pass, 3 tasks per benchmark per arm, Claude Code / Qwen3.8-27B-FP8.</b> The Jev arm here is the external bundle D′. The previous README reports 36/36 attempts finished; the local accepted score/audit files contain 22 attempts. The full raw totals below are retained as reported figures, pending reconciliation and final closure.</p>

| Benchmark | Native | Karpathy (prompt-only) | external D′ (Jev) |
|---|---:|---:|---:|
| SWE-bench Multilingual | 3/3 | 3/3 | 3/3 |
| SWE-bench Pro v1 | 2/3 | 1/3 | 2/3 |
| LiveCodeBench v6 | 0/3 | 0/3 | 1/3¹¹ |
| Terminal-Bench 2.0 | 2/3 | 3/3 | 3/3 |
| **All (raw)** | **7/12** | **7/12** | **9/12** |
| Ours | not run | not run | not run |

¹¹ Passed the grader but exceeded the solve budget; counts as 0 under the primary metric (reward 1 and
normal completion), which is known only for the 22 audited attempts (9 primary of 12 raw).

</details>

<details>
<summary><b>Limitations and the planned ablation</b></summary>

**Limitations.** n = 20 tasks, one attempt each; the same 20 tasks were reused across passes, so later
passes are optimistic; enforced Claude and voluntary Codex differ in both model and harness; Jev
thresholds are uncalibrated; SWE-bench never exercises the ambiguity check; the 2026-10-04 audit found the
manual judge-calibration records incomplete (`../../eval_min/original_goal_report_audit.md`).

**Planned ablation** (not run). The full system has separable parts, and each can be removed while everything else stays fixed:

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
alongside `resolved`, since `resolved` is at ceiling for strong models on SWE-bench Verified. A prospective power analysis should set the sample size before running these contrasts. None of this has been run; the tables report version history and comparison passes.

</details>

Full data: `../../eval_min/` (`result.md`, `report*.md`, `scores*.csv`).
