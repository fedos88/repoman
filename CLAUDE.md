# Project instructions

## Repository purpose

This repository contains DevOps and automation code. The main technologies are:
- Bash
- Python
- GitLab CI
- Jenkins / Groovy pipelines
- Ansible / AWX automation

Treat existing repository conventions as authoritative. Inspect the relevant code before changing it.

## Working principles

- Make the smallest correct change that satisfies the task.
- Do not refactor, rename, reorganize, or modernize unrelated code.
- Preserve existing public interfaces, parameter names, environment variable names, file names, output formats, and CI behavior unless the task explicitly requires changing them.
- Reuse existing helpers, patterns, and conventions before introducing new abstractions.
- Do not hard-code environment-specific values when the repository already provides configuration, parameters, credentials, or environment variables for them.
- Do not create helper scripts or temporary files unless they materially simplify the task. Remove temporary artifacts before finishing.
- If requirements are ambiguous, prefer the behavior that is most compatible with the existing implementation.

## Investigation and context efficiency

- Search before reading large files or directories.
- Prefer targeted searches such as `rg`, `grep`, `find`, and narrow `sed` ranges over dumping entire large files.
- Read only files relevant to the current task.
- Do not explore unrelated directories "for completeness".
- Before adding a new helper, function, variable, pipeline step, or script, search the repository for an existing equivalent.
- Do not repeat commands when the result is already known and still relevant.
- Avoid subagents for single-file changes, straightforward searches, and simple debugging. Use them only for genuinely independent workstreams or when isolating a large exploratory context is useful.

## Change workflow

Before editing:
1. Identify the smallest relevant set of files.
2. Read the implementation and nearby conventions.
3. Search for callers, references, related variables, and tests when changing behavior or interfaces.

After editing:
1. Review the diff.
2. Check for accidental unrelated changes.
3. Run the narrowest relevant validation available in the repository.
4. Report what was changed and what validation was actually run.
5. Never claim a check passed if it was not executed.

## Git rules

- Do not commit, push, merge, rebase, tag, or force-push unless explicitly requested.
- Never rewrite existing history unless explicitly requested.
- Do not discard user changes.
- Before destructive Git operations, inspect the working tree and preserve unrelated modifications.
- Keep diffs focused on the requested task.
- Do not modify `.gitignore` merely to hide files created by the task unless requested or clearly required by an established repository convention.

## Production and infrastructure safety

- Treat production infrastructure and production data as sensitive.
- Do not execute deployment, restart, delete, wipe, truncate, drop, destroy, force, cleanup, or migration commands against production unless explicitly requested.
- Prefer validation, dry-run, syntax-check, plan, diff, or read-only commands before mutating infrastructure.
- Never expose secrets, tokens, passwords, private keys, credential contents, or secret environment variable values in output.
- Do not replace credential references with plaintext secrets.
- Do not weaken TLS verification, authentication, authorization, or permission checks merely to make a task pass unless explicitly required and the security impact is stated.

## Configuration and compatibility

- Preserve backward compatibility unless the task explicitly says otherwise.
- Existing CI/CD parameters and environment variables are interfaces. Rename or remove them only when explicitly requested.
- Prefer configuration through existing variables, credentials, parameters, or config files over hard-coded hostnames, paths, usernames, IDs, or URLs.
- When an empty value and an unset value have different semantics, preserve that distinction.

## Communication

- Keep explanations concise and technical.
- If the user writes in Russian, explanations may be in Russian.
- Keep code, identifiers, command names, and existing comments in the repository's established language and style.
- When something cannot be verified locally, state exactly what remains unverified instead of guessing.
