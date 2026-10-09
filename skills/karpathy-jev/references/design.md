# Router design

## Stage contracts

The router has three stages. Each is a plain function in `scripts/router.py` and can be tested on its own.

**1. `identify(registry, moment, evidence) -> plan`** (code only, no model call)

- Selects decisions whose `moment` matches and whose `needs` are met by the evidence. The available facts
  are `request` (a request exists), `hunks` (a diff exists), and `changed` (a diff exists, or the transcript
  shows an edit).
- Records every decision it did not select under `skipped`, with the reason.
- Collects the routing questions that the selected decisions' gates depend on.

**2. `construct(registry, plan, evidence) -> (state, questions)`** (code only)

- Builds one Jev request containing the routing questions and every selected decision's questions. Per-hunk
  and per-command templates are expanded with `{i}`.
- Question ids are namespaced (`route__task_kind`, `scope__h3__extra_lines`), so several decisions can share
  one request.
- The state contains only the paths the selected decisions declare in `evidence`. Observed facts go under
  `observed`, the agent's claims under `agent_said`.

**3. `respond(registry, plan, answers, state) -> response`** (code only)

- Applies each decision's `gate` to the routing answer, using P(option) rather than `confidence`. Closed
  gates yield `gated_out`, and their branch answers are ignored.
- Runs the decision's responder: thresholds from the registry produce `block`, `advise`, `review` or `pass`,
  with messages taken from the registry.
- Returns a single verdict: `revise` if any decision blocks, otherwise `proceed`. `route()` returns
  `unchecked` when Jev could not be reached.

`respond` depends only on `(plan, answers, state)`, all of which are logged. That is why `router.py replay`
can re-decide past moments under new thresholds without calling the API.

## Adding a decision

1. Add an entry under `decisions` in `decisions.jev.json` with these fields: `principle`, `moment`, `needs`,
   `evidence` (state paths), `questions` and/or `per_hunk_questions` / `per_command_questions`, `respond`
   messages, `thresholds`, and optionally a `gate` over a routing question.
2. Add a responder function to `RESPONDERS` in `router.py`.
3. Run `python3 scripts/build_skill.py`, then `pytest`. The tests lint every generated request against the
   API limits, check that each backticked path resolves in the state, and fail if SKILL.md is stale or a
   decision has no responder.

A new moment additionally needs a hook mapping in `hook_main` and an agent-mode branch in `agent_decide`.

## How the TypeSafe guidance is applied

| Guidance ([typesafe-ai/skills](https://github.com/typesafe-ai/skills), [docs](https://docs.typesafe.ai/llms.txt)) | Where |
|---|---|
| Code owns the workflow; the model supplies narrow judgments | All three stages are code. Jev is called once, between construct and respond. |
| Route and fill known arguments: ask branch questions up front, consume only the relevant answers | `routing` + `gate`; closed gates become `gated_out` |
| Ask independent questions over the same state together | One request per moment, with namespaced ids |
| Include only relevant context | State is assembled from each decision's declared `evidence` paths |
| Keep inferred state distinct from observed facts | `observed` (diff, commands, exit results) vs. `agent_said` |
| Noul: one per label when several may apply | Five per-hunk Nouls in `scope` |
| Confidence is not permission to act | Gates and `ambiguity` use P(option) |
| Include a no-match outcome | `task_kind` has `other` |
| Score levels describe concrete situations | `size_vs_need` levels describe how much could be removed |
| Keep policy explicit; changing a weight need not rerun inference | Thresholds in the registry; `replay` |
| For failures, inspect exact state, questions, answers | Logged per moment; `eval/run_eval.py` prints them for failed cases |

## Limits

- **Uncalibrated thresholds.** Run the eval and label the logged `review` outcomes first.
- **Independent, not smarter.** Jev is independent of the agent's reasoning, not a better coder. It catches
  scope drift and unverified "done" claims, but not a wrong fix whose test is wrong in the same way.
- **Agent mode is voluntary.** A self-misled agent may not call the router. Hooks are the enforcing path.
- **Exit codes depend on the source.** In agent mode, exit codes are only observed for commands run through
  `router.py run`. In hook mode they come from the transcript.
- **Cost grows with the diff.** Five Nouls per hunk, capped at 20 hunks. Measure latency and token cost
  before raising the cap.
- **Language.** Jev is English-first; the docs report lower accuracy for other languages.

## Method and evaluation boundary

Code owns deterministic facts such as exit status, command order, and the current patch. Jev supplies
atomic semantic judgments such as whether a hunk is relevant to the request. Questions use explicit
evidence paths; missing evidence is skipped or unchecked, never a pass. Thresholds are uncalibrated
starting points, and near-threshold answers remain review signals rather than claims of certainty. This
follows the supplied TypeSafe guidance in `jev-docs/concepts/how-to-build-with-system-one.md`,
`jev-docs/concepts/state.md`, and `jev-docs/model-jaggedness/jev-1.13.md`.

Score criteria describe broad situations. Thresholding a returned Score expectation is supported, but do
not treat it as exact arithmetic or reconstruct a precise quantity from the levels.

The bundled fixtures are for development and calibration only. A benchmark revision should use
a new pre-registered held-out manifest and output, preserve historical artifacts, and run every arm with
the same runtime, pinned model, task budget, and environment. Resolved tasks are the primary outcome;
intervention correctness, false-success prevention, verification behavior, and runtime are secondary.
Include a deterministic-router ablation to separate harness plumbing from Jev's contribution. Keep the
router interpreter compatible with the harness runtime and separate from the task environment.

## Bounded fixture validation

On 2026-09-25, the 23 development fixtures were run once with the pinned `jev-1.13.0` model. All 23
requests completed and the response reported `jev-1.13.0`; the raw output is preserved in
[`eval/results_jev_1_13_0_20260925T071057.jsonl`](../../../eval/results_jev_1_13_0_20260925T071057.jsonl).
The fixture-level expected block-label sets matched exactly for 15/23 cases. This is a calibration result,
not evidence of a SWE improvement or behavioral superiority.

The eight mismatches expose evaluation limitations. Four clean fixtures supplied only a generic `pytest -q`
command, without a test node, output, or changed-path linkage; verification therefore lacked evidence that
the command exercised the request. Four bad fixtures expected one principle, although simplicity, scope, and
verification are independent decisions and can legitimately produce multiple blocks. Future calibration
manifests should label each decision independently, include positive and negative cases with realistic command,
path, and output evidence, and report per-decision TP/FP/FN plus `review`, `advise`, `gated_out`, and
`skipped` outcomes. Overall exact-label-set matching must not be the sole metric; use a held-out manifest and
keep historical SWE results unchanged. When comparing arms within a harness, hold model, runtime, task
budget, and environment equal; this does not imply equality between Claude and Codex harnesses. A pinned
response model establishes provenance, not an improvement claim.

The fixture evidence was then tightened in a revised development manifest: clean cases use targeted test
commands with output, and bad cases label independently supported simplicity and scope violations where the
source diff contains both. The revised 23-case run matched all 23 expected label sets, with no API errors or
unchecked responses, using response model `jev-1.13.0`; its fixture SHA-256 is
`b0d085f32442d49ec294f3bcd05b8355488ad225d8df89de2fea86f3b29cd114`. The raw output is preserved in
[`eval/results_jev_1_13_0_revised_20260925T074106.jsonl`](../../../eval/results_jev_1_13_0_revised_20260925T074106.jsonl).
This supersedes neither the earlier 15/23 result nor any historical benchmark artifact: the two runs use
different development fixture versions, and neither supports a SWE performance claim.
