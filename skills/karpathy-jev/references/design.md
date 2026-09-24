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
