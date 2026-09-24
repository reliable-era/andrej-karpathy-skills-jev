"""Evidence collection: what the router may show Jev. Everything here is observed, not claimed.

- Transcripts (Claude Code and Codex JSONL): the request, what the agent said, tool calls and their status.
- Git: the diff since a baseline snapshot taken when the turn started, plus files created during the turn.
- Recorded runs (agent mode, no transcript): commands executed through `router.py run`, with real exit codes.
"""
import json
import os
import re
import subprocess
import time

MAX_HUNK_CHARS = 1500
MAX_MSG_CHARS = 2000
NEW_FILE_LINES = 80
TAIL_BYTES = 768 * 1024

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "str_replace_based_edit_tool"}
COMMAND_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "container.exec"}
HARNESS_PREFIXES = (
    "Stop hook feedback", "PreToolUse:", "PostToolUse:", "[Request interrupted", "[Image:", "Caveat: The messages below",
    "API Error", "Another Claude session sent", "# AGENTS.md instructions", "The following is the Codex agent history",
)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.\w+$|\.(test|spec)\.\w+$")


# --- transcripts (Claude Code and Codex JSONL) ---

def _rows(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        start = max(0, os.path.getsize(path) - TAIL_BYTES)
        f.seek(start)
        text = f.read().decode("utf-8", "replace")
    if start:
        text = text.split("\n", 1)[-1]
    rows = []
    for line in text.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def _clean_human(s):
    s = (s or "").strip()
    if not s or s.startswith("<") or s.startswith(HARNESS_PREFIXES):
        return None
    return s


def human_text(d):
    if d.get("type") == "response_item":  # Codex
        p = d.get("payload") or {}
        if p.get("type") != "message" or p.get("role") != "user":
            return None
        c = p.get("content") or []
        return _clean_human("\n".join(b.get("text", "") for b in c if isinstance(b, dict)))
    if d.get("type") != "user":
        return None
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return _clean_human(c) if isinstance(c, str) else None


def assistant_text(d):
    if d.get("type") == "response_item":
        p = d.get("payload") or {}
        if p.get("type") != "message" or p.get("role") != "assistant":
            return None
        c = p.get("content") or []
    elif d.get("type") == "assistant":
        c = (d.get("message") or {}).get("content")
    else:
        return None
    if not isinstance(c, list):
        return None
    s = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
    return s.strip() or None


def _command_of(name, inp):
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except ValueError:
            return inp
    if not isinstance(inp, dict):
        return ""
    c = inp.get("command") or inp.get("cmd") or ""
    if isinstance(c, list):  # Codex: ["bash", "-lc", "pytest -q"]
        c = c[-1] if c else ""
    return str(c)


def _codex_status(output):
    text = output if isinstance(output, str) else json.dumps(output)
    try:
        meta = json.loads(text).get("metadata") or {}
        if isinstance(meta.get("exit_code"), int):
            return "ok" if meta["exit_code"] == 0 else "error"
    except (ValueError, AttributeError):
        pass
    m = re.search(r"(?:exit[_ ]code\"?:?\s*)(-?\d+)", text, re.I)
    if m:
        return "ok" if int(m.group(1)) == 0 else "error"
    return "unknown"


def read_turn(path):
    """The current turn: request, assistant messages, and tool calls in order with their status."""
    rows = _rows(path)
    start = 0
    request = None
    for j in range(len(rows) - 1, -1, -1):
        h = human_text(rows[j])
        if h:
            start, request = j, h
            break
    calls, status, texts = [], {}, []
    for d in rows[start:]:
        t = assistant_text(d)
        if t:
            texts.append((len(calls), t))
        if d.get("type") == "response_item":
            p = d.get("payload") or {}
            if p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                name = p.get("name") or ("local_shell" if p.get("type") == "local_shell_call" else "")
                args = p.get("arguments") or p.get("input") or p.get("action")
                calls.append({"id": p.get("call_id"), "name": name, "command": _command_of(name, args)})
            elif p.get("type") in ("function_call_output", "custom_tool_call_output"):
                status[p.get("call_id")] = _codex_status(p.get("output"))
            continue
        for b in (d.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            if d.get("type") == "assistant" and b.get("type") == "tool_use":
                calls.append({"id": b.get("id"), "name": b.get("name"), "command": _command_of(b.get("name"), b.get("input"))})
            elif d.get("type") == "user" and b.get("type") == "tool_result":
                status[b.get("tool_use_id")] = "error" if b.get("is_error") else "ok"
    for c in calls:
        c["status"] = status.get(c["id"], "pending")
        c["kind"] = "edit" if c["name"] in EDIT_TOOLS else "command" if c["name"] in COMMAND_TOOLS else "other"
    first_edit = next((i for i, c in enumerate(calls) if c["kind"] == "edit"), None)
    last_edit = max((i for i, c in enumerate(calls) if c["kind"] == "edit"), default=None)
    before_first_edit = [t[:MAX_MSG_CHARS] for n, t in texts if first_edit is None or n <= first_edit]
    return {
        "request": request,
        "messages_before_first_edit": before_first_edit,
        "final_message": texts[-1][1][:MAX_MSG_CHARS] if texts else "",
        "calls": calls,
        "edited": last_edit is not None,
        "commands_after_last_edit": [
            {"command": c["command"][:300], "result": c["status"]}
            for c in (calls[last_edit + 1:] if last_edit is not None else [])
            if c["kind"] == "command"
        ],
    }


# --- git evidence ---

def _git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def snapshot(cwd):
    """Baseline for this turn: a commit of the working tree (tracked files) plus the untracked file list."""
    try:
        _git(cwd, "rev-parse", "--is-inside-work-tree")
    except Exception:
        return None
    base = _git(cwd, "stash", "create").strip()
    if not base:
        try:
            base = _git(cwd, "rev-parse", "HEAD").strip()
        except Exception:
            base = None
    untracked = _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    return {"base": base, "untracked": untracked}


def parse_diff(text):
    hunks, file, cur = [], None, None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            m = re.search(r" b/(.+)$", line)
            file, cur = (m.group(1) if m else None), None
        elif line.startswith("@@") and file:
            cur = {"file": file, "header": line.split("@@")[1].strip() if line.count("@@") >= 2 else line, "diff": ""}
            hunks.append(cur)
        elif cur is not None and line[:1] in ("+", "-", " ") and not line.startswith(("+++", "---")):
            cur["diff"] += line + "\n"
    for h in hunks:
        if len(h["diff"]) > MAX_HUNK_CHARS:
            h["diff"] = h["diff"][:MAX_HUNK_CHARS] + "…[truncated]\n"
    return hunks


def turn_hunks(cwd, snap):
    """Hunks changed since the baseline, plus files created during the turn."""
    if not snap:
        snap = snapshot(cwd)
        if not snap or not snap.get("base"):
            return []
        # no baseline recorded: fall back to everything uncommitted
        text = _git(cwd, "diff", "HEAD")
        return parse_diff(text)
    hunks = parse_diff(_git(cwd, "diff", snap["base"])) if snap.get("base") else []
    now = _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    own = os.path.relpath(os.path.expanduser(os.environ.get("KARPATHY_JEV_HOME", "~/.karpathy-jev")), cwd)  # never count the hook's own files as changes
    for path in sorted(set(now) - set(snap.get("untracked") or [])):
        if not own.startswith("..") and (path == own or path.startswith(own.rstrip("/") + "/")):
            continue
        try:
            with open(os.path.join(cwd, path), encoding="utf-8") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        body = "".join(f"+{l}\n" for l in lines[:NEW_FILE_LINES])
        if len(lines) > NEW_FILE_LINES:
            body += f"+…[{len(lines) - NEW_FILE_LINES} more lines]\n"
        hunks.append({"file": path, "header": "new file", "diff": body[:MAX_HUNK_CHARS]})
    return hunks



# --- agent mode: observed runs instead of a transcript ---

def run_recorded(cmd, runs_path):
    """Run a command, stream its output, and record the real exit code with a timestamp."""
    t0 = time.time()
    r = subprocess.run(cmd, shell=isinstance(cmd, str))
    entry = {"ts": t0, "command": cmd if isinstance(cmd, str) else " ".join(cmd),
             "result": "ok" if r.returncode == 0 else "error", "exit_code": r.returncode}
    os.makedirs(os.path.dirname(runs_path), exist_ok=True)
    with open(runs_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return r.returncode


def runs_after_last_edit(runs_path, cwd, hunks):
    """Recorded runs that started after the newest modification of any changed file."""
    mtimes = []
    for h in hunks:
        try:
            mtimes.append(os.path.getmtime(os.path.join(cwd, h["file"])))
        except OSError:
            pass
    last_edit = max(mtimes, default=0)
    out = []
    if os.path.exists(runs_path):
        for line in open(runs_path):
            e = json.loads(line)
            if e["ts"] > last_edit:
                out.append({"command": e["command"][:300], "result": e["result"]})
    return out
