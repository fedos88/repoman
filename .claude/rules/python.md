---
paths:
  - "**/*.py"
  - "**/requirements*.txt"
  - "**/pyproject.toml"
  - "**/pytest.ini"
  - "**/tox.ini"
---

# Python rules

## Dependencies and environment

- Run project Python code in the project's virtual environment when one is defined.
- All third-party runtime dependencies must be declared in the repository dependency files. For this project, prefer and maintain `requirements.txt` when that is the established dependency source.
- Do not suggest or add ad-hoc global `pip install` steps as the permanent solution.
- Before adding a dependency, check whether the standard library or an existing dependency already solves the problem.

## Implementation

- Follow the Python version and style already used by the repository.
- Preserve existing CLI arguments, environment variables, output formats, filenames, and return/exit behavior unless explicitly requested.
- Prefer straightforward code over new abstractions for one-off behavior.
- Do not introduce broad exception handling that hides failures.
- Catch exceptions at meaningful boundaries and preserve useful error context.
- Use `pathlib` when it fits existing style, but do not refactor existing path code solely for stylistic reasons.
- For subprocess execution, prefer argument lists over shell strings. Use `shell=True` only when shell semantics are actually required.
- Do not log secret values or full credential-bearing URLs.

## Configuration

- Reuse the project's existing environment/config loading mechanism.
- Preserve the semantic difference between missing, empty, and explicit null values when the existing application relies on it.
- Do not hard-code deployment-specific hosts, paths, IDs, or credentials when configuration already exists.

## Database code

- Use parameterized SQL; never interpolate untrusted values into SQL strings.
- Preserve transaction boundaries and existing commit/rollback behavior unless the task requires changing them.
- Do not modify already-deployed migrations to change production schema history; add a new migration when the repository follows append-only migrations.

## Validation

After changing Python code, use the narrowest applicable checks already supported by the repository, for example:
- syntax/import check;
- targeted unit tests or `pytest` selection;
- configured formatter/linter/type checker if the project already uses one;
- a safe `--help`, dry-run, or equivalent invocation for CLI scripts.

Do not add a new formatter, linter, test framework, or type checker solely for validation unless requested.
