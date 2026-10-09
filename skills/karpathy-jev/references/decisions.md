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
- **`unrequested_docs`** (Noul, per hunk): Is `observed.hunks[i].diff` an edit to documentation, a changelog, or release notes, when `request` does not ask for any documentation change?
  - yes: The hunk edits docs, a changelog, or release notes, and `request` asks only for a code change. Count it even when the text describes the requested fix.
  - no: The hunk changes code or tests, or `request` asks for documentation.

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
- **`exercises`** (Noul, per command): `observed.commands_after_last_edit[i].command` ran after the agent's final edit; the end of its output is `observed.commands_after_last_edit[i].output`. Does that command run a test or check that exercises the behavior `request` is about? *Does not count:* Listing files, git status, or printing file contents; Installing dependencies; A linter or type checker, unless the request is about lint or types.

**Respond**

- `block` if `claims_done >= 0.6 AND admits_unverified < 0.5 AND no command has (exercises >= 0.6 AND result = ok)`: You say the task is done, but no passing test or check that exercises the request ran after your last edit. Run one, or say plainly that it is unverified. A check piped into tail/head/grep reports the pipe's exit code, not the check's: run it plain.

**Thresholds:** `claims_done_min` = 0.6, `admits_unverified_max` = 0.5, `exercises_min` = 0.6, `max_commands` = 15, `review_band` = [0.4, 0.6]

## `repro_test` (Goal-driven execution)

**Define success criteria. Loop until verified.**

- **Moment:** `before_done`
- **Needs:** changed
- **Gate:** P(`task_kind` = `bug_fix`) ≥ 0.6: only bug fixes need a reproducing test
- **Evidence:** `request`, `observed.hunks`, `observed.commands_on_unfixed_code`

**Questions**

- **`reproduces`** (Noul, per command): `observed.commands_on_unfixed_code[i].command` ran while the fix was not in the tree (before any non-test file was edited, or after the change was stashed or reverted). Its result was `observed.commands_on_unfixed_code[i].result` and the end of its output is `observed.commands_on_unfixed_code[i].output`. Judged on its own, ignoring what ran later: does that command run a test, script, or check that fails because of the problem `request` describes? *Does not count:* Listing files, reading code, git status, or searching; Installing dependencies; A command that fails for an unrelated reason, such as a missing module or a typo.
  - yes: The command exercises the function, file, or behavior that `request` names, and its failure is what the request describes. A pytest node, a test file, a doctest, or a one-off script of that behavior all count.
  - no: The command only reads, lists, or searches code, installs dependencies, or fails for an unrelated reason, or it does not touch the behavior `request` describes.

**Respond**

- `block` if `no command on the unfixed code has (result = error AND reproduces >= 0.6)`: This is a bug fix, but no check failed on the unfixed code. Reproduce first: before editing any non-test file (adding a test first is fine), or with your change stashed or reverted, run a test or script that exits non-zero because of the bug, for example an assert; run it plain, not piped into tail/head/grep and not followed by echo. Then fix it and show that same check passing.
- `advise` if `no changed file is a test file (checked in code)`: This is a bug fix but no test file changed. Consider a test that reproduces the bug.

**Thresholds:** `reproduces_min` = 0.6, `max_commands` = 15

## Not checked (still expected)

- **Think before coding:** Whether a simpler approach exists and you said so. Whether you pushed back when warranted.
- **Simplicity first:** Error handling for impossible scenarios (needs code context the diff lacks).
- **Surgical changes:** Whether you mentioned the unrelated issues you noticed.
- **Goal-driven execution:** Whether the test is a meaningful test of the fix rather than one written to pass. Whether your plan's intermediate checks were run.
