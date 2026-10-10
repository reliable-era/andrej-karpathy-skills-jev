#!/usr/bin/python3
"""Passive wrapper for the supported CLAUDE_CODE_SHELL_PREFIX hook.

The pinned CLI passes one wrapped Bash command string (snapshot + eval + cwd
receipt), observed in the v2 probe. Execute it with /bin/bash -c, preserving stdio,
status and signals. Never enable pipefail; reject unknown argument mappings.
"""
import json
import os
import signal
import subprocess
import sys
import time

args = sys.argv[1:]
with open('/tmp/campaign-prefix-exits.jsonl', 'a') as f:
    f.write(json.dumps({'argv_received':args, 'utc_ns':time.time_ns()})+'\n')
if len(args) != 1:
    raise SystemExit('Unsupported prefix ABI; inspect the preserved argv receipt')
result = subprocess.run(['/bin/bash', '-c', args[0]])
with open('/tmp/campaign-prefix-exits.jsonl', 'a') as f:
    f.write(json.dumps({'command':args[0], 'observed_exit':result.returncode, 'utc_ns':time.time_ns()})+'\n')
if result.returncode < 0:
    sig = -result.returncode
    if sig not in (signal.SIGKILL, signal.SIGSTOP):
        signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)
raise SystemExit(result.returncode)
