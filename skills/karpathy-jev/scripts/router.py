#!/usr/bin/env python3
"""karpathy-jev router: route a moment in an agent's turn to Jev decisions, then respond to them.

  1. identify   code picks the candidate decisions for this moment from the registry
                (by `moment` and by which evidence exists: a request, a diff, any change).
  2. construct  one Jev request: routing questions plus every candidate's questions, over only the
                state paths those decisions declare. Branch questions are asked speculatively.
  3. respond    code applies each decision's gate to the routing answers (unused branches are ignored),
                then its thresholds, and returns one verdict: proceed, or revise with concrete actions.

Two ways in:
  hooks (enforced)   python3 router.py hook                      # stdin: Claude Code / Codex hook JSON
  agent (voluntary)  python3 router.py start --request "..."     # turn_start: request + git baseline
                     python3 router.py decide before_first_edit --said "I'll read X as ..."
                     python3 router.py run -- pytest -q          # records the real exit code
                     python3 router.py decide before_done --final "Done: ..."
Tools:
                     python3 router.py identify before_done      # show plan and request, no API call
                     python3 router.py replay [log.jsonl]        # re-apply edited thresholds, no API call
                     python3 router.py check

Standard library only. Fails open: if Jev cannot be reached the verdict is `unchecked`, never `revise`.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evidence as ev  # noqa: E402
import jev_client as jev  # noqa: E402

REGISTRY_PATH = os.path.join(os.path.dirname(HERE), "decisions.jev.json")
SEP = "__"


def load_registry(path=REGISTRY_PATH):
    with open(path) as f:
        return json.load(f)


def mode():
    m = os.environ.get("KARPATHY_JEV_MODE", "enforce").strip().lower()
    return m if m in ("enforce", "shadow", "off") else "enforce"


def qid(*parts):
    return SEP.join(str(p) for p in parts)


def fill(template, i):
    return json.loads(json.dumps(template).replace("{i}", str(i)))


# --- evidence -> full state ---

def empty_evidence():
    return {"request": None, "messages_before_first_edit": [], "final_message": "", "hunks": [],
            "commands_after_last_edit": [], "edited": False}


def full_state(reg, e):
    d = reg["decisions"]
    max_hunks = d["scope"]["thresholds"].get("max_hunks", 20)
    max_cmds = d["verification"]["thresholds"].get("max_commands", 15)
    return {
        "request": e["request"],
        "agent_said": {"messages_before_first_edit": e["messages_before_first_edit"],
                       "final_message": e["final_message"]},
        "observed": {"hunks": e["hunks"][:max_hunks], "commands_after_last_edit": e["commands_after_last_edit"][:max_cmds]},
    }


def facts(e):
    return {"request": bool(e["request"]), "hunks": bool(e["hunks"]), "changed": bool(e["hunks"]) or e["edited"]}


# --- 1. identify ---

def identify(reg, moment, e):
    f = facts(e)
    plan = {"moment": moment, "decisions": [], "skipped": [], "routes": []}
    for did, d in reg["decisions"].items():
        if d["moment"] != moment:
            continue
        missing = [n for n in d.get("needs", []) if not f.get(n)]
        if missing:
            plan["skipped"].append({"id": did, "why": "no " + ", ".join(missing)})
        else:
            plan["decisions"].append(did)
    plan["routes"] = sorted({reg["decisions"][did]["gate"]["route"] for did in plan["decisions"]
                             if reg["decisions"][did].get("gate")})
    return plan


# --- 2. construct ---

def _get(obj, path):
    for part in path.split("."):
        obj = obj[part]
    return obj


def _put(obj, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        obj = obj.setdefault(part, {})
    obj[parts[-1]] = value


def construct(reg, plan, e):
    full = full_state(reg, e)
    paths, questions = set(), {}
    for route in plan["routes"]:
        questions[qid("route", route)] = copy.deepcopy(reg["routing"][route])
        paths.add("request")
    hunks = full["observed"]["hunks"]
    commands = full["observed"]["commands_after_last_edit"]
    for did in plan["decisions"]:
        d = reg["decisions"][did]
        paths.update(d["evidence"])
        for name, q in d.get("questions", {}).items():
            questions[qid(did, name)] = copy.deepcopy(q)
        for i in range(len(hunks)):
            for name, q in d.get("per_hunk_questions", {}).items():
                questions[qid(did, f"h{i}", name)] = fill(q, i)
        for i in range(len(commands)):
            for name, q in d.get("per_command_questions", {}).items():
                questions[qid(did, f"c{i}", name)] = fill(q, i)
    state = {}
    for p in sorted(paths):
        _put(state, p, _get(full, p))
    return state, questions


# --- 3. respond ---

def view(answers, prefix):
    """Answers for one decision, with its namespace stripped."""
    n = len(prefix) + len(SEP)
    return {k[n:]: v for k, v in answers.items() if k.startswith(prefix + SEP)}


def gate(reg, did, answers):
    """(open, p) for a decision's gate. A missing routing answer leaves the gate open."""
    g = reg["decisions"][did].get("gate")
    if not g:
        return True, None
    p = jev.prob(answers, qid("route", g["route"]), g["option"])
    if p is None:
        return True, None
    if "at_least" in g:
        return p >= g["at_least"], p
    return p < g["below"], p


