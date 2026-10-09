"""Offline tests for the karpathy-jev skill bundle. No TypeSafe key needed (KARPATHY_JEV_FAKE)."""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "karpathy-jev")
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "eval"))
import build_fixtures  # noqa: E402
import evidence as ev  # noqa: E402
import router  # noqa: E402
import run_eval  # noqa: E402

REG = router.load_registry()
ROUTER = os.path.join(SCRIPTS, "router.py")


# --- helpers ---

def nl(p):
    return {"type": "noul", "noul": p}


def ch(dist):
    best = max(dist, key=dist.get)
    return {"type": "choice", "choice": best, "confidence": dist[best], "probabilities": dist}


def complete_answers(plan, state):
    answers = {}
    for key, q in router._expected_questions(REG, plan, state).items():
        if q["type"] == "noul":
            answers[key] = nl(0.0)
        elif q["type"] == "choice":
            answers[key] = ch({name: 1.0 if i == 0 else 0.0 for i, name in enumerate(q["criteria"])})
        else:
            answers[key] = {"type": "score", "score": 0.0, "confidence": 1.0}
    return answers


def ev_(**kw):
    return {**router.empty_evidence(), **kw}


HUNK = {"file": "app.py", "header": "-1,2 +1,2", "diff": " def g(y):\n-    return y\n+    return  y\n"}


def blocked(resp):
    return sorted({r["id"] for r in resp["results"] if r["outcome"] == "block"})


def outcomes(resp):
    return {r["id"]: r["outcome"] for r in resp["results"]}


# --- registry integrity ---

def test_registry_is_consistent():
    full = router.full_state(REG, ev_(request="r", hunks=[HUNK], commands_after_last_edit=[{"command": "x", "result": "ok"}]))
    for did, d in REG["decisions"].items():
        assert did in router.RESPONDERS, f"{did} has no responder"
        assert d["moment"] in REG["moments"]
        assert d["principle"] in REG["principles"]
        assert set(d["needs"]) <= {"request", "hunks", "changed"}
        for p in d["evidence"]:
            router._get(full, p)
        if d.get("gate"):
            g = d["gate"]
            assert g["route"] in REG["routing"] and g["option"] in REG["routing"][g["route"]]["criteria"]
            assert ("at_least" in g) != ("below" in g)


# --- every constructed request is valid for the documented API ---

def resolve(obj, path):
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        obj = obj[int(part[1:-1])] if part.startswith("[") else obj[part]
    return obj


def lint(qid, q):
    assert q["type"] in ("noul", "choice", "score"), qid
    assert q["instructions"], qid
    if q["type"] == "choice":
        assert isinstance(q["criteria"], dict) and 2 <= len(q["criteria"]) <= 255, qid
    if q["type"] == "score":
        assert isinstance(q["criteria"], list) and 2 <= len(q["criteria"]) <= 10, qid
    if q["type"] == "noul" and "criteria" in q:
        assert set(q["criteria"]) <= {"true", "false"}, qid


CASES = build_fixtures.build()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_constructed_requests_are_valid_and_paths_resolve(case):
    e = run_eval.evidence_for(case)
    plan = router.identify(REG, case["moment"], e)
    state, questions = router.construct(REG, plan, e)
    json.dumps(state)
    assert questions, "every fixture should route to at least one question"
    for qid, q in questions.items():
        lint(qid, q)
        text = json.dumps(q)
        assert "{i}" not in text
        local = q["instructions"] if isinstance(q["instructions"], dict) else {}
        for path in re.findall(r"`([A-Za-z_][\w.\[\]]*)`", text):
            for scope in (state, local):
                try:
                    resolve(scope, path)
                    break
                except (KeyError, IndexError, TypeError):
                    continue
            else:
                pytest.fail(f"{qid}: `{path}` not in state")


def test_fixtures_cover_examples_and_routing():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) == 23
    for p in ("think-", "simple-", "surgical-", "goal-"):
        assert any(i.startswith(p) and i.endswith("-bad") for i in ids)
        assert any(i.startswith(p) and i.endswith("-good") for i in ids)


def test_fixture_commands_are_specific_and_labels_can_overlap():
    cases = [json.loads(line) for line in open(os.path.join(ROOT, "eval", "fixtures.jsonl"))]
    by_id = {c["id"]: c for c in cases}
    for cid in ("simple-discount-good", "simple-prefs-good", "surgical-email-good", "surgical-logging-good"):
        command = by_id[cid]["commands"][0]
        assert "::" in command["command"] and command["result"] == "ok" and command["output"]
    assert set(by_id["simple-discount-bad"]["expect"]["block"]) == {"simplicity", "scope"}
    assert set(by_id["surgical-email-bad"]["expect"]["block"]) == {"simplicity", "scope"}


