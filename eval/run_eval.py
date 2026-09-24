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
        e.update(final_message=case["final_message"], hunks=case["hunks"],
                 commands_after_last_edit=case["commands"], edited=case["edited"])
    return e


def main():
    dry = "--dry" in sys.argv
    reg = router.load_registry()
    cases = [json.loads(l) for l in open(os.path.join(HERE, "fixtures.jsonl"))]
    if not dry and not jev.api_key():
        sys.exit("no TypeSafe key: set TYPESAFE_API_KEY, or run with --dry")
    rows, out = [], None if dry else open(os.path.join(HERE, "results.jsonl"), "w")
    for c in cases:
        e = evidence_for(c)
        plan = router.identify(reg, c["moment"], e)
        state, qs = router.construct(reg, plan, e)
        if dry:
            print(f"{c['id']:<30} {','.join(plan['decisions']):<45} {len(qs):>3} q  {len(json.dumps(state)):>6} chars")
            continue
        t0 = time.time()
        answers = jev.ask(state, qs, reg["model"])
        dt = time.time() - t0
        resp = router.respond(reg, plan, answers, state)
        got = sorted({r["id"] for r in resp["results"] if r["outcome"] == "block"})
        gated = sorted({r["id"] for r in resp["results"] if r["outcome"] == "gated_out"})
        ok = got == sorted(c["expect"]["block"]) and set(c["expect"].get("gated_out", [])) <= set(gated)
        rows.append((c, got, ok))
        out.write(json.dumps({"id": c["id"], "plan": plan, "answers": answers, "response": resp, "latency_s": dt}) + "\n")
        print(f"{'PASS' if ok else 'FAIL'}  {c['id']:<30} want={c['expect']} got={got} gated={gated}  {dt:.2f}s")
        if not ok:
            for qid, a in answers.items():
                v = a.get("noul", a.get("score", a.get("probabilities", a.get("choice"))))
                print(f"        {qid:<40} {json.dumps(v)}")
    if dry:
        return
    print("\ndecision        caught/should  false-alarms/clean")
    for did in reg["decisions"]:
        moment = reg["decisions"][did]["moment"]
        pool = [r for r in rows if r[0]["moment"] == moment]
        should = [r for r in pool if did in r[0]["expect"]["block"]]
        clean = [r for r in pool if did not in r[0]["expect"]["block"]]
        print(f"{did:<15} {sum(did in r[1] for r in should)}/{len(should):<13} {sum(did in r[1] for r in clean)}/{len(clean)}")
    print(f"\n{sum(r[2] for r in rows)}/{len(rows)} cases match. Raw answers: eval/results.jsonl")


if __name__ == "__main__":
    main()