def _r(v):
    return round(v, 3) if isinstance(v, float) else v


def out(outcome, message="", **evidence):
    return {"outcome": outcome, "message": message, "evidence": {k: _r(v) for k, v in evidence.items()}}


def in_band(v, band):
    return v is not None and band[0] <= v < band[1]


def respond_ambiguity(d, a, state):
    th = d["thresholds"]
    p_many = jev.prob(a, "interpretations", "several_material")
    stated = jev.noul(a, "assumptions_stated")
    if p_many is None or stated is None:
        return []
    if p_many >= th["several_material_min_prob"]:
        if stated <= th["assumptions_stated_max"]:
            return [out("block", d["respond"][0]["message"], several_material=p_many, assumptions_stated=stated)]
        if in_band(stated, th["review_band"]):
            return [out("review", "near threshold", several_material=p_many, assumptions_stated=stated)]
    return []


def respond_simplicity(d, a, state):
    th, res = d["thresholds"], []
    for name, key, rule in (("speculative_feature", "speculative_feature_min", 0),
                            ("single_use_abstraction", "single_use_abstraction_min", 1)):
        v = jev.noul(a, name)
        if v is not None and v >= th[key]:
            res.append(out("block", d["respond"][rule]["message"], **{name: v}))
        elif in_band(v, th["review_band"]):
            res.append(out("review", "near threshold", **{name: v}))
    sz = jev.score(a, "size_vs_need")
    if sz is not None and sz >= th["size_vs_need_min"]:
        res.append(out("block", d["respond"][2]["message"], size_vs_need=sz))
    return res


def respond_scope(d, a, state):
    th, res = d["thresholds"], []
    labels = [k for k in d["per_hunk_questions"] if k != "extra_lines"]
    for i, h in enumerate(state["observed"]["hunks"]):
        extra = jev.noul(a, qid(f"h{i}", "extra_lines"))
        hits = {k: jev.noul(a, qid(f"h{i}", k)) for k in labels}
        flagged = [k.replace("_", " ") for k, v in hits.items() if v is not None and v >= th["label_min"]]
        if (extra is not None and extra >= th["extra_lines_min"]) or flagged:
            msg = d["respond"][0]["message"].format(
                file=h["file"], hunk=h["header"], reasons=", ".join(flagged) or "changes lines the request does not need")
            res.append(out("block", msg, file=h["file"], hunk=h["header"], extra_lines=extra,
                           **{k: v for k, v in hits.items() if v is not None}))
        elif in_band(extra, th["review_band"]):
            res.append(out("review", "near threshold", file=h["file"], extra_lines=extra))
    return res


def respond_verification(d, a, state):
    th = d["thresholds"]
    commands = state["observed"]["commands_after_last_edit"]
    verified = any((jev.noul(a, qid(f"c{i}", "exercises")) or 0) >= th["exercises_min"] and c["result"] == "ok"
                   for i, c in enumerate(commands))
    claims = jev.noul(a, "claims_done") or 0
    admits = jev.noul(a, "admits_unverified") or 0
    if verified:
        return []
    if claims >= th["claims_done_min"] and admits < th["admits_unverified_max"]:
        return [out("block", d["respond"][0]["message"], claims_done=claims, admits_unverified=admits,
                    commands_after_last_edit=len(commands))]
    if in_band(claims, th["review_band"]):
        return [out("review", "near threshold", claims_done=claims)]
    return []


