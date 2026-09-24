#!/usr/bin/env python3
"""Render SKILL.md and references/decisions.md from decisions.jev.json.

SKILL.md stays short (what the router does, when to call it, how to respond). The exact questions,
thresholds and messages go to references/decisions.md. Both come from the registry the router runs on,
so the skill cannot drift from the checks.

  python3 scripts/build_skill.py          # write both files
  python3 scripts/build_skill.py --check  # exit 1 if either is stale
"""
import json
import os
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(SKILL, "decisions.jev.json")
OUT_SKILL = os.path.join(SKILL, "SKILL.md")
OUT_REF = os.path.join(SKILL, "references", "decisions.md")
NEEDS = {"request": "a request", "hunks": "a diff", "changed": "any file change"}
GEN = "<!-- Generated from decisions.jev.json by scripts/build_skill.py. Edit the registry, then rebuild. -->"


def items(xs):
    return "; ".join(text(x).rstrip(".") for x in xs) + "."


def text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.replace("[{i}]", "[i]")
    if isinstance(v, list):
        return items(v)
    lead = [text(v[k]) for k in ("premise", "question", "means") if k in v]
    rest = [f"*{k.replace('_', ' ').capitalize()}:* " + (items(x) if isinstance(x, list) else text(x))
            for k, x in v.items() if k not in ("premise", "question", "means")]
    return " ".join(lead + rest)


def question_lines(qid, q, scope=""):
    lines = [f"- **`{qid}`** ({q['type'].capitalize()}{scope}): {text(q['instructions'])}"]
    c = q.get("criteria")
    if q["type"] == "choice":
        lines += [f"  - `{k}`: {text(v)}" for k, v in c.items()]
    elif q["type"] == "score":
        lines += [f"  - level {i}: {text(v)}" for i, v in enumerate(c)]
    elif c:
        lines += [f"  - yes: {text(c.get('true'))}", f"  - no: {text(c.get('false'))}"]
    return lines


def skill_md(r):
    moments = r["moments"]
    by_moment = {}
    for did, d in r["decisions"].items():
        by_moment.setdefault(d["moment"], []).append(did)
    rows = []
    for m, spec in moments.items():
        ds = ", ".join(f"`{x}`" for x in by_moment.get(m, [])) or "none (records the request and a git baseline)"
        rows.append(f"| `{m}` | {spec['when']} | {ds} | {spec['hook']} |")
    decision_rows = []
    for did, d in r["decisions"].items():
        g = d.get("gate")
        gate = f"only if P({g['route']} = {g['option']}) {'≥ ' + str(g['at_least']) if 'at_least' in g else '< ' + str(g['below'])}" if g else "always"
        needs = " and ".join(NEEDS[n] for n in d["needs"])
        decision_rows.append(f"| `{did}` | {r['principles'][d['principle']]['title']} | {needs} exists; {gate} |")
    principles = []
    for p in r["principles"].values():
        principles.append(f"**{p['title']}.** {p['rule']} *Passes when:* {p['passes_when']}")

    return f"""---
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

{GEN}

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
{chr(10).join(rows)}

| Decision | Guideline | Routed when |
|---|---|---|
{chr(10).join(decision_rows)}

Branch questions are asked speculatively in the same request as the routing question. A decision whose
gate stays closed is reported as `gated_out` and its answers are ignored.

## Responding to a decision

- **`proceed`**: continue. Outcomes of `review` are logged for calibration and need nothing from you.
- **`revise`**: each `block` names what fired and why. For each one, fix it, or if it is wrong, say why in
  one line to the user. Then continue. Each moment pushes back at most once per turn, so a false alarm
  costs one sentence. `advise` outcomes are suggestions.
- **`unchecked`**: Jev was unreachable. Nothing was judged. Do not describe the work as verified by it.

## The guidelines

{(chr(10) * 2).join(principles)}

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
"""


def reference_md(r):
    out = ["# Decisions", "", GEN, "",
           "Every question below is sent to Jev under a namespaced id: `route__<id>` for routing questions,",
           "`<decision>__<question>` for a decision's questions, and `<decision>__h<i>__<question>` or",
           "`<decision>__c<i>__<question>` for per-hunk and per-command questions.", "",
           "## Routing questions", ""]
    for rid, q in r["routing"].items():
        out += question_lines(rid, q)
    for did, d in r["decisions"].items():
        p = r["principles"][d["principle"]]
        out += ["", f"## `{did}` ({p['title']})", "", f"**{p['rule']}**", "",
                f"- **Moment:** `{d['moment']}`",
                f"- **Needs:** {', '.join(d['needs'])}"]
        if d.get("gate"):
            g = d["gate"]
            cond = f"≥ {g['at_least']}" if "at_least" in g else f"< {g['below']}"
            out.append(f"- **Gate:** P(`{g['route']}` = `{g['option']}`) {cond}: {g['why']}")
        out.append("- **Evidence:** " + ", ".join(f"`{x}`" for x in d["evidence"]))
        if d.get("questions") or d.get("per_hunk_questions") or d.get("per_command_questions"):
            out += ["", "**Questions**", ""]
            for qid, q in d.get("questions", {}).items():
                out += question_lines(qid, q)
            for qid, q in d.get("per_hunk_questions", {}).items():
                out += question_lines(qid, q, ", per hunk")
            for qid, q in d.get("per_command_questions", {}).items():
                out += question_lines(qid, q, ", per command")
        out += ["", "**Respond**", ""]
        out += [f"- `{x['outcome']}` if `{x['if']}`: {x['message']}" for x in d["respond"]]
        if d.get("thresholds"):
            out += ["", "**Thresholds:** " + ", ".join(f"`{k}` = {v}" for k, v in d["thresholds"].items())]
    out += ["", "## Not checked (still expected)", ""]
    for p in r["principles"].values():
        out += [f"- **{p['title']}:** " + " ".join(p["not_checked"])]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    reg = json.load(open(REG))
    files = {OUT_SKILL: skill_md(reg), OUT_REF: reference_md(reg)}
    if "--check" in sys.argv:
        stale = [p for p, body in files.items() if not os.path.exists(p) or open(p).read() != body]
        sys.exit(1 if stale else 0)
    for path, body in files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(body)
        print(f"wrote {os.path.relpath(path, SKILL)} ({len(body.splitlines())} lines)")