def test_decision_metrics_are_case_level_and_exclude_unchecked():
    cases = [
        {"id": "a", "expect": {"block": ["scope"]}},
        {"id": "b", "expect": {"block": []}},
        {"id": "c", "expect": {"block": ["scope"]}},
    ]
    rows = [
        (cases[0], ["scope"], True, {"verdict": "revise", "results": [
            {"id": "scope", "outcome": "block"}, {"id": "scope", "outcome": "review"}]}),
        (cases[1], [], True, {"verdict": "proceed", "results": [
            {"id": "scope", "outcome": "pass"}, {"id": "scope", "outcome": "advise"}]}),
        (cases[2], [], False, {"verdict": "unchecked", "results": []}),
    ]
    m = run_eval.decision_metrics(rows, cases, ["scope"])["scope"]
    assert m["tp"] == 1 and m["fp"] == 0 and m["fn"] == 0 and m["excluded"] == 1
    assert m["outcomes"] == {"pass": 1, "block": 1, "review": 1, "advise": 1,
                              "gated_out": 0, "skipped": 0}
    assert any(c["expect"].get("gated_out") for c in CASES)


# --- 1. identify ---

def test_identify_selects_by_moment_and_evidence():
    p = router.identify(REG, "before_first_edit", ev_(request="r"))
    assert p["decisions"] == ["ambiguity"] and p["routes"] == []
    p = router.identify(REG, "before_done", ev_(request="r", hunks=[HUNK]))
    assert p["decisions"] == ["simplicity", "scope", "verification", "repro_test"]
    assert p["routes"] == ["task_kind"]
    # an edit seen in the transcript but no diff (e.g. not a git repo): only the command-based decisions run
    p = router.identify(REG, "before_done", ev_(request="r", edited=True))
    assert p["decisions"] == ["verification", "repro_test"]
    assert {s["id"] for s in p["skipped"]} == {"simplicity", "scope"}


# --- 2. construct ---

def test_construct_sends_only_declared_evidence_under_namespaced_ids():
    e = ev_(request="r", messages_before_first_edit=["m"], hunks=[HUNK])
    plan = router.identify(REG, "before_first_edit", e)
    state, qs = router.construct(REG, plan, e)
    assert state == {"request": "r", "agent_said": {"messages_before_first_edit": ["m"]}}  # no diff leaks in
    assert set(qs) == {"ambiguity__interpretations", "ambiguity__assumptions_stated"}

    e = ev_(request="r", hunks=[HUNK, HUNK], commands_after_last_edit=[{"command": "pytest", "result": "ok"}],
            final_message="done")
    state, qs = router.construct(REG, router.identify(REG, "before_done", e), e)
    assert "route__task_kind" in qs and "scope__h1__style_edits" in qs and "verification__c0__exercises" in qs
    assert "messages_before_first_edit" not in state["agent_said"]


def test_construct_caps_hunks_in_state_and_questions():
    many = [dict(HUNK, file=f"f{i}.py") for i in range(30)]
    e = ev_(request="r", hunks=many)
    state, qs = router.construct(REG, router.identify(REG, "before_done", e), e)
    cap = REG["decisions"]["scope"]["thresholds"]["max_hunks"]
    assert len(state["observed"]["hunks"]) == cap
    assert not any(k.startswith(f"scope__h{cap}__") for k in qs)


# --- 3. respond ---

def done_plan(**kw):
    e = ev_(request="r", hunks=[HUNK], final_message="Done.", **kw)
    plan = router.identify(REG, "before_done", e)
    state, _ = router.construct(REG, plan, e)
    return plan, state


def test_gate_closes_branch_and_ignores_its_answers():
    plan, state = done_plan()
    a = {**complete_answers(plan, state), "route__task_kind": ch({"bug_fix": 0.1, "new_behavior": 0.1, "refactor": 0.0, "non_code": 0.8, "other": 0.0}),
         "verification__claims_done": nl(0.95)}
    resp = router.respond(REG, plan, a, state)
    assert outcomes(resp)["verification"] == "gated_out"
    assert outcomes(resp)["repro_test"] == "gated_out"
    assert resp["verdict"] == "proceed"