def respond_repro_test(d, a, state):
    hunks = state["observed"]["hunks"]
    if hunks and not any(ev.TEST_PATH.search(h["file"]) for h in hunks):
        return [out("advise", d["respond"][0]["message"])]
    return []


RESPONDERS = {"ambiguity": respond_ambiguity, "simplicity": respond_simplicity, "scope": respond_scope,
              "verification": respond_verification, "repro_test": respond_repro_test}


def respond(reg, plan, answers, state):
    results = []
    for did in plan["decisions"]:
        d = reg["decisions"][did]
        base = {"id": did, "principle": d["principle"]}
        opened, p = gate(reg, did, answers)
        if not opened:
            results.append({**base, **out("gated_out", d["gate"]["why"], **{d["gate"]["option"]: p})})
            continue
        outs = RESPONDERS[did](d, view(answers, did), state)
        results += [{**base, **o} for o in outs] or [{**base, **out("pass")}]
    for s in plan["skipped"]:
        d = reg["decisions"][s["id"]]
        results.append({"id": s["id"], "principle": d["principle"], **out("skipped", s["why"])})
    verdict = "revise" if any(r["outcome"] == "block" for r in results) else "proceed"
    return {"moment": plan["moment"], "verdict": verdict, "results": results}


def render(response):
    lines = ["karpathy-jev (Jev judged observed evidence; code decided):"]
    lines += [f"- [{r['principle']}] {r['message']}" for r in response["results"] if r["outcome"] == "block"]
    lines += [f"- [{r['principle']}, advice] {r['message']}" for r in response["results"] if r["outcome"] == "advise"]
    lines.append("Fix what applies. If a point is wrong, say why in one line, then continue.")
    return "\n".join(lines)


# --- run a moment end to end, with logging ---

