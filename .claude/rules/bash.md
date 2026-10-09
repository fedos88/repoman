---
paths:
  - "**/*.sh"
  - "**/*.bash"
---

# Bash rules

## Compatibility

- Determine the expected shell from the shebang and existing repository conventions before using shell-specific features.
- Do not silently change a script from POSIX `sh` compatibility to Bash-only syntax.
- Preserve existing CLI arguments, exit codes, stdout/stderr behavior, and machine-readable output unless explicitly requested.

## Safety and correctness

- Quote variable expansions unless intentional word splitting or glob expansion is required.
- Use arrays for argument lists in Bash when that avoids unsafe string construction.
- Avoid `eval` unless the existing design genuinely requires it and there is no safer alternative.
- Validate required variables and arguments at appropriate boundaries.
- Be careful with `set -e`, pipelines, subshells, traps, and commands whose non-zero exit status is expected.
- When using temporary files or directories, prefer `mktemp` and clean them with an appropriate trap.
- Do not embed passwords, tokens, private keys, or credentials in commands or source files.

## Destructive commands

- Treat `rm -rf`, filesystem formatting, disk operations, service disruption, bulk process termination, database mutation, and remote deletion as destructive.
- Never broaden a destructive path or glob without checking the resolved target.
- Prefer explicit paths and defensive checks for cleanup operations.
- Do not add `sudo` unless the operation actually requires it and the repository convention expects it.

## Remote execution

- Quote remote command arguments deliberately; distinguish local shell expansion from remote shell expansion.
- Avoid constructing SSH commands through fragile nested string interpolation when safer argument or helper patterns already exist.
- Reuse existing SSH wrappers/helpers in the repository.

## Validation

After changing Bash code:
- run `bash -n <changed-script>` for Bash scripts when applicable;
- run `shellcheck` if it is already used by the project or available in the existing toolchain;
- exercise the smallest safe non-destructive code path when practical.
