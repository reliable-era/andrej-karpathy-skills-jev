# Repository Memo

Recorded: 2026-10-09. Applies to this published repository and future evaluation campaigns.

## 1. Plan Evaluations Before Running Them

Write the protocol in [eval/EVALUATION.md](eval/EVALUATION.md), then freeze a campaign manifest before
scored execution. It must define benchmarks, sample IDs, harness/model cells, methods, repeat counts,
budgets, metrics, calibration, analysis, and completion criteria. Unimplemented adapters and unrun
cells remain explicitly planned. Any later change creates a separately named condition.

## 2. Reuse the 10%, 20%, and 30% Checkpoints

The samples are nested: **10% ⊆ 20% ⊆ 30%**. Freeze the complete task order and all checkpoint
memberships before scoring.

- At 20%, retain accepted attempts from the 10% checkpoint and run only the additional tasks.
- At 30%, retain accepted attempts from the 20% checkpoint and run only the additional tasks.
- Reuse applies to the same task, method, harness, model, repeat, and frozen protocol. Verify manifest
  and artifact hashes before reuse; do not regenerate an attempt to improve its score.
- Reuse task IDs across methods and harness/model cells, but give each scheduled attempt its own
  fresh environment. The three repeats are distinct attempts, not checkpoint reruns.
- If software, skills, models, prompts, budgets, or grading change, preserve old attempts under their
  original condition. Do not present them as attempts under the new condition.
- Earlier development runs remain separate from the new held-out campaign, as specified in the plan.

## 3. Record Software Versions and Hashes

A version string alone is insufficient. Record both provenance and the actual installed artifacts:

| Component | Required record |
|---|---|
| Repository and skill | Release tag, full Git commit SHA, skill/registry SHA256 |
| Agent harness | Reported version, source commit SHA when available, executable or installed-package SHA256 |
| Harness adapter and tools | Source commit where applicable, artifact SHA256, tool/runtime versions |
| Model server and grader | Version/source commit, artifact SHA256, container image digest |
| Dataset and protocol | Dataset revision, manifest/config/prompt hashes, grader source hashes |

Hash the code actually executed, including package bundles and compatibility bridges, rather than
only a launcher or symlink. For directory hashes, freeze the file selection, ordering, and symlink
treatment. Keep the runtime/lockfile identity with the record. Verify hashes before scoring and again
at final collection; unexpected changes invalidate reuse until investigated.

If a closed-source harness exposes no source commit, record that fact and retain its reported
version plus executable/package hash. Do not invent a SHA. A local client hash does not pin a hosted
model; record the provider's returned model identity and any remaining version uncertainty separately.

## 4. Use Pull Requests for Future Updates

Submit changes only to **`reliable-era/andrej-karpathy-skills-jev`**. External repositories,
including `multica-ai/andrej-karpathy-skills`, are read-only references. Do not push branches or
create pull requests, issues, or comments there without new explicit user authorization.
For GitHub write commands, always specify `--repo reliable-era/andrej-karpathy-skills-jev`.

The repository is already public. Future code, plugin metadata, documentation, and evaluation changes
must use a feature branch and a PR targeting `main`, including this evaluation-plan update.

```text
Feature branch → scoped changes → verification → PR → review → merge → release when needed
```

Do not push updates directly to `main`. PRs must state what changed, what was checked, and any
remaining evidence gaps. Creating a PR does not authorize merging it. Preserve historical results and
release snapshots; changing a reported condition requires a new condition and explicit provenance.

## 5. Treat the Published Version as a Release

Public release numbering starts at **v0.1.0**. Internal development labels do not determine the public
release version.

Baseline release: **v0.1.0**, published source commit
**35316505ef52cde1c045b55071fe5625c4663e01**. The evaluation plan and this memo are follow-up PR changes;
they are not part of that baseline snapshot.

Keep release tags immutable. Future releases come from reviewed, merged commits, with the release tag
and plugin version in agreement. Release notes must identify the source commit, verification performed,
and limitations. An installable software release does not imply that its historical benchmark audit is
complete or that the proposed evaluation has run.

For reproducible installation of the baseline release:

```text
/plugin install karpathy-jev --marketplace reliable-era/andrej-karpathy-skills-jev#v0.1.0
```
