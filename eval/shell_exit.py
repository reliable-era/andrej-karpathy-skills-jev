"""Passive Bash EXIT receipt; never changes pipeline options or command status.

Install this file and bash_env under root-owned /opt/campaign-tools. Initialize
/tmp/campaign-bash-exits.jsonl before solving; collect privately and secret-scan.
A missing receipt remains unknown (signals/trap replacement/non-Bash shells).
"""
import json
import os
import sys
import time

if __name__ == '__main__':
    with open('/tmp/campaign-bash-exits.jsonl', 'a') as f:
        f.write(json.dumps({'observed_exit':int(sys.argv[1]), 'command':sys.argv[2],
                            'shell_pid':os.getppid(), 'utc_ns':time.time_ns()})+'\n')
