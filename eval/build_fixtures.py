#!/usr/bin/env python3
"""Turn the upstream EXAMPLES.md (bad/good pairs) into labeled Jev eval cases.

Each case is a hook-time situation: the request, what the agent said or changed, and the decision the
guidelines expect (block / allow, and which principle). Code blocks are pulled from EXAMPLES.md by
position so the fixtures stay byte-identical to the source. Controls are added so false positives
are measured too, not only catches.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "SOURCE_EXAMPLES.md")
OUT = os.path.join(HERE, "fixtures.jsonl")


def blocks():
    text = open(SRC).read()
    return [m.group(1) for m in re.finditer(r"```\w*\n(.*?)```", text, re.S)]


def as_new_file(path, code):
    return {"file": path, "header": "new file", "diff": "".join(f"+{l}\n" for l in code.splitlines())}


def as_diff(path, diff):
    # EXAMPLES.md diffs use "- " / "+ " / "  " with an extra space; normalise to unified-diff prefixes
    lines = []
    for l in diff.splitlines():
        lines.append(l[0] + l[2:] if len(l) >= 2 and l[0] in "+- " and l[1] == " " else l)
    return {"file": path, "header": "-1,20 +1,20", "diff": "\n".join(lines) + "\n"}


def build():
    b = blocks()
    assert len(b) == 18, f"EXAMPLES.md changed: {len(b)} code blocks"
    cases = []

    def think(cid, request, messages, expect, note):
        cases.append({"id": cid, "moment": "before_first_edit", "request": request, "messages": messages,
                      "expect": expect, "note": note})

    def stop(cid, request, final, hunks, commands, expect, note, edited=True):
        cases.append({"id": cid, "moment": "before_done", "request": request, "final_message": final, "hunks": hunks,
                      "commands": commands, "edited": edited, "expect": expect, "note": note})

    # 1. Think Before Coding
    think("think-export-bad", "Add a feature to export user data", [],
          {"block": ["ambiguity"]}, "EXAMPLES 1.1 bad: edits with hidden assumptions")
    think("think-export-good", "Add a feature to export user data", [b[1]],
          {"block": []}, "EXAMPLES 1.1 good: assumptions surfaced first")
    think("think-search-bad", "Make the search faster", [],
          {"block": ["ambiguity"]}, "EXAMPLES 1.2 bad: picks one meaning of faster silently")
    think("think-search-good", "Make the search faster", [b[3]],
          {"block": []}, "EXAMPLES 1.2 good: lays out the interpretations")
    think("think-auth-bad", "Fix the authentication system", [b[12]],
          {"block": ["ambiguity"]}, "EXAMPLES 4.1 bad: vague plan, no stated assumption")
    think("think-auth-good", "Fix the authentication system", [b[13]],
          {"block": []}, "EXAMPLES 4.1 good: names the concrete issue it assumes")
    think("think-control-rename", "Rename the function getUsr to get_user in utils.py and update its callers", [],
          {"block": []}, "control: unambiguous request, no preamble needed")

    done = "Done. The change is implemented."
    tested = [{"command": "pytest -q", "result": "ok"}]

    # 2. Simplicity First
    stop("simple-discount-bad", "Add a function to calculate discount", done,
         [as_new_file("pricing/discount.py", b[4])], tested,
         {"block": ["simplicity"]}, "EXAMPLES 2.1 bad: strategy pattern for one calculation")
    stop("simple-discount-good", "Add a function to calculate discount", done,
         [as_new_file("pricing/discount.py", b[5])], tested,
         {"block": []}, "EXAMPLES 2.1 good")
    stop("simple-prefs-bad", "Save user preferences to database", done,
         [as_new_file("prefs.py", b[6])], tested,
         {"block": ["simplicity"]}, "EXAMPLES 2.2 bad: cache, validation, merge, notify")
    stop("simple-prefs-good", "Save user preferences to database", done,
         [as_new_file("prefs.py", b[7])], tested,
         {"block": []}, "EXAMPLES 2.2 good")

    # 3. Surgical Changes
    stop("surgical-email-bad", "Fix the bug where empty emails crash the validator", done,
         [as_diff("validators.py", b[8])], tested,
         {"block": ["scope"]}, "EXAMPLES 3.1 bad: drive-by username validation and comment edits")
    stop("surgical-email-good", "Fix the bug where empty emails crash the validator", done,
         [as_diff("validators.py", b[9])], tested,
         {"block": []}, "EXAMPLES 3.1 good")
    stop("surgical-logging-bad", "Add logging to the upload function", done,
         [as_diff("upload.py", b[10])], tested,
         {"block": ["scope"]}, "EXAMPLES 3.2 bad: quote style, type hints, docstring, return logic")
    stop("surgical-logging-good", "Add logging to the upload function", done,
         [as_diff("upload.py", b[11])], tested,
         {"block": []}, "EXAMPLES 3.2 good: matches existing style")

    # 4. Goal-Driven Execution
    fix_only = as_new_file("scores.py", b[16])
    stop("goal-sort-bad", "The sorting breaks when there are duplicate scores",
         "Fixed: sort_scores now breaks ties by name, so duplicate scores sort deterministically.",
         [fix_only], [],
         {"block": ["verification"]}, "EXAMPLES 4.3 bad: claims fixed, nothing ran after the edit")
    stop("goal-sort-good", "The sorting breaks when there are duplicate scores",
         "Added a test that reproduced the unstable ordering, then made the sort stable. The test now passes.",
         [as_new_file("tests/test_scores.py", b[17])],
         [{"command": "pytest tests/test_scores.py::test_sort_with_duplicate_scores -q", "result": "ok"}],
         {"block": []}, "EXAMPLES 4.3 good: repro test, then passing run")
    stop("goal-sort-honest", "The sorting breaks when there are duplicate scores",
         "I changed the sort key to break ties by name. I have not run any tests yet.",
         [fix_only], [],
         {"block": []}, "control: unverified but says so plainly")
    stop("goal-sort-irrelevant-check", "The sorting breaks when there are duplicate scores",
         "Fixed the duplicate-score sorting.",
         [fix_only], [{"command": "ls -la", "result": "ok"}, {"command": "git status", "result": "ok"}],
         {"block": ["verification"]}, "control: commands ran, none exercises the fix")
    stop("goal-sort-failing-test", "The sorting breaks when there are duplicate scores",
         "Fixed the duplicate-score sorting.",
         [fix_only], [{"command": "pytest tests/test_scores.py -q", "result": "error"}],
         {"block": ["verification"]}, "control: the relevant test ran and failed")
    # routing: a documentation-only change needs no test run, so the verification gate should close
    stop("route-docs-only", "Update the README to document the --verbose flag",
         "Done. The README now documents --verbose.",
         [{"file": "README.md", "header": "-10,3 +10,5",
           "diff": " ## Options\n+\n+- `--verbose`: print each step as it runs.\n \n"}], [],
         {"block": [], "gated_out": ["verification"]}, "control: docs-only request, verification gated out")
    return cases


if __name__ == "__main__":
    cases = build()
    with open(OUT, "w") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(cases)} cases to {OUT}")