def test_gate_opens_on_bug_fix_and_missing_routing_answer_leaves_it_open():
    plan, state = done_plan()
    a = {**complete_answers(plan, state), "route__task_kind": ch({"bug_fix": 0.9, "new_behavior": 0.0, "refactor": 0.0, "non_code": 0.1, "other": 0.0}), "verification__claims_done": nl(0.95)}
    resp = router.respond(REG, plan, a, state)
    assert blocked(resp) == ["repro_test", "verification"] and outcomes(resp)["repro_test"] == "advise"
    missing_route = complete_answers(plan, state)
    missing_route.pop("route__task_kind")
    resp = router.respond(REG, plan, {**missing_route, "verification__claims_done": nl(0.95)}, state)
    assert resp["verdict"] == "unchecked" and "route__task_kind" in resp["error"]


def test_verification_uses_observed_exit_status_not_the_claim():
    ok = [{"command": "pytest", "result": "ok"}]
    bad = [{"command": "pytest", "result": "error"}]
    plan, state = done_plan(commands_after_last_edit=ok)
    a = {**complete_answers(plan, state), "verification__claims_done": nl(0.9), "verification__c0__exercises": nl(0.95)}
    assert "verification" not in blocked(router.respond(REG, plan, a, state))
    plan, state = done_plan(commands_after_last_edit=bad)
    a = {**complete_answers(plan, state), "verification__claims_done": nl(0.9), "verification__c0__exercises": nl(0.95)}
    assert "verification" in blocked(router.respond(REG, plan, a, state))
    a["verification__admits_unverified"] = nl(0.9)  # honest about it
    assert "verification" not in blocked(router.respond(REG, plan, a, state))


def test_ambiguity_decides_on_probability_not_confidence():
    e = ev_(request="r")
    plan = router.identify(REG, "before_first_edit", e)
    state, _ = router.construct(REG, plan, e)
    flat = {"type": "choice", "choice": "several_material", "confidence": 0.2,
            "probabilities": {"one_clear": 0.2, "minor_variants": 0.2, "several_material": 0.6}}
    resp = router.respond(REG, plan, {"ambiguity__interpretations": flat, "ambiguity__assumptions_stated": nl(0.1)}, state)
    assert resp["verdict"] == "revise"
    resp = router.respond(REG, plan, {"ambiguity__interpretations": flat, "ambiguity__assumptions_stated": nl(0.45)}, state)
    assert resp["verdict"] == "proceed" and outcomes(resp)["ambiguity"] == "review"


def test_scope_labels_co_occur_and_name_the_hunk():
    plan, state = done_plan()
    a = {**complete_answers(plan, state), "scope__h0__style_edits": nl(0.9), "scope__h0__unrequested_behavior": nl(0.85)}
    r = [x for x in router.respond(REG, plan, a, state)["results"] if x["id"] == "scope"][0]
    assert r["outcome"] == "block" and "app.py" in r["message"]
    assert "style edits" in r["message"] and "unrequested behavior" in r["message"]


def test_scope_flags_unrequested_docs():
    plan, state = done_plan()
    r = [x for x in router.respond(REG, plan, {**complete_answers(plan, state), "scope__h0__unrequested_docs": nl(0.9)}, state)["results"]
         if x["id"] == "scope"][0]
    assert r["outcome"] == "block" and "unrequested docs" in r["message"]


def test_repro_test_needs_a_failing_run_on_unfixed_code():
    e = ev_(request="Sorting breaks on duplicate scores", hunks=[{"file": "tests/test_app.py", "header": "-1", "diff": "+x\n"}],
            commands_on_unfixed_code=[{"command": "pytest -q", "result": "error"}], edited=True)
    plan = router.identify(REG, "before_done", e)
    state, qs = router.construct(REG, plan, e)
    assert "repro_test__c0__reproduces" in qs and "verification__c0__exercises" not in qs
    route = {"route__task_kind": ch({"bug_fix": 0.9, "new_behavior": 0.0, "refactor": 0.0, "non_code": 0.0, "other": 0.1})}
    r = lambda a: outcomes(router.respond(REG, plan, {**route, **a}, state))["repro_test"]  # noqa: E731
    assert r({"repro_test__c0__reproduces": nl(0.9)}) == "pass"
    assert r({"repro_test__c0__reproduces": nl(0.2)}) == "block"
    e["commands_on_unfixed_code"] = [{"command": "pytest -q", "result": "ok"}]  # passed before the fix: no reproduction
    plan = router.identify(REG, "before_done", e)
    state, _ = router.construct(REG, plan, e)
    assert outcomes(router.respond(REG, plan, {**route, "repro_test__c0__reproduces": nl(0.9)}, state))["repro_test"] == "block"


