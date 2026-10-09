---
paths:
  - "ansible/**/*"
  - "playbooks/**/*"
  - "roles/**/*"
  - "inventory/**/*"
  - "inventories/**/*"
  - "group_vars/**/*"
  - "host_vars/**/*"
  - "**/ansible.cfg"
  - "**/.ansible-lint"
  - "**/requirements.yml"
  - "**/requirements.yaml"
---

# Ansible rules

## General approach

- Preserve existing playbook, role, inventory, variable, tag, and naming conventions.
- Make the smallest change required for the task. Do not reorganize roles or inventories unless explicitly requested.
- Prefer built-in Ansible modules and existing collection modules over `ansible.builtin.shell`, `ansible.builtin.command`, or custom scripts.
- Use fully qualified collection names (FQCN) when the repository already follows that convention or when module origin could be ambiguous.
- Do not introduce a module, collection, filter, or feature that requires a newer `ansible-core` or collection version than the repository/runtime provides.
- Before adding a dependency, inspect the existing collection requirements and execution environment.

## Idempotency

- Tasks should be idempotent whenever possible.
- Re-running a playbook against an already configured host should normally result in no changes.
- Prefer declarative modules such as `package`, `service`, `file`, `template`, `copy`, `user`, `mount`, and provider-specific modules over imperative shell commands.
- Do not use `changed_when: false` merely to hide a non-idempotent task.
- When `command` or `shell` is genuinely necessary, define correct `changed_when`, `failed_when`, `creates`, `removes`, or equivalent guards when applicable.
- Avoid unconditional restarts. Use handlers and `notify` when a service should restart only after a relevant change.

## Shell and command tasks

- Prefer `ansible.builtin.command` over `ansible.builtin.shell` when shell syntax is not required.
- Use `shell` only when pipes, redirects, shell expansion, compound commands, or other shell features are actually necessary.
- Quote variables passed into shell commands carefully. Treat inventory variables and external input as untrusted unless guaranteed otherwise.
- Specify the required shell explicitly only when needed; do not assume Bash features under `/bin/sh`.
- Do not combine unrelated mutations into one large shell block when native modules can express them safely.

## Variables and precedence

- Reuse existing variables instead of creating duplicate variables for the same value.
- Preserve existing variable names because they are interfaces for inventories, AWX surveys, job templates, CI/CD, and callers.
- Put defaults that users are expected to override in role `defaults/main.yml` rather than `vars/main.yml` unless stronger precedence is intentional.
- Do not move variables between `defaults`, `vars`, inventory, `group_vars`, `host_vars`, or extra vars without considering Ansible precedence.
- Do not hard-code environment-specific hosts, addresses, credentials, paths, IDs, or URLs when a variable already exists or should reasonably exist.
- Use `default(...)` only when a missing value is genuinely acceptable. Do not silently mask required configuration.
- Use `assert` or explicit validation for required or constrained input when failure should happen early.

## Secrets and credentials

- Never place passwords, tokens, private keys, Vault secrets, or other credentials in plaintext in playbooks, inventories, defaults, examples, logs, or committed files.
- Preserve existing Ansible Vault, AWX credential, environment variable, or external secret-store integrations.
- Do not replace credential references with literal values while debugging.
- Add `no_log: true` to tasks that can expose secrets in module arguments or results, while keeping enough non-secret diagnostics available to troubleshoot failures.
- Do not print complete registered results if they may contain credentials or sensitive data.

## Privilege escalation

- Use `become` only where elevated privileges are required.
- Prefer task- or block-level `become` when only part of a play requires elevation instead of unnecessarily running the entire play as root.
- Do not hard-code sudo passwords or privilege-escalation credentials.
- Preserve established `become_user`, `become_method`, and privilege boundaries.

## Inventory and targeting safety

