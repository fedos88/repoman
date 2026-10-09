# Как вносить изменения

## Ветки (GitHub Flow)

- `main` всегда в рабочем состоянии; прямой push запрещён, изменения — только через Pull Request с зелёным CI.
- Для каждой задачи — короткоживущая ветка от `main`: `<тип>/<кратко>`, например `feat/apt-proxy`, `fix/login-rate-limit`, `docs/design-storage`, `ci/postgres-service`.
- Слияние — **squash merge**: одна задача = один коммит в `main`.

## Сообщения коммитов (Conventional Commits)

```
<тип>(<область>): <кратко, на русском>

<необязательно: почему сделано так, на русском>
```

- Типы: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`.
- Области: `backend`, `frontend`, `auth`, `ldap`, `jobs`, `apt`, `storage`, `deploy`.
- Заголовок PR оформляется так же — он становится сообщением коммита при squash merge.

Пример:

```
feat(ldap): членство в группах через tokenGroups

Основная группа (Domain Users) не отражается в member/memberOf,
поэтому вложенное членство через неё не определялось.
```

## Проверки перед PR

Backend (`backend/`):

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
REPOMAN_TEST_DATABASE_URL=postgresql://... pytest   # без переменной тесты с БД пропускаются
```

Frontend (`frontend/`):

```bash
npm ci
npm run lint && npm run format:check && npm run typecheck && npm run i18n:check && npm run build
```

Изменения схемы БД — только новой миграцией Alembic; уже выпущенные миграции не редактируются.
