"""Capture HEAD-to-final tracked, staged and all untracked files inside a guest.

Returns bytes, never writes/exports them. The caller must exact-secret scan before
archival. Ignored untracked files are included; scope/grading projections must
separately declare how pre-existing files and generated artifacts are classified.
"""
import hashlib
import subprocess
from pathlib import Path


def capture_final_diff(cwd):
    cwd = Path(cwd)
    def git(*args):
        return subprocess.run(['git', *args], cwd=cwd, capture_output=True, check=True).stdout
    head = git('rev-parse', 'HEAD').decode().strip()
    patch = git('diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD', '--')
    untracked = git('ls-files', '--others', '-z').split(b'\0')
    files = []
    for raw in sorted(p for p in untracked if p):
        name = raw.decode('utf-8', 'surrogateescape')
        result = subprocess.run(['git', 'diff', '--no-index', '--binary', '--no-ext-diff',
                                 '--no-textconv', '--', '/dev/null', name], cwd=cwd, capture_output=True)
        if result.returncode not in (0, 1):
            raise RuntimeError('Untracked diff failed: ' + name)
        patch += result.stdout
        files.append(name)
    return {'head': head, 'patch': patch, 'patch_sha256': hashlib.sha256(patch).hexdigest(),
            'untracked_files': files, 'ignored_untracked_included': True}