- Treat inventory groups and `hosts:` expressions as safety boundaries.
- Do not broaden a play from a narrow group to `all` unless explicitly requested and verified safe.
- Preserve existing `limit`, tags, environment selectors, and host-group semantics.
- Be especially careful with `delegate_to`, `local_action`, `run_once`, and loops over inventory groups: verify which host actually executes the task and how many times.
- Do not assume `run_once` means one execution globally when plays may be processed in batches via `serial`.
- Before destructive or disruptive operations, confirm that host selection cannot unintentionally include production systems.

## Handlers, blocks, and errors

- Use handlers for actions that should occur only after a configuration change, especially service reloads and restarts.
- Give handlers stable names and preserve existing notification contracts.
- Use `block`, `rescue`, and `always` when they improve failure handling or cleanup; do not use them to suppress real failures.
- Avoid `ignore_errors: true` unless failure is explicitly acceptable and subsequent behavior is well defined.
- Prefer precise `failed_when` conditions over globally ignoring failures.
- When registering command output, handle return codes explicitly if more than one exit code is valid.

## Files and templates

- Prefer `template` when content contains variables or configuration logic; prefer `copy` for static content.
- Preserve file owner, group, mode, SELinux context, and other metadata expected by the target system.
- Quote YAML file modes, for example `mode: "0644"`, to avoid unintended numeric interpretation.
- Use `validate` on `template`/`copy` when the target application provides a safe configuration-check command.
- Do not overwrite a remotely managed configuration file without first understanding its ownership and existing repository pattern.

## Packages and services

- Use the platform-appropriate package/service modules already established in the repository.
- Avoid unnecessary package upgrades when the task only requires ensuring a package is installed.
- Do not use `state: latest` by default, especially for production infrastructure.
- Preserve version pinning when present.
- Prefer a handler-triggered restart or reload over unconditional service restarts.

## AWX / Automation Controller

- Treat job-template variables, surveys, credentials, inventory names, execution-environment assumptions, and extra vars as external interfaces.
- Preserve variable names consumed by AWX unless the task explicitly includes updating the corresponding job templates/surveys.
- Do not assume an interactive terminal, local user profile, or locally installed dependency exists in AWX.
- Do not rely on files outside the project or execution environment unless they are deliberately mounted/provided by the controller.
- Keep stdout useful for job diagnostics, but do not expose secrets.
- When changing collections or Python dependencies, consider the execution environment used by AWX as well as local development.

## Delegation and remote execution

- Distinguish clearly between code running on the controller/execution environment and code running on managed hosts.
- When using `delegate_to: localhost`, verify that required binaries, network access, files, and credentials exist inside the actual execution environment.
- When using SSH indirectly from a playbook, prefer Ansible's connection model and modules where practical rather than starting nested SSH sessions.
- Preserve proxy, bastion, `ansible_ssh_common_args`, and connection settings already used by the inventory.

## Performance

- Avoid repeated expensive fact gathering when the play does not need facts.
- Do not disable fact gathering globally unless all dependent tasks have been checked.
- Prefer one module invocation over large loops of equivalent remote shell calls when a module supports bulk operations.
- Avoid unnecessary `include_tasks`/`import_tasks` complexity for small, single-use task sequences.

## Validation

After modifying Ansible code, run the narrowest applicable checks that are available:

1. YAML/schema/lint validation if configured.
2. `ansible-playbook --syntax-check` with the appropriate inventory or required variables.
3. `ansible-lint` if the repository uses it.
4. `--check --diff` against a safe test inventory when the involved modules support check mode and the operation is safe.
5. A real run against a test host or test inventory when syntax/check mode cannot validate the behavior.

Do not run a changed playbook against production merely to validate it.

Do not claim a playbook is idempotent unless it was either structurally verified with clear module semantics or, preferably, executed twice against a safe test target and the second run produced no unintended changes.

## Review checklist

Before finishing an Ansible change, verify:

- host targeting did not become broader unintentionally;
- variable names and AWX-facing interfaces remain compatible;
- secrets cannot appear in logs or committed files;
- privilege escalation is no broader than required;
- handlers are notified only when needed;
- shell/command usage is justified;
- the change remains idempotent where practical;
- production execution was not performed unless explicitly requested;
- the exact validation commands that were actually run are reported.