def test_messages_come_from_the_registry():
    plan, state = done_plan()
    a = {"simplicity__single_use_abstraction": nl(0.9), "verification__claims_done": nl(0.9)}
    msgs = {x["message"] for d in REG["decisions"].values() for x in d["respond"]}
    for r in router.respond(REG, plan, a, state)["results"]:
        if r["outcome"] == "block":
            assert r["message"] in msgs


# --- evidence ---

def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "app.py").write_text("def f(x):\n    return x\n\n\ndef g(y):\n    return y\n")
    git(d, "add", ".")
    git(d, "commit", "-qm", "init")
    return d


def test_clean_tree_uses_head_as_baseline(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("KARPATHY_JEV_HOME", str(tmp_path / "home"))
    snap = ev.snapshot(str(repo))
    assert snap["base"] == subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    (repo / "app.py").write_text("def f(x):\n    return x\n\n\ndef g(y):\n    return y * 2\n")
    assert [h["file"] for h in ev.turn_hunks(str(repo), snap)] == ["app.py"]


def test_baseline_excludes_changes_made_before_the_turn(repo):
    (repo / "app.py").write_text("def f(x):\n    return x + 0\n\n\ndef g(y):\n    return y\n")
    (repo / "old.txt").write_text("already here\n")
    snap = ev.snapshot(str(repo))
    (repo / "app.py").write_text("def f(x):\n    return x + 0\n\n\ndef g(y):\n    return y * 2\n")
    (repo / "new.py").write_text("print('hi')\n")
    hunks = ev.turn_hunks(str(repo), snap)
    assert [h["file"] for h in hunks] == ["app.py", "new.py"]
    changed = "".join(l for l in hunks[0]["diff"].splitlines(True) if l[:1] in "+-")
    assert "y * 2" in changed and "x + 0" not in changed


def test_snapshot_never_writes_to_the_repo(repo, tmp_path, monkeypatch):
    # agents often cannot write .git (another owner, a sandbox); the baseline must still work
    monkeypatch.setenv("KARPATHY_JEV_HOME", str(tmp_path / "home"))
    (repo / "app.py").write_text("def f(x):\n    return x + 0\n\n\ndef g(y):\n    return y\n")
    objects = repo / ".git" / "objects"
    before = sorted(p for p in objects.rglob("*"))
    modes = {p: p.stat().st_mode for p in [objects, *before]}
    for p in modes:
        p.chmod(modes[p] & ~0o222)
    try:
        snap = ev.snapshot(str(repo))
        (repo / "app.py").write_text("def f(x):\n    return x + 0\n\n\ndef g(y):\n    return y * 2\n")
        hunks = ev.turn_hunks(str(repo), snap)
    finally:
        for p, m in modes.items():
            p.chmod(m)
    assert [h["file"] for h in hunks] == ["app.py"]
    changed = "".join(l for l in hunks[0]["diff"].splitlines(True) if l[:1] in "+-")
    assert "y * 2" in changed and "x + 0" not in changed
    assert sorted(p for p in objects.rglob("*")) == before


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def cu(t):
    return {"type": "user", "message": {"content": t}}


def ca(*b):
    return {"type": "assistant", "message": {"content": list(b)}}


def cr(tid, err=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": err}]}}


def test_claude_transcript(tmp_path):
    p = tmp_path / "t.jsonl"
    write_jsonl(p, [
        cu("old"), ca({"type": "text", "text": "old"}),
        cu("Fix the empty email crash"),
        ca({"type": "tool_use", "id": "b0", "name": "Bash", "input": {"command": "pytest -q -k empty"}}),
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "b0", "is_error": True,
                                                  "content": [{"type": "text", "text": "E  ValueError: empty\n1 failed"}]}]}},
        ca({"type": "text", "text": "Assuming empty means missing or blank."},
           {"type": "tool_use", "id": "e1", "name": "Edit", "input": {"file_path": "v.py"}}), cr("e1"),
        ca({"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "pytest -q"}}), cr("b1", True),
        ca({"type": "tool_use", "id": "b2", "name": "Bash", "input": {"command": "pytest -q"}}), cr("b2"),
        ca({"type": "tool_use", "id": "b3", "name": "Bash", "input": {"command": "pytest -q 2>&1 | tail -5"}}), cr("b3"),
        cu("Stop hook feedback:\nx"),
        ca({"type": "text", "text": "Done, tests pass."}),
    ])
    t = ev.read_turn(str(p))
    assert t["request"] == "Fix the empty email crash"
    assert t["messages_before_first_edit"] == ["Assuming empty means missing or blank."]
    assert t["commands_on_unfixed_code"] == [{"command": "pytest -q -k empty", "result": "error", "output": "E  ValueError: empty\n1 failed"}]
    assert [(c["command"], c["result"]) for c in t["commands_after_last_edit"]] == [
        ("pytest -q", "error"), ("pytest -q", "ok"), ("pytest -q 2>&1 | tail -5", "masked")]


