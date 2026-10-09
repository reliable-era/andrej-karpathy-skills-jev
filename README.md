# karpathy-jev

**Checks whether a coding agent followed Karpathy's guidelines before it finishes a code change.**

The agent edits the code. A separate model, [TypeSafe Jev](https://typesafe.ai), reviews evidence from
that work. A Python router turns its answers into a request to continue or revise.

For example, an agent says “fixed, tests pass,” but its last test ran **before** its final edit.
The router can ask it to run a relevant check again before finishing.

[How it works](#how-it-works) · [Setup](#setup) · [Results](#results) · [Detailed evaluation](eval/EVALUATION.md)

## What changes when you add this skill?

| Setup | How the guidelines are applied |
|---|---|
| **Native** | The coding agent works without an added Karpathy skill. |
| **Karpathy skill** | The agent can read the guidelines and assess its own work. |
| **karpathy-jev** | The router collects evidence and asks Jev to judge specific questions. Claude Code hooks can run these checks automatically. |

The four [Karpathy guidelines](https://github.com/multica-ai/andrej-karpathy-skills) are:

1. **Think before coding:** explain consequential assumptions or ask about an unclear request.
2. **Keep it simple:** implement only what the request needs.
3. **Make surgical changes:** keep each change relevant to the request.
4. **Verify the goal:** run a relevant check after the final edit; for a bug fix, also reproduce the failure first.

The router looks for evidence of these behaviours. It cannot prove that a passing test covers every
bug or that Jev's judgment is correct.

### At a glance

<p>Native vs. the Karpathy skill vs. karpathy-jev. In group B, every check in karpathy-jev is made by Jev from observed evidence. Measured outcomes are in <a href="#results">Results</a>.</p>

<table>
<thead><tr><th>Aspect</th><th>Native<br>(no skill)</th><th>Karpathy skill<br>(prompt-only)</th><th>Ours<br>(karpathy-jev)</th></tr></thead>
<tbody>
<tr><td colspan="4"><b>A. Delivery — does the method reach the agent?</b></td></tr>
<tr><td>Guidelines are in the agent's context</td><td>❌</td><td>✅</td><td>✅</td></tr>
<tr><td>Active even if the model never opens the skill</td><td>—</td><td>❌ (Sonnet opened it 0/20)</td><td>✅ hooks (Claude Code); ⚠️ voluntary in Codex</td></tr>
<tr><td colspan="4"><b>B. Is each guideline checked?</b> (⚠️ = asked in the skill text; the agent judges itself)</td></tr>
<tr><td>1. Think before coding (unclear request)</td><td>❌</td><td>⚠️</td><td>✅ request, before the first edit ¹</td></tr>
<tr><td>2. Simplicity first</td><td>❌</td><td>⚠️</td><td>✅ the diff</td></tr>
<tr><td>3. Surgical changes (scope)</td><td>❌</td><td>⚠️</td><td>✅ each changed hunk vs. the request</td></tr>
<tr><td>4. Goal-driven (verify the result)</td><td>❌</td><td>⚠️</td><td>✅ a test after the last edit; a bug fix must fail first, then pass</td></tr>
<tr><td colspan="4"><b>C. Evidence — what the judgment is based on</b></td></tr>
<tr><td>Observed diff and real exit codes</td><td>❌</td><td>❌</td><td>✅</td></tr>
<tr><td>Detects results hidden by <code>| tail</code>, <code>; echo $?</code></td><td>❌</td><td>❌</td><td>✅</td></tr>
<tr><td colspan="4"><b>D. Cost and risk</b></td></tr>
<tr><td>External dependency</td><td>✅ none</td><td>✅ none</td><td>❌ Jev API key</td></tr>
<tr><td>Median agent time per task (Sonnet)</td><td>158 s</td><td>159 s</td><td>170 s (+8 %; Codex +45 %)</td></tr>
<tr><td>Wrong or unresolved push-backs</td><td>—</td><td>—</td><td>⚠️ 10/20 runs ended with a block still open ²</td></tr>
<tr><td>If the judge is unreachable</td><td>—</td><td>—</td><td>fails open: verdict <code>unchecked</code>, agent continues</td></tr>
</tbody>
</table>

<p>✅ yes / better · ⚠️ partial · ❌ no / worse · — not applicable.<br>
¹ Implemented, but SWE-bench never exercised it: its issues are unambiguous.<br>
² The agent argued and finished anyway, or the evidence stayed unobservable (<a href="eval/EVALUATION.md">evaluation details</a>, Table 3).</p>

## How it works

```text
Request → agent works → router collects evidence → Jev judges → continue or revise
```

| When | What happens |
|---|---|
| A request starts | Record the request and the starting Git state. |
| Before the first edit | Ask Jev whether ambiguity needs to be addressed. |
| Before a shell pipeline | Add `pipefail` so a failed check is not hidden by a successful output filter. |
| Before finishing after edits | Review simplicity, scope, final verification, and bug reproduction where applicable. |

The evidence includes the code diff, command order, recorded results, output excerpts, and relevant
user/agent messages. Jev answers narrow questions about that evidence; the router applies the
configured rules and thresholds.

- **`proceed`:** no applicable check blocks completion.
- **`revise`:** address the reported problem; the revision can be judged once more.
- **`unchecked`:** Jev was unreachable or required answers were missing or malformed.

Checks are bounded to two finishing reviews. An unavailable judge does not block the agent.
**`proceed` is permission to continue, not proof that the code is correct.**

See the [decision rules](skills/karpathy-jev/references/decisions.md) and
[router design](skills/karpathy-jev/references/design.md) for the exact questions and thresholds.

## Setup

Requires Python 3.6+ and a TypeSafe API key. Supply the key through `TYPESAFE_API_KEY` or the private
file `~/.karpathy-jev/key`. The router itself uses only the Python standard library.

### Install the skill in a project

From your target project's root, set `JEV_REPO` to the absolute path of this repository:

```bash
JEV_REPO=/absolute/path/to/andrej-karpathy-skills-jev
mkdir -p .claude/skills
cp -R "$JEV_REPO/skills/karpathy-jev" .claude/skills/
python3 .claude/skills/karpathy-jev/scripts/router.py check
```

The check prints configuration and whether a key is present; it does **not** test API connectivity.

### Claude Code: automatic checks

Merge the `hooks` object from [hooks/hooks.json](hooks/hooks.json) into your project's
`.claude/settings.json`, preserving any existing hooks. In each command, replace
`${CLAUDE_PLUGIN_ROOT}/skills/karpathy-jev/scripts/router.py` with the **absolute path** to the copied
`.claude/skills/karpathy-jev/scripts/router.py`.

Both the skill and the hooks are needed for automatic checks. Copying the skill folder alone makes
its use voluntary. Router logs are written under `~/.karpathy-jev/` by default; inspect `log.jsonl`
after a code change to confirm that the judgment hooks ran.

### Other agents: explicit calls

Run the router from the target repository, using its installed or original absolute path:

```bash
R=/absolute/path/to/skills/karpathy-jev/scripts/router.py
python3 "$R" start --request "Fix the reported bug"
python3 "$R" decide before_first_edit --said "I will reproduce the failure before editing."
python3 "$R" run -- python -m pytest path/to/test.py   # reproduce before the fix
# Make the code change.
python3 "$R" run -- python -m pytest path/to/test.py   # check after the final edit
python3 "$R" decide before_done --final "Fixed the bug; the focused test passes."
```

Use the actual request, explanation, test command, and final message. On `revise`, address the feedback
before continuing. This mode depends on the agent making the calls.

## Results

**The historical pilot reports more self-verification and higher cost. It does not establish an
improvement in task success.**

The main comparison used 20 SWE-bench Verified tasks, one attempt per method, with the same prompt
within each harness. These are results for the earlier **“fixed” version**, not a fresh score for the
current checkout. Later versions and Qwen results are in the [evaluation details](eval/EVALUATION.md).

Three terms matter:

- **Resolved:** the benchmark's hidden tests passed on the submitted patch.
- **Self-verified:** the agent reportedly ran a passing test after its last edit.
- **False “done”:** the final message claimed completion, but the task was unresolved.

### Claude Code / Sonnet 5

Hooks ran the Jev checks automatically.

| Method | Resolved | Reported false “done” | Reported self-verified | Median time/task |
|---|---:|---:|---:|---:|
| Native | 18/20 | 2 | 1/20 | 158 s |
| Karpathy skill | 19/20 | 1 | 4/20 | 159 s |
| **karpathy-jev, fixed** | **20/20** | **0** | **13/20** | **170 s** |

The Jev version recorded 62 live calls. Median time was about **8% higher** than native; total recorded
time was 18% higher and estimated CLI cost was 35% higher. These estimates exclude unknown all-in costs.

### Codex / GPT-5.5

The agent called the router voluntarily.

| Method | Resolved | Reported false “done” | Reported self-verified | Median time/task |
|---|---:|---:|---:|---:|
| Native | 16/20 | 4 | 20/20 | 110 s |
| Karpathy skill | 16/20 | 4 | 20/20 | 97 s |
| **karpathy-jev, fixed** | **17/20** | **3** | **20/20** | **160 s** |

The Jev version recorded 55 live calls. Median time was about **45% higher** than native.

### What can we conclude?

- The observed success differences are small. Paired sign tests did not establish a reliable gain;
  this sample also does not establish that the skill cannot hurt performance.
- Automatic hooks ensure the router runs even when the agent never opens the skill text. Several
  voluntary conditions recorded no router calls; reading a skill and calling Jev are separate steps.
- The same public tasks were reused during development. Later results are development evidence.
- **Audit remains incomplete:** matching historical source snapshots and manual-label calibration
  records are missing, and strict verification still needs reconciliation. The behavioural columns
  above are reported figures, not fully accepted audit findings.
- Jev thresholds are uncalibrated. These tasks barely exercise clarification of ambiguous requests.

The [evaluation details](eval/EVALUATION.md) preserve scope metrics, paired comparisons, version
history, Qwen replication, external-skill adoption, and the planned ablations.
The separate v005.1 cross-benchmark pilot is also listed there: the previous README reports all 36
attempts finished, while local accepted score/audit files contain 22. Its full totals await
reconciliation. This repository's hooked router was not run in that pilot.

## Repository map

| Path | Contents |
|---|---|
| [skills/karpathy-jev/](skills/karpathy-jev/) | Skill instructions, decision registry, and Python router |
| [hooks/hooks.json](hooks/hooks.json) | Claude Code hook definitions |
| [tests/](tests/) | Offline checks for routing, evidence, and redaction |
| [eval/](eval/) | Development fixtures, saved fixture results, and evaluation details |

The surrounding workspace stores benchmark artifacts in `../eval_min/`, including
[the historical audit](../eval_min/original_goal_report_audit.md). These files are outside this Git
repository and may be unavailable in a standalone clone.

## Sources

- [Andrej Karpathy's guidelines](https://x.com/karpathy/status/2015883857489522876), distributed in
  [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills).
- [typesafe-ai/skills](https://github.com/typesafe-ai/skills) for question design.
- [limpet](https://github.com/noplan-inc/limpet) for hook and transcript patterns.

See [LICENSE](LICENSE).
