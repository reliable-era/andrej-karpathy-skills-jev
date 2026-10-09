import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "eval"))
import run_eval  # noqa: E402


def test_metrics_exclude_one_unchecked_decision_from_case_counts():
    cases = [{"id": "mixed", "expect": {"block": ["scope"]}}]
    rows = [(cases[0], ["scope"], False, {"verdict": "revise", "results": [
        {"id": "scope", "outcome": "block"},
        {"id": "verification", "outcome": "unchecked"},
    ]})]
    metrics = run_eval.decision_metrics(rows, cases, ["scope", "verification"])
    assert metrics["scope"]["tp"] == 1
    assert metrics["verification"]["excluded"] == 1
    assert metrics["verification"]["outcomes"]["unchecked"] == 1


def test_existing_explicit_output_is_rejected_before_api(monkeypatch, tmp_path):
    output = tmp_path / "results.jsonl"
    output.write_text('{"old": true}\n')
    monkeypatch.setattr(run_eval.jev, "api_key", lambda: "present")
    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--output", str(output)])
    with pytest.raises(SystemExit, match="choose a fresh --output path"):
        run_eval.main()
    assert output.read_text() == '{"old": true}\n'