def test_codex_transcript(tmp_path):
    p = tmp_path / "c.jsonl"
    it = lambda payload: {"type": "response_item", "payload": payload}  # noqa: E731
    write_jsonl(p, [
        it({"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Add logging"}]}),
        it({"type": "custom_tool_call", "name": "apply_patch", "call_id": "a", "input": "*** Begin Patch"}),
        it({"type": "custom_tool_call_output", "call_id": "a", "output": "Success"}),
        it({"type": "function_call", "name": "shell", "call_id": "s",
            "arguments": json.dumps({"command": ["bash", "-lc", "pytest -q"]})}),
        it({"type": "function_call_output", "call_id": "s", "output": json.dumps({"metadata": {"exit_code": 1}})}),
    ])
    t = ev.read_turn(str(p))
    assert t["edited"] and [(c["command"], c["result"]) for c in t["commands_after_last_edit"]] == [("pytest -q", "error")]


def test_reproduction_after_the_first_edit_counts_when_the_change_was_reverted():
    cmd = lambda i, c, err=False: {"id": i, "name": "Bash", "command": c, "status": "error" if err else "ok", "kind": "command"}  # noqa: E731
    edit = {"id": "e", "name": "Edit", "command": "", "status": "ok", "kind": "edit"}
    calls = [cmd(1, "grep -rn crash src"), edit, cmd(2, "pytest -q"),
             cmd(3, "git diff > /tmp/fix.patch && git apply -R /tmp/fix.patch"), cmd(4, "pytest -q -k empty", err=True),
             cmd(5, "git apply /tmp/fix.patch"), cmd(6, "pytest -q -k empty")]
    assert [c["id"] for c in ev.on_unfixed_code(calls)] == [1, 3, 4, 5]  # 5 is the reapply itself; it never fails as a test
    calls = [edit, cmd(1, "git stash && pytest -q; git stash pop", err=True), cmd(2, "pytest -q")]
    assert [c["id"] for c in ev.on_unfixed_code(calls)] == [1]
    calls = [edit, cmd(1, "git stash list"), cmd(2, "pytest -q", err=True)]
    assert ev.on_unfixed_code(calls) == []


def test_masked_exit_codes_do_not_verify():
    assert ev.observed_result("pytest -q | tail -20", "ok") == "masked"
    assert ev.observed_result("set -o pipefail; pytest -q | tail -20", "ok") == "ok"
    assert ev.observed_result("pytest -q | tail -20", "error") == "error"
    assert ev.observed_result("pytest -q | tail -20", "ok", pipefail=True) == "ok"  # the hook rewrote it
    assert ev.observed_result("pytest -q; echo done", "ok", "done", pipefail=True) == "masked"  # echo still masks
    assert ev.observed_result("grep -rn foo src | head", "ok") == "masked"  # not a check either way
    assert ev.observed_result("pytest -q -k 'a or b'", "ok") == "ok"
    assert ev.observed_result('pytest -q; echo "EXIT CODE: $?"', "ok") == "masked"  # no output: unknown
    assert ev.observed_result('pytest -q; echo "EXIT CODE: $?"', "ok", "1 failed\nEXIT CODE: 1\n") == "error"
    assert ev.observed_result('pytest -q; echo "EXIT CODE: $?"', "ok", "3 passed\nEXIT CODE: 0") == "ok"
    assert ev.observed_result('pytest -q; echo done', "ok", "3 passed\ndone") == "ok"  # the runner's own summary
    # a reproduction followed by a restore step: the echoed code is mid-output, the last stage is git stash pop
    cmd = 'git stash push -- a.py && python -c "import a"\necho "EXIT: $?"\ngit stash pop'
    assert ev.observed_result(cmd, "ok", "Traceback ...\nAssertionError\nEXIT: 1\nOn branch main\nDropped refs/stash@{0}") == "error"
    assert ev.observed_result(cmd, "ok", "ok\nEXIT: 0\nDropped refs/stash@{0}") == "ok"
    assert ev.observed_result("pytest -q; git stash pop", "ok", "1 failed\nDropped refs/stash@{0}") == "error"
    assert ev.observed_result("pytest -q | tail -5", "ok", "FAILED tests/test_a.py::test_x\n1 failed, 2 passed") == "error"
    assert ev.observed_result("pytest -q | tail -5", "ok", "ERROR:root:noise from a passing test\n3 passed") == "ok"
    assert ev.observed_result("pytest -q | tail -5", "ok", "collecting ...") == "masked"
    assert ev.with_pipefail("pytest -q | tail -5") == "set -o pipefail; pytest -q | tail -5"
    assert ev.with_pipefail("pytest -q || true") == "pytest -q || true"
    assert ev.with_pipefail("set -o pipefail; pytest -q | tail") == "set -o pipefail; pytest -q | tail"
    assert ev.observed_result('python -c "\nimport x\n"\necho "EXIT CODE: $?"', "ok", "Traceback\nEXIT CODE: 1") == "error"
    assert ev.observed_result('python -c "\nimport x\n"\necho "EXIT CODE: $?"', "ok", "ok\nEXIT CODE: 0") == "ok"
    assert ev.observed_result("pytest -q || true", "ok") == "masked"
    e = ev_(request="r", hunks=[HUNK], final_message="Done.",
            commands_after_last_edit=[{"command": "pytest -q | tail -5", "result": "masked"}])
    plan = router.identify(REG, "before_done", e)
    state, _ = router.construct(REG, plan, e)
    a = {**complete_answers(plan, state), "verification__claims_done": nl(0.95), "verification__c0__exercises": nl(0.95)}
    assert "verification" in blocked(router.respond(REG, plan, a, state))


