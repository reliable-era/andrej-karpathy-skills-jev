# Decisions

<!-- Generated from decisions.jev.json by scripts/build_skill.py. Edit the registry, then rebuild. -->

Every question below is sent to Jev under a namespaced id: `route__<id>` for routing questions,
`<decision>__<question>` for a decision's questions, and `<decision>__h<i>__<question>` or
`<decision>__c<i>__<question>` for per-hunk and per-command questions.

## Routing questions

- **`task_kind`** (Choice): What kind of task is `request`?
  - `bug_fix`: Something that should already work is broken.
  - `new_behavior`: Add or change a feature or behavior.
  - `refactor`: Change structure without changing behavior.
  - `non_code`: A question, explanation, documentation-only, or exploration request.
  - `other`: None of the above, or a mix.

## `ambiguity` (Think before coding)

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- **Moment:** `before_first_edit`
- **Needs:** request
- **Evidence:** `request`, `agent_said.messages_before_first_edit`

**Questions**

- **`interpretations`** (Choice): How many materially different implementations could `request` reasonably mean? *Material difference:* Two readings differ materially when they change which data is touched, what users observe, the scope of work, or its cost.
  - `one_clear`: One obvious implementation; a competent engineer would start without asking anything.
  - `minor_variants`: Only small details are open, and any sensible default would satisfy the requester.
  - `several_material`: At least two readings differ materially, and choosing wrongly would mean redoing the work.
- **`assumptions_stated`** (Noul): Do `agent_said.messages_before_first_edit` name the interpretation of `request` the agent chose, or the assumptions it is making, or ask the user to choose?
  - yes: The agent says in words which reading, scope, or assumptions it is going with, or asks. *Example shape:* I'll read 'faster' as lower latency for single queries, not throughput; I'm assuming the index is the bottleneck.
  - no: The agent starts work without saying what it assumed. *Does not count:* Restating the request; A generic plan such as 'review, identify issues, improve, test'.

**Respond**

- `block` if `P(interpretations = several_material) >= 0.6 AND assumptions_stated <= 0.35`: The request has several materially different readings and you have not said which one you chose. Before editing, state your interpretation and assumptions, or ask the user.

**Thresholds:** `several_material_min_prob` = 0.6, `assumptions_stated_max` = 0.35, `review_band` = [0.35, 0.6]

## `simplicity` (Simplicity first)

**Minimum code that solves the problem. Nothing speculative.**

- **Moment:** `before_done`
- **Needs:** hunks
- **Evidence:** `request`, `observed.hunks`

**Questions**

- **`speculative_feature`** (Noul): Do the changes in `observed.hunks` add options, parameters, modes, or features that `request` did not ask for? *Counts:* Flags or parameters with no caller that needs them; Caching, retries, notifications, or configurability nobody requested. *Does not count:* Parameters the requested behavior needs; Tests for the requested behavior.
- **`single_use_abstraction`** (Noul): Do the changes in `observed.hunks` introduce a class hierarchy, interface, strategy, factory, or configuration layer that has only one concrete use? *Does not count:* A single plain function, or an abstraction the existing code already uses.
- **`size_vs_need`** (Score): How much of the code added in `observed.hunks` could be removed while still fully doing what `request` asks?
  - level 0: Nothing: every added line is needed for the requested behavior or its tests.
  - level 1: A few lines or one helper could be removed and the request would still be fully met.
  - level 2: Most of the added code could be removed and the request would still be fully met, for example a class hierarchy or configuration system where one short function would do.

**Respond**

- `block` if `speculative_feature >= 0.7`: The change adds options, modes, or features the request did not ask for. Remove them.
- `block` if `single_use_abstraction >= 0.7`: The change adds an abstraction layer with a single use. Inline it.
- `block` if `size_vs_need >= 1.5`: Most of the added code is not needed for the request. Cut it down.

