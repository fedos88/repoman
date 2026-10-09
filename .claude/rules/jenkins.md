---
paths:
  - "**/Jenkinsfile"
  - "**/Jenkinsfile.*"
  - "**/*.groovy"
  - "jenkins/**/*"
---

# Jenkins / Groovy pipeline rules

## Preserve the pipeline interface

- Treat Jenkins parameters, environment variable names, credentials IDs, stage names used by automation, downstream job names, artifact paths, and shared-library contracts as interfaces.
- Preserve existing parameter names and defaults unless explicitly requested.
- Before changing a shared helper or pipeline function, search for all callers.
- Preserve existing stage order when ordering is operationally significant.

## Credentials and secrets

- Use Jenkins credential bindings and existing credential helpers.
- Never place secret values directly in Groovy strings, shell commands, logs, or source code.
- Avoid Groovy interpolation of credential values into shell command strings when a safer binding/environment pattern is available.
- Preserve existing credential IDs; do not invent replacement IDs.

## Groovy and shell boundaries

- Pay special attention to quoting and escaping across Groovy -> shell -> SSH -> remote shell layers.
- Do not assume a regex, backslash, `$`, quote, or heredoc survives multiple interpolation layers unchanged.
- Prefer existing helper methods for SSH, credentials, file transfer, and command execution.
- Keep embedded shell/Python snippets small. If substantial logic already belongs in a repository script, modify/reuse that script instead of duplicating it in Groovy.

## Pipeline behavior

- Preserve agent/node selection, labels, workspace assumptions, timeouts, retries, post-actions, and cleanup unless the task explicitly changes them.
- Do not broaden deployment targets or production execution conditions unintentionally.
- Keep validation steps before deployment/mutation steps when possible.
- When a pipeline updates a version, index, metadata, or artifact sequentially, preserve required ordering and stop on meaningful failures.
- Do not silently convert a sequential operational workflow into parallel execution.

## Remote operations

- Treat remote service restarts, scans, deploys, file replacement, and cleanup as mutating actions.
- Reuse the repository's established SSH execution helper and credentials mechanism.
- Do not bypass `sudoers`, host-key verification, or permissions by weakening security controls unless explicitly required and the impact is stated.

## Validation

After changing Jenkins/Groovy code:
- inspect Groovy quoting/interpolation carefully;
- run any repository-provided Jenkins/Groovy lint or validation tool if available;
- verify all referenced parameters, credentials IDs, environment variables, helper functions, job names, and paths exist;
- validate embedded shell/Python snippets separately when practical.

Do not claim Jenkins accepted the pipeline unless it was actually validated by Jenkins or an equivalent configured validator.
