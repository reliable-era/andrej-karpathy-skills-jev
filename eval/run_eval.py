#!/usr/bin/env python3
"""Run the EXAMPLES.md fixtures through the full router: identify -> construct -> Jev -> respond.

  TYPESAFE_API_KEY=... python3 eval/run_eval.py   # live
  python3 eval/run_eval.py --dry                   # identify + construct only, no API call

Checks which decisions block and, where a case says so, which are gated out. Raw answers go to
eval/results.jsonl so thresholds can be refit without re-calling the API.
"""
import json
import os
import sys
import time
import argparse
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "karpathy-jev", "scripts"))
import jev_client as jev  # noqa: E402
import router  # noqa: E402


def evidence_for(case):
    e = router.empty_evidence()
    e["request"] = case["request"]
    if case["moment"] == "before_first_edit":
        e["messages_before_first_edit"] = case["messages"]
    else:
        e.update(final_message=case["final_message"], hunks=case["hunks"], edited=case["edited"],
                 commands_on_unfixed_code=case.get("commands_before", []), commands_after_last_edit=case["commands"])
    return e


def decision_metrics(rows, cases, decisions):
    """Aggregate independent case-level decisions; multiple blocks count once per case."""
    expected = {c["id"]: set(c["expect"].get("block", [])) for c in cases}
    metrics = {}
    for did in decisions:
        outcomes = {k: 0 for k in ("pass", "block", "review", "advise", "gated_out", "skipped", "unchecked")}
        considered = []
        excluded = 0
        for case, got, ok, response in rows:
            result = [r for r in response.get("results", []) if r["id"] == did]
            if response.get("verdict") == "unchecked" or not result:
                if result:
                    outcomes["unchecked"] += 1
                excluded += 1
                continue
            if any(r["outcome"] == "unchecked" for r in result):
                outcomes["unchecked"] += 1
                excluded += 1
                continue
            for item in result:
                if item["outcome"] in outcomes:
                    outcomes[item["outcome"]] += 1
            considered.append((case["id"], any(r["outcome"] == "block" for r in result)))
        considered_ids = {cid for cid, _ in considered}
        actual = {cid for cid, blocked in considered if blocked}
        positives = {cid for cid in considered_ids if did in expected[cid]}
        if outcomes["unchecked"] == 0:
            del outcomes["unchecked"]
        metrics[did] = {
            "cases": len(considered), "excluded": excluded,
            "tp": len(actual & positives), "fp": len(actual - positives),
            "fn": len(positives - actual), "outcomes": outcomes,
        }
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Run the EXAMPLES.md fixtures through Jev.")
    parser.add_argument("--dry", action="store_true", help="identify and construct only; do not call the API")
    parser.add_argument("--output", default=None,
                        help="JSONL output path (default: eval/results.jsonl)")
    args = parser.parse_args()
    dry = args.dry
    reg = router.load_registry()
    fixture_path = os.path.join(HERE, "fixtures.jsonl")
    cases = [json.loads(l) for l in open(fixture_path)]
    fixture_sha256 = hashlib.sha256(open(fixture_path, "rb").read()).hexdigest()
    if not dry and not jev.api_key():
        sys.exit("no TypeSafe key: set TYPESAFE_API_KEY, or run with --dry")
    output_path = args.output or os.path.join(HERE, "results.jsonl")
    if not dry and os.path.exists(output_path):
        raise SystemExit(f"output exists: {output_path}; choose a fresh --output path")
    output_mode = "x"
    rows, out = [], None if dry else open(output_path, output_mode)
    for c in cases:
        e = evidence_for(c)
        plan = router.identify(reg, c["moment"], e)
        state, qs = router.construct(reg, plan, e)
        if dry:
            print(f"{c['id']:<30} {','.join(plan['decisions']):<45} {len(qs):>3} q  {len(json.dumps(state)):>6} chars")
            continue
        t0 = time.time()
        error = None
        try:
            answers = jev.ask(state, qs, reg["model"])
        except Exception as err:
            answers = {}
            error = str(err)[:300]
        dt = time.time() - t0
        resp = (router.respond(reg, plan, answers, state) if error is None else
                {"moment": c["moment"], "verdict": "unchecked", "error": error, "results": []})
        got = sorted({r["id"] for r in resp["results"] if r["outcome"] == "block"})
        gated = sorted({r["id"] for r in resp["results"] if r["outcome"] == "gated_out"})
        comparable = error is None and not any(r["outcome"] == "unchecked" for r in resp.get("results", []))
        ok = comparable and got == sorted(c["expect"]["block"]) and set(c["expect"].get("gated_out", [])) <= set(gated)
        rows.append((c, got, ok, resp))
        out.write(json.dumps({"id": c["id"], "plan": plan, "answers": answers, "response": resp,
                             "requested_model": reg["model"],
                             "response_model": jev.last_response_model, "fixture_sha256": fixture_sha256,
                             "latency_s": dt}) + "\n")
        label = "PASS" if ok else "ERROR" if error else "FAIL"
        print(f"{label}  {c['id']:<30} want={c['expect']} got={got} gated={gated}  {dt:.2f}s")
        if not ok:
            for qid, a in answers.items():
                v = a.get("noul", a.get("score", a.get("probabilities", a.get("choice"))))
                print(f"        {qid:<40} {json.dumps(v)}")
    if dry:
        return
    out.close()
    print("\ndecision        caught/should  false-alarms/clean")
    for did in reg["decisions"]:
        moment = reg["decisions"][did]["moment"]
        m = decision_metrics(rows, cases, [did])[did]
        print(f"{did:<15} TP={m['tp']} FP={m['fp']} FN={m['fn']} cases={m['cases']} excluded={m['excluded']} outcomes={m['outcomes']}")
    errors = sum(r[3].get("verdict") == "unchecked" for r in rows)
    print(f"\n{sum(r[2] for r in rows)}/{len(rows)} cases exact-match; unchecked/errors={errors}. Raw answers: {output_path}")


if __name__ == "__main__":
    main()