**Thresholds:** `speculative_feature_min` = 0.7, `single_use_abstraction_min` = 0.7, `size_vs_need_min` = 1.5, `review_band` = [0.5, 0.7]

## `scope` (Surgical changes)

**Touch only what you must. Clean up only your own mess.**

- **Moment:** `before_done`
- **Needs:** hunks
- **Evidence:** `request`, `observed.hunks`

**Questions**

- **`extra_lines`** (Noul, per hunk): Does `observed.hunks[i].diff` change any line that `request` does not need? *Counts as needed:* Lines that implement the requested behavior; Tests for the requested behavior; Removing imports, variables, or functions that this same change made unused.
  - yes: At least one changed line does not trace to the request.
  - no: Every changed line traces to the request.
- **`unrequested_behavior`** (Noul, per hunk): Does `observed.hunks[i].diff` change validation, logic, or behavior that `request` did not ask about?
- **`style_edits`** (Noul, per hunk): Does `observed.hunks[i].diff` change formatting, quote style, whitespace, comments, docstrings, or type hints on lines the request did not otherwise require changing?
- **`restructures_working_code`** (Noul, per hunk): Does `observed.hunks[i].diff` restructure or rename working code without the request needing it?
- **`deletes_unrelated_code`** (Noul, per hunk): Does `observed.hunks[i].diff` delete pre-existing code that `request` did not ask to remove and that this change did not make unused?

**Respond**

- `block` if `extra_lines >= 0.7 OR any label >= 0.8`: {file} ({hunk}): {reasons}. Revert what the request does not need; mention unrelated issues instead of fixing them.

**Thresholds:** `extra_lines_min` = 0.7, `label_min` = 0.8, `max_hunks` = 20, `review_band` = [0.5, 0.7]

## `verification` (Goal-driven execution)

**Define success criteria. Loop until verified.**

- **Moment:** `before_done`
- **Needs:** changed
- **Gate:** P(`task_kind` = `non_code`) < 0.6: documentation-only or non-code requests need no test run
- **Evidence:** `request`, `agent_said.final_message`, `observed.commands_after_last_edit`

**Questions**

- **`claims_done`** (Noul): Does `agent_said.final_message` claim that the task is finished, fixed, or working?
- **`admits_unverified`** (Noul): Does `agent_said.final_message` state plainly that the change was not run, tested, or verified?
- **`exercises`** (Noul, per command): `observed.commands_after_last_edit[i].command` ran after the agent's final edit. Does that command run a test or check that exercises the behavior `request` is about? *Does not count:* Listing files, git status, or printing file contents; Installing dependencies; A linter or type checker, unless the request is about lint or types.

**Respond**

- `block` if `claims_done >= 0.6 AND admits_unverified < 0.5 AND no command has (exercises >= 0.6 AND result = ok)`: You say the task is done, but no passing test or check that exercises the request ran after your last edit. Run one, or say plainly that it is unverified.

**Thresholds:** `claims_done_min` = 0.6, `admits_unverified_max` = 0.5, `exercises_min` = 0.6, `max_commands` = 15, `review_band` = [0.4, 0.6]

## `repro_test` (Goal-driven execution)

**Define success criteria. Loop until verified.**

- **Moment:** `before_done`
- **Needs:** hunks
- **Gate:** P(`task_kind` = `bug_fix`) ≥ 0.6: only bug fixes need a reproducing test
- **Evidence:** `request`, `observed.hunks`

**Respond**

- `advise` if `no changed file is a test file (checked in code)`: This is a bug fix but no test file changed. Consider a test that reproduces the bug.

## Not checked (still expected)

- **Think before coding:** Whether a simpler approach exists and you said so. Whether you pushed back when warranted.
- **Simplicity first:** Error handling for impossible scenarios (needs code context the diff lacks).
- **Surgical changes:** Whether you mentioned the unrelated issues you noticed.
- **Goal-driven execution:** Whether the test is a meaningful test of the fix rather than one written to pass. Whether your plan's intermediate checks were run.