def log(entry):
    try:
        os.makedirs(jev.home(), exist_ok=True)
        if os.environ.get("KARPATHY_JEV_LOG_STATE", "1") != "1":
            entry.pop("state", None)
        with open(os.path.join(jev.home(), "log.jsonl"), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def route(reg, moment, e, session=None, dry=False):
    t0 = time.time()
    plan = identify(reg, moment, e)
    state, questions = construct(reg, plan, e)
    if dry:
        return {"moment": moment, "verdict": "dry_run", "plan": plan, "request": {"state": state, "questions": questions}}
    entry = {"ts": t0, "moment": moment, "session": session, "mode": mode(), "plan": plan, "state": state,
             "n_questions": len(questions)}
    if not questions:
        response = respond(reg, plan, {}, state)
    else:
        try:
            answers = jev.ask(state, questions, os.environ.get("KARPATHY_JEV_MODEL", reg.get("model", "jev-latest")))
        except Exception as err:  # fail open
            response = {"moment": moment, "verdict": "unchecked", "error": str(err)[:300], "results": []}
            log({**entry, "response": response, "latency_s": round(time.time() - t0, 3)})
            return response
        entry["answers"] = answers
        response = respond(reg, plan, answers, state)
    log({**entry, "response": response, "latency_s": round(time.time() - t0, 3)})
    return response


def replay(log_path, reg):
    changed, total = [], 0
    for line in open(log_path):
        entry = json.loads(line)
        if "answers" not in entry or "state" not in entry:
            continue
        total += 1
        now = respond(reg, entry["plan"], entry["answers"], entry["state"])
        was = sorted({r["id"] for r in entry["response"]["results"] if r["outcome"] == "block"})
        new = sorted({r["id"] for r in now["results"] if r["outcome"] == "block"})
        if was != new:
            changed.append({"ts": entry["ts"], "moment": entry["moment"], "was": was, "now": new})
    return {"replayed": total, "changed": changed}


# --- sessions ---

def _session_path(sid):
    return os.path.join(jev.home(), "sessions", hashlib.sha1((sid or "default").encode()).hexdigest()[:16] + ".json")


def load_session(sid):
    try:
        with open(_session_path(sid)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_session(sid, data):
    path = _session_path(sid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def start_turn(sid, cwd, request):
    try:
        snap = ev.snapshot(cwd)
    except Exception:
        snap = None
    save_session(sid, {"user_request": (request or "")[: ev.MAX_MSG_CHARS], "baseline": snap,
                       "first_edit_routed": False, "cwd": cwd, "ts": time.time()})


def _hunks(cwd, sess):
    try:
        return ev.turn_hunks(cwd, sess.get("baseline"))
    except Exception:
        return []


# --- hook mode (enforced) ---

def hook_main(hook, reg):
    event = hook.get("hook_event_name")
    sid, cwd = hook.get("session_id"), hook.get("cwd") or os.getcwd()
    if event == "UserPromptSubmit":
        start_turn(sid, cwd, hook.get("prompt"))
        return 0, ""
    if event == "PreToolUse":
        if hook.get("tool_name") not in ev.EDIT_TOOLS:
            return 0, ""
        sess = load_session(sid)
        if sess.get("first_edit_routed"):
            return 0, ""
        sess["first_edit_routed"] = True
        save_session(sid, sess)
        turn = ev.read_turn(hook.get("transcript_path"))
        e = {**empty_evidence(), "request": sess.get("user_request") or turn["request"],
             "messages_before_first_edit": turn["messages_before_first_edit"]}
        response = route(reg, "before_first_edit", e, sid)
    elif event == "Stop":
        if hook.get("stop_hook_active"):
            return 0, ""
        sess = load_session(sid)
        turn = ev.read_turn(hook.get("transcript_path"))
        e = {**empty_evidence(), "request": sess.get("user_request") or turn["request"],
             "final_message": turn["final_message"], "hunks": _hunks(cwd, sess),
             "commands_after_last_edit": turn["commands_after_last_edit"], "edited": turn["edited"]}
        if not facts(e)["changed"]:
            return 0, ""
        response = route(reg, "before_done", e, sid)
    else:
        return 0, ""
    if response["verdict"] == "revise" and mode() == "enforce":
        return 2, render(response)
    return 0, ""


# --- agent mode (voluntary) ---

AGENT_SESSION = "agent-mode"


def agent_decide(reg, moment, args):
    cwd = os.getcwd()
    sess = load_session(AGENT_SESSION)
    request = args.request or sess.get("user_request")
    e = {**empty_evidence(), "request": request}
    if moment == "before_first_edit":
        e["messages_before_first_edit"] = args.said or []
    elif moment == "before_done":
        hunks = _hunks(cwd, sess)
        runs = os.path.join(jev.home(), "runs.jsonl")
        e.update(final_message=args.final or "", hunks=hunks, edited=bool(hunks),
                 commands_after_last_edit=ev.runs_after_last_edit(runs, cwd, hunks))
    else:
        raise SystemExit(f"unknown moment {moment!r}; choose from {sorted(reg['moments'])}")
    return route(reg, moment, e, AGENT_SESSION, dry=args.dry)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="router.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook")
    sub.add_parser("check")
    s = sub.add_parser("start")
    s.add_argument("--request", required=True)
    for name in ("decide", "identify"):
        p = sub.add_parser(name)
        p.add_argument("moment")
        p.add_argument("--request")
        p.add_argument("--said", action="append")
        p.add_argument("--final")
        p.add_argument("--dry", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("command", nargs=argparse.REMAINDER)
    rp = sub.add_parser("replay")
    rp.add_argument("log", nargs="?")
    args = ap.parse_args(argv)
    reg = load_registry()

    if args.cmd == "check":
        print(json.dumps({"mode": mode(), "key": bool(jev.api_key()), "home": jev.home(),
                          "registry": REGISTRY_PATH, "decisions": list(reg["decisions"])}, indent=2))
        return 0
    if args.cmd == "replay":
        print(json.dumps(replay(args.log or os.path.join(jev.home(), "log.jsonl"), reg), indent=2))
        return 0
    if args.cmd == "run":
        cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
        return ev.run_recorded(cmd, os.path.join(jev.home(), "runs.jsonl"))
    if args.cmd == "start":
        start_turn(AGENT_SESSION, os.getcwd(), args.request)
        runs = os.path.join(jev.home(), "runs.jsonl")
        if os.path.exists(runs):
            os.remove(runs)
        print(json.dumps({"moment": "turn_start", "recorded": True}))
        return 0
    if args.cmd in ("decide", "identify"):
        if args.cmd == "identify":
            args.dry = True
        response = agent_decide(reg, args.moment, args)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        if response["verdict"] == "revise":
            print("\n" + render(response), file=sys.stderr)
            return 2 if mode() == "enforce" else 0
        return 0
    if mode() == "off":
        return 0
    try:  # hook
        code, msg = hook_main(json.load(sys.stdin), reg)
    except Exception as err:  # never break the agent
        log({"ts": time.time(), "moment": "crash", "error": str(err)[:300]})
        return 0
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
