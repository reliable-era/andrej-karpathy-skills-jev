import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "karpathy-jev", "scripts"))
import router  # noqa: E402


REG = router.load_registry()


def noul(value):
    return {"type": "noul", "noul": value}


def choice(options):
    return {"type": "choice", "choice": options[0],
            "confidence": 1.0, "probabilities": {k: 1.0 if k == options[0] else 0.0 for k in options}}


def test_missing_active_answer_is_unchecked_instead_of_pass():
    evidence = {**router.empty_evidence(), "request": "r"}
    plan = router.identify(REG, "before_first_edit", evidence)
    state, _ = router.construct(REG, plan, evidence)
    answers = {"ambiguity__interpretations": choice(["one_clear", "minor_variants", "several_material"])}
    response = router.respond(REG, plan, answers, state)
    assert response["verdict"] == "unchecked"
    assert response["results"][0]["outcome"] == "unchecked"
    assert "assumptions_stated" in response["error"]


def test_complete_active_answers_keep_normal_policy_result():
    evidence = {**router.empty_evidence(), "request": "r"}
    plan = router.identify(REG, "before_first_edit", evidence)
    state, _ = router.construct(REG, plan, evidence)
    answers = {
        "ambiguity__interpretations": choice(["one_clear", "minor_variants", "several_material"]),
        "ambiguity__assumptions_stated": noul(1.0),
    }
    response = router.respond(REG, plan, answers, state)
    assert response["verdict"] == "proceed"
    assert response["results"][0]["outcome"] == "pass"


def test_malformed_active_answer_is_unchecked():
    evidence = {**router.empty_evidence(), "request": "r"}
    plan = router.identify(REG, "before_first_edit", evidence)
    state, _ = router.construct(REG, plan, evidence)
    answers = {
        "ambiguity__interpretations": choice(["one_clear", "minor_variants", "several_material"]),
        "ambiguity__assumptions_stated": {"type": "noul", "noul": "certain"},
    }
    response = router.respond(REG, plan, answers, state)
    assert response["verdict"] == "unchecked"
    assert "assumptions_stated" in response["error"]


def test_closed_gate_does_not_require_ignored_branch_answers():
    plan = {"moment": "before_done", "decisions": ["verification"], "skipped": [], "routes": ["task_kind"]}
    state = {"request": "docs", "agent_said": {"final_message": "Done."},
             "observed": {"hunks": [], "commands_after_last_edit": []}}
    answers = {
        "route__task_kind": choice(["non_code", "bug_fix", "new_behavior", "refactor", "other"]),
        "verification__claims_done": noul(1.0),
        "verification__admits_unverified": noul(0.0),
    }
    response = router.respond(REG, plan, answers, state)
    assert response["verdict"] == "proceed"
    assert response["results"][0]["outcome"] == "gated_out"


def _ambiguity_verdict(interpretations):
    evidence = {**router.empty_evidence(), "request": "r"}
    plan = router.identify(REG, "before_first_edit", evidence)
    state, _ = router.construct(REG, plan, evidence)
    answers = {"ambiguity__interpretations": interpretations, "ambiguity__assumptions_stated": noul(1.0)}
    return router.respond(REG, plan, answers, state)["verdict"]


def test_choice_probabilities_must_cover_exactly_the_offered_options():
    answer = {"type": "choice", "choice": "one_clear", "confidence": 1.0, "probabilities": {"one_clear": 1.0}}
    assert _ambiguity_verdict(answer) == "unchecked"


def test_choice_probabilities_must_sum_to_one():
    answer = {"type": "choice", "choice": "one_clear", "confidence": 1.0,
              "probabilities": {"one_clear": 0.9, "minor_variants": 0.9, "several_material": 0.0}}
    assert _ambiguity_verdict(answer) == "unchecked"


def test_choice_must_be_the_most_probable_option():
    answer = {"type": "choice", "choice": "one_clear", "confidence": 0.7,
              "probabilities": {"one_clear": 0.2, "minor_variants": 0.1, "several_material": 0.7}}
    assert _ambiguity_verdict(answer) == "unchecked"


def test_score_off_the_rubric_is_invalid():
    q = {"type": "score", "criteria": ["low", "mid", "high"]}
    assert router._answer_valid(q, {"type": "score", "score": 2.5})
    assert not router._answer_valid(q, {"type": "score", "score": 2.6})
    assert not router._answer_valid(q, {"type": "score", "score": -0.6})
