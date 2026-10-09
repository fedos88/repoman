---
paths:
  - ".gitlab-ci.yml"
  - ".gitlab-ci.yaml"
  - ".gitlab/**/*.yml"
  - ".gitlab/**/*.yaml"
---

# GitLab CI rules

## Preserve the pipeline interface

- Treat job names, stages, variables, artifacts, cache keys, `needs`, `dependencies`, rules, trigger contracts, and included templates as interfaces.
- Do not rename or remove them unless explicitly requested.
- Check references before changing a shared variable, template, anchor, job, stage, artifact path, or include.
- Preserve existing runner tags and execution environment unless the task explicitly changes runner placement.

## Rules and execution behavior

- Read the existing `workflow: rules`, job `rules`, `only/except`, manual actions, schedules, and branch/tag conditions before changing when a job runs.
- Avoid unintentionally making production/deployment jobs run on more refs than before.
- Preserve `when: manual`, protected-environment behavior, and approval gates unless explicitly requested.
- Do not turn optional jobs into blocking jobs, or blocking jobs into optional jobs, without noting the behavior change.

## Variables and secrets

- Never hard-code CI secrets, access tokens, passwords, private keys, or credential values.
- Use existing GitLab CI/CD variables and secret-management patterns.
- Preserve variable names used by scripts and downstream pipelines.
- Be conscious of variable expansion and quoting differences between YAML, GitLab, and the job shell.

## Includes and reuse

- Prefer the repository's existing templates, `extends`, anchors, and includes over duplicating job definitions.
- Do not introduce abstraction for a single tiny job if duplication is clearer and matches existing style.
- When modifying a shared template, inspect its consumers before changing behavior.

## Scripts

- Keep complex shell logic in existing repository scripts when practical rather than growing large inline YAML command blocks.
- Preserve exit-code behavior; do not hide failures with `|| true` unless failure is intentionally non-blocking.

## Validation

After changing GitLab CI:
- validate YAML structure with an existing repository tool if available;
- use GitLab CI lint when available in the established workflow;
- inspect the resulting `rules`/`needs`/stage behavior for the affected jobs;
- verify referenced scripts, variables, includes, artifacts, and paths exist.

Do not trigger a deployment pipeline merely to validate syntax unless explicitly requested.
