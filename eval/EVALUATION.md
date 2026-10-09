# Evaluation details

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