def test_adding_a_test_first_keeps_the_code_unfixed():
    cmd = lambda i, c, err=False: {"id": i, "name": "Bash", "command": c, "status": "error" if err else "ok", "kind": "command"}  # noqa: E731
    edit = lambda i, path: {"id": i, "name": "Edit", "command": "", "status": "ok", "kind": "edit", "paths": [path]}  # noqa: E731
    calls = [edit("t", "tests/test_app.py"), cmd(1, "pytest -q -k empty", err=True), edit("f", "src/app.py"), cmd(2, "pytest -q -k empty")]
    assert [c["id"] for c in ev.on_unfixed_code(calls)] == [1]
    patch = {"id": "p", "name": "apply_patch", "command": "", "status": "ok", "kind": "edit",
             "paths": ev._paths_of("*** Begin Patch\n*** Update File: tests/test_app.py\n@@\n+x\n*** End Patch")}
    assert patch["paths"] == ["tests/test_app.py"]
    assert [c["id"] for c in ev.on_unfixed_code([patch, cmd(1, "pytest -q", err=True)])] == [1]
    assert ev.on_unfixed_code([{**patch, "paths": ["src/app.py"]}, cmd(1, "pytest -q", err=True)]) == []


def test_test_path_pattern():
    for f in ("tests/test_a.py", "src/a_test.go", "web/a.spec.ts", "test_x.py", "pkg/__tests__/x.js"):
        assert ev.TEST_PATH.search(f), f
    for f in ("src/app.py", "contest.py", "latest/x.py"):
        assert not ev.TEST_PATH.search(f), f


# --- hook mode end to end ---

