# karpathy-jev

The [Karpathy coding guidelines](https://github.com/multica-ai/andrej-karpathy-skills) as a **skill bundle with
a decision router**. The agent does the work. At fixed moments in each turn, the router checks the
guidelines instead of the agent grading itself, using [TypeSafe Jev](https://docs.typesafe.ai) for the
judgments and code for everything else:

```
moment ──► 1. identify ──► 2. construct ──► Jev ──► 3. respond ──► proceed | revise
           which decisions    one request: routing   typed      gates + thresholds
           apply (code)       + branch questions,    answers    in code, one verdict
                              declared evidence only            with concrete actions
```

| Moment | Decisions | Guideline |
|---|---|---|
| `before_first_edit` | `ambiguity` | Think before coding |
| `before_done` | `simplicity` | Simplicity first |
| | `scope` (five Nouls per hunk) | Surgical changes |
| | `verification`, gated out when P(non-code task) ≥ 0.6 | Goal-driven execution |
| | `repro_test`, only when P(bug fix) ≥ 0.6 | Goal-driven execution |

## Bundle layout

```
skills/karpathy-jev/            ← the skill (copy this folder into any agent's skills directory)
  SKILL.md                      generated: what the router does, when to call it, how to respond
  decisions.jev.json            the registry: moments, routing questions, decisions, gates, thresholds, messages
  scripts/router.py             identify → construct → respond; hook entry and agent CLI
  scripts/evidence.py           observed evidence: transcripts, git diff since turn start, recorded runs
  scripts/jev_client.py         one POST to /v1/systemone; offline fake; typed readers
  scripts/build_skill.py        renders SKILL.md and references/decisions.md from the registry
  references/decisions.md       generated: every question, criterion, gate and threshold
  references/design.md          stage contracts, adding a decision, TypeSafe guidance mapping, limits
hooks/hooks.json                UserPromptSubmit / PreToolUse / Stop → router.py hook
.claude-plugin/                 plugin + marketplace manifests
eval/                           EXAMPLES.md turned into 21 labeled cases, run through the full router
tests/                          42 offline tests
```

The registry is the single source of truth. To change a question, gate, threshold or message, edit
`decisions.jev.json` and run `python3 skills/karpathy-jev/scripts/build_skill.py`. The tests fail if the
generated files are stale.

## Install

You need a TypeSafe key with Jev access (`export TYPESAFE_API_KEY=apikey_...`, or put the key in
`~/.karpathy-jev/key`) and Python 3.9+. Only the standard library is used.

- **Claude Code (enforced):** install this repo as a plugin. The hooks call the router at every moment.
- **Codex:** add the `Stop` entry from `hooks/hooks.json` to `~/.codex/hooks.json`, pointing at `router.py hook`.
  The `before_done` moment works from Codex transcripts. `UserPromptSubmit` and `PreToolUse` are unverified
  on Codex.
- **Any other agent (voluntary):** copy `skills/karpathy-jev/` into its skills folder. SKILL.md tells the
  agent to call `router.py start / decide / run` at the same moments. This is weaker than hooks, because the
  agent chooses when to call.

Check the setup with `python3 skills/karpathy-jev/scripts/router.py check`. Modes: `KARPATHY_JEV_MODE=enforce`
(default), `shadow` (log only), or `off`.

## Evaluate and calibrate

```bash
python3 eval/run_eval.py --dry                      # identify + construct every case, no API call
TYPESAFE_API_KEY=... python3 eval/run_eval.py       # per-decision catches and false alarms; answers on failure
python3 skills/karpathy-jev/scripts/router.py replay   # re-decide logged moments under edited thresholds
python3 -m pytest -q tests
```

The thresholds are starting points and have **not** been run against live Jev. Run the eval first, then
label the `review` outcomes in `~/.karpathy-jev/log.jsonl` and refit.

## Credits

Guidelines and examples: [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
(MIT, commit 2c60614), from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876).
Question design follows [typesafe-ai/skills](https://github.com/typesafe-ai/skills) (MIT, commit 65a39f3). Hook
and transcript patterns follow [limpet](https://github.com/noplan-inc/limpet).
