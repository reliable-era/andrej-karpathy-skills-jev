---
name: karpathy-jev
license: MIT
description: >
  Karpathy's coding guidelines (think before coding, simplicity first, surgical
  changes, goal-driven execution) enforced by a decision router: at fixed moments
  in a turn, code identifies which decisions apply, constructs one TypeSafe Jev
  request from observed evidence, and responds with proceed or revise. Use when
  writing, reviewing, or refactoring code, especially in long agent runs where
  self-judged "done" drifts. Hooks enforce it in Claude Code; the CLI lets any
  agent call the same router.
---

<!-- Generated from decisions.jev.json by scripts/build_skill.py. Edit the registry, then rebuild. -->

# Karpathy guidelines, routed to Jev

You do the work. You do not decide whether you followed the guidelines. At fixed moments a router does:

```
moment ──► 1. identify ──► 2. construct ──► Jev ──► 3. respond ──► proceed | revise
           which decisions    one request: routing   typed      gates + thresholds
           apply (code)       + branch questions,    answers    in code, one verdict
                              declared evidence only            with concrete actions
```

The judge sees the **request**, what you **said** to the user, and what was **observed**: the diff since
the turn began, and the commands run after your last edit with their exit results. It never sees your
reasoning, so make compliance observable. A plan you kept to yourself counts as no plan. A test that ran
before your final edit does not verify that edit.

## Moments

| Moment | When | Decisions routed | Hook |
|---|---|---|---|
| `turn_start` | A new user request arrives. | none (records the request and a git baseline) | UserPromptSubmit |
| `before_first_edit` | Before your first file edit of a turn. | `ambiguity` | PreToolUse (Edit, Write, MultiEdit, NotebookEdit, apply_patch) |
| `before_done` | When you are about to end your turn after changing files. | `simplicity`, `scope`, `verification`, `repro_test` | Stop |

| Decision | Guideline | Routed when |
|---|---|---|
| `ambiguity` | Think before coding | a request exists; always |
| `simplicity` | Simplicity first | a diff exists; always |
| `scope` | Surgical changes | a diff exists; always |
| `verification` | Goal-driven execution | any file change exists; only if P(task_kind = non_code) < 0.6 |
| `repro_test` | Goal-driven execution | a diff exists; only if P(task_kind = bug_fix) ≥ 0.6 |

Branch questions are asked speculatively in the same request as the routing question. A decision whose
gate stays closed is reported as `gated_out` and its answers are ignored.

## Responding to a decision

- **`proceed`**: continue. Outcomes of `review` are logged for calibration and need nothing from you.
- **`revise`**: each `block` names what fired and why. For each one, fix it, or if it is wrong, say why in
  one line to the user. Then continue. Each moment pushes back at most once per turn, so a false alarm
  costs one sentence. `advise` outcomes are suggestions.
- **`unchecked`**: Jev was unreachable. Nothing was judged. Do not describe the work as verified by it.

## The guidelines

**Think before coding.** Don't assume. Don't hide confusion. Surface tradeoffs. *Passes when:* Before the first edit, one or two lines name the reading you chose and what you assumed, or you ask. Unambiguous requests need nothing.

**Simplicity first.** Minimum code that solves the problem. Nothing speculative. *Passes when:* The diff contains the requested behavior and its tests, and nothing a reviewer could delete without losing something that was asked for.

**Surgical changes.** Touch only what you must. Clean up only your own mess. *Passes when:* Every changed line traces to the request. Unrelated problems you noticed are mentioned in your message, not fixed.

**Goal-driven execution.** Define success criteria. Loop until verified. *Passes when:* The last thing before you claim success is a passing run of a check that exercises the request, after your final edit. If you could not verify, say so plainly instead of claiming success.

The exact questions, criteria, thresholds and push-back messages are in
[references/decisions.md](references/decisions.md). How the router is built, and why, is in
[references/design.md](references/design.md).

## Using the router without hooks

With the plugin installed in Claude Code, hooks call the router automatically. In any other agent, call it
yourself at the same moments. This is weaker than hooks, because you choose when to call:

```bash
R=scripts/router.py                                   # relative to this skill's folder
python3 $R start --request "<the user's request>"     # turn_start: records request and git baseline
python3 $R decide before_first_edit --said "<what you told the user about your reading and assumptions>"
python3 $R run -- <test command>                      # run checks through the router so exit codes are observed
python3 $R decide before_done --final "<your final message>"
```

`decide` prints the response as JSON and exits 2 on `revise`. `identify <moment>` shows the plan and the
exact request without calling Jev. Requires `TYPESAFE_API_KEY`.

## Source

Guidelines: [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) (MIT),
from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876). Question design
follows [typesafe-ai/skills](https://github.com/typesafe-ai/skills). Thresholds are uncalibrated starting points.