def run(args, env, stdin=None, cwd=None):
    r = subprocess.run([sys.executable, ROUTER, *args], input=stdin, capture_output=True, text=True, env=env, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


@pytest.fixture
def env(tmp_path):
    e = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    e["KARPATHY_JEV_HOME"] = str(tmp_path / "home")
    return e


def fake(tmp_path, answers):
    p = tmp_path / "fake.json"
    p.write_text(json.dumps(answers))
    return str(p)


def test_hook_mode(repo, tmp_path, env):
    tr = tmp_path / "t.jsonl"
    base = {"session_id": "s1", "cwd": str(repo), "transcript_path": str(tr)}
    hook = lambda **kw: run(["hook"], env, json.dumps({**base, **kw}))[::2]  # noqa: E731  (code, stderr)
    env["KARPATHY_JEV_FAKE"] = fake(tmp_path, {
        "ambiguity__interpretations": ch({"one_clear": 0.1, "minor_variants": 0.0, "several_material": 0.9}),
        "ambiguity__assumptions_stated": nl(0.05),
        "verification__claims_done": nl(0.9), "scope__h0__style_edits": nl(0.9),
    })
    assert hook(hook_event_name="UserPromptSubmit", prompt="Make g faster") == (0, "")
    write_jsonl(tr, [cu("Make g faster")])
    code, err = hook(hook_event_name="PreToolUse", tool_name="Edit")
    assert code == 2 and "think_before_coding" in err
    assert hook(hook_event_name="PreToolUse", tool_name="Edit")[0] == 0  # once per turn
    assert hook(hook_event_name="PreToolUse", tool_name="Bash")[0] == 0
    code, out, _ = run(["hook"], env, json.dumps({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                  "tool_input": {"command": "pytest -q 2>&1 | tail -5"}}))
    assert code == 0 and json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"].startswith("set -o pipefail; ")
    code, out, _ = run(["hook"], env, json.dumps({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                  "tool_input": {"command": "pytest -q"}}))
    assert code == 0 and out == ""  # nothing to rewrite

    (repo / "app.py").write_text("def f(x):\n    return x\n\n\ndef g(y):\n    return  y\n")
    write_jsonl(tr, [cu("Make g faster"),
                     ca({"type": "tool_use", "id": "e1", "name": "Edit", "input": {}}), cr("e1"),
                     ca({"type": "text", "text": "Done, g is faster."})])
    code, err = hook(hook_event_name="Stop", stop_hook_active=False)
    assert code == 2 and "app.py" in err and "surgical_changes" in err and "goal_driven_execution" in err
    assert hook(hook_event_name="Stop", stop_hook_active=True)[0] == 2  # the revision is judged again
    assert hook(hook_event_name="Stop", stop_hook_active=True)[0] == 0  # then the turn may end
    env["KARPATHY_JEV_MODE"] = "shadow"
    assert hook(hook_event_name="Stop", stop_hook_active=False)[0] == 0

    log = [json.loads(l) for l in open(os.path.join(env["KARPATHY_JEV_HOME"], "log.jsonl"))]
    stops = [x for x in log if x["moment"] == "before_done"]
    assert [x["response"]["verdict"] for x in stops] == ["revise", "revise", "revise"]
    assert all({"plan", "state", "answers", "response"} <= set(x) for x in stops)


def test_hook_skips_turns_without_changes(repo, tmp_path, env):
    tr = tmp_path / "t.jsonl"
    write_jsonl(tr, [cu("What does g do?"), ca({"type": "text", "text": "Returns y."})])
    env["KARPATHY_JEV_FAKE"] = fake(tmp_path, {"verification__claims_done": nl(1.0)})
    env["KARPATHY_JEV_HOME"] = str(repo / ".karpathy-jev")  # own files inside the repo are not changes
    base = json.dumps({"session_id": "s2", "cwd": str(repo), "transcript_path": str(tr),
                       "hook_event_name": "UserPromptSubmit", "prompt": "What does g do?"})
    run(["hook"], env, base)
    stop = json.dumps({"session_id": "s2", "cwd": str(repo), "transcript_path": str(tr), "hook_event_name": "Stop"})
    assert run(["hook"], env, stop)[0] == 0
    assert not os.path.exists(os.path.join(env["KARPATHY_JEV_HOME"], "log.jsonl"))


def test_fails_open_as_unchecked(repo, tmp_path, env):
    code, out, _ = run(["start", "--request", "Refactor everything"], env, cwd=str(repo))
    code, out, _ = run(["decide", "before_first_edit"], env, cwd=str(repo))
    assert code == 0 and json.loads(out)["verdict"] == "unchecked"


# --- agent mode end to end ---

def test_agent_mode(repo, tmp_path, env):
    env["KARPATHY_JEV_FAKE"] = fake(tmp_path, {
        "route__task_kind": ch({"bug_fix": 0.0, "new_behavior": 0.9, "refactor": 0.0, "non_code": 0.1, "other": 0.0}),
        "verification__claims_done": nl(0.9),
        "verification__c0__exercises": nl(0.9), "verification__c1__exercises": nl(0.9),
    })
    assert run(["start", "--request", "Double g's output"], env, cwd=str(repo))[0] == 0
    (repo / "app.py").write_text("def f(x):\n    return x\n\n\ndef g(y):\n    return y * 2\n")
    # nothing ran after the edit: revise, exit 2
    code, out, err = run(["decide", "before_done", "--final", "Done."], env, cwd=str(repo))
    assert code == 2 and json.loads(out)["verdict"] == "revise" and "verification" in blocked(json.loads(out))
    # a failing run is observed as failing
    assert run(["run", "--", "false"], env, cwd=str(repo))[0] == 1
    code, out, _ = run(["decide", "before_done", "--final", "Done."], env, cwd=str(repo))
    assert code == 2
    # a passing run after the edit verifies it
    assert run(["run", "--", "true"], env, cwd=str(repo))[0] == 0
    code, out, _ = run(["decide", "before_done", "--final", "Done."], env, cwd=str(repo))
    assert code == 0 and json.loads(out)["verdict"] == "proceed"
    # identify is a dry run: plan and request, no Jev call
    code, out, _ = run(["identify", "before_done"], env, cwd=str(repo))
    body = json.loads(out)
    assert body["verdict"] == "dry_run" and "route__task_kind" in body["request"]["questions"]


def test_agent_mode_records_reproduction_before_the_first_change(repo, tmp_path, env):
    env["KARPATHY_JEV_FAKE"] = fake(tmp_path, {
        "route__task_kind": ch({"bug_fix": 0.9, "new_behavior": 0.0, "refactor": 0.0, "non_code": 0.0, "other": 0.1}),
        "repro_test__c0__reproduces": nl(0.9), "verification__c0__exercises": nl(0.9),
    })
    assert run(["start", "--request", "g returns the wrong value"], env, cwd=str(repo))[0] == 0
    (repo / "test_app.py").write_text("from app import g\n\n\ndef test_g():\n    assert g(2) == 4\n")  # a test first is not the fix
    assert run(["run", "--", "false"], env, cwd=str(repo))[0] == 1  # reproduction: fails before any change
    (repo / "app.py").write_text("def f(x):\n    return x\n\n\ndef g(y):\n    return y * 2\n")
    assert run(["run", "--", "true"], env, cwd=str(repo))[0] == 0
    code, out, _ = run(["decide", "before_done", "--final", "Fixed."], env, cwd=str(repo))
    assert code == 0 and "repro_test" not in blocked(json.loads(out))
    runs = [json.loads(l) for l in open(os.path.join(env["KARPATHY_JEV_HOME"], "runs.jsonl"))]
    assert [r["changed"] for r in runs] == [False, True]
    assert run(["run", "--", "sh", "-c", "echo out; echo err >&2; exit 3"], env, cwd=str(repo))[0] == 3
    assert json.loads(open(os.path.join(env["KARPATHY_JEV_HOME"], "runs.jsonl")).readlines()[-1])["output"] == "out\nerr\n"
    assert run(["run", "--", "./no_such_runner.py"], env, cwd=str(repo))[0] == 127  # recorded, not a traceback
    assert json.loads(open(os.path.join(env["KARPATHY_JEV_HOME"], "runs.jsonl")).readlines()[-1])["result"] == "error"


def test_agent_mode_reports_what_was_not_judged(repo, tmp_path, env):
    env["KARPATHY_JEV_FAKE"] = fake(tmp_path, {})
    code, out, err = run(["decide", "before_first_edit"], env, cwd=str(repo))  # no start: no request
    assert code == 0 and "not judged" in err and "ambiguity" in err


# --- replay and skill sync ---

def test_replay_reapplies_thresholds_without_calling_jev(tmp_path):
    plan, state = done_plan()
    answers = {**complete_answers(plan, state), "scope__h0__extra_lines": nl(0.65)}
    resp = router.respond(REG, plan, answers, state)
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({"ts": 1, "moment": "before_done", "plan": plan, "state": state,
                               "answers": answers, "response": resp}) + "\n")
    assert router.replay(str(log), REG)["changed"] == []
    reg2 = json.loads(json.dumps(REG))
    reg2["decisions"]["scope"]["thresholds"]["extra_lines_min"] = 0.6
    assert router.replay(str(log), reg2)["changed"][0]["now"] == ["repro_test", "scope"]


def test_skill_files_are_generated_from_the_registry():
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_skill.py"), "--check"])
    assert r.returncode == 0, "stale: run python3 skills/karpathy-jev/scripts/build_skill.py"
    skill = open(os.path.join(SKILL, "SKILL.md")).read()
    ref = open(os.path.join(SKILL, "references", "decisions.md")).read()
    assert skill.startswith("---\nname: karpathy-jev\n")
    for did, d in REG["decisions"].items():
        assert f"`{did}`" in skill and f"`{did}`" in ref
        for q in list(d.get("questions", {})) + list(d.get("per_hunk_questions", {})) + list(d.get("per_command_questions", {})):
            assert f"`{q}`" in ref
    for m in REG["moments"]:
        assert f"`{m}`" in skill
    assert "{i}" not in skill + ref
