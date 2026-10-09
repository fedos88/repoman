# RepoMan — Design Document (MVP)

Статус: **черновик на согласование**
Дата: 2026-10-09

Документ фиксирует решения, согласованные для первой версии (MVP). Всё, что помечено «вне MVP», — только заложено в модель/интерфейсы, но не реализуется.

---

## 1. Цели и объём MVP

### 1.1. Входит в MVP

- Proxy-репозитории формата **APT** (клиенты Ubuntu 24.04 и 26.04), upstream — публичные HTTP/HTTPS-репозитории без авторизации.
- Кэширование с разделением на immutable / mutable metadata / negative cache, `serve_stale`, обязательный single-flight.
- Хранилище: **filesystem**, через абстракцию blob store (S3 — позже без переписывания proxy-логики).
- Внутренняя БД: **PostgreSQL**.
- Конфигурация репозиториев, пользователей, ролей, LDAP и т.д. — **только через Web UI / REST API** (API-first, UI — клиент REST API). Через env задаётся только bootstrap (подключение к БД, путь хранилища, ключи).
- **Backend и frontend — отдельные контейнеры.** Backend работает самостоятельно (REST API, Swagger, APT proxy); frontend — SPA (React), только статика.
- Аутентификация: локальные пользователи + **Active Directory (LDAP)**; API-токены.
- Авторизация: RBAC (роли → права `read` на репозитории), встроенные роли `anonymous`, `authenticated`, `admin`.
- Синхронизация пользователей с AD по расписанию.
- Фоновые задания на PostgreSQL-очереди; ручная полная очистка репозитория.
- Минимальный Web UI (тёмная и светлая темы, i18n ru + en); публичная главная страница-заглушка на основе README.
- `/healthz`, `/readyz`, `/metrics`.

### 1.2. Вне MVP (закладываем в модель, не реализуем)

- Реиндекс (сверка хранилища и БД) — `repository_reconcile`.
- Миграция данных репозитория между blob store — `blob_store_migrate`.
- Политики очистки (по `last_accessed_at`, возрасту, размеру).
- S3 blob store.
- Upstream с авторизацией.
- Hosted / group репозитории, другие форматы (YUM, npm, Go, Docker, Raw).
- Kerberos / SSO, несколько доменов AD.
- Multi-node.

### 1.3. Целевая нагрузка MVP

10 клиентов + 2 CI-раннера, проксируемый объём ~500 ГБ, single-node.

---

## 2. Архитектура

```text
          browser            apt / curl / automation
             │                         │
     ┌───────▼─────────────────────────▼───────┐
     │  reverse proxy (nginx / LB, TLS)        │
     │   /             → frontend              │
     │   /api/         → backend               │
     │   /repository/  → backend               │
     └──────┬───────────────────────┬──────────┘
            │                       │
┌───────────▼──────────┐  ┌─────────▼─────────────────────────────────┐
│ frontend (nginx)     │  │ backend (FastAPI, 1 процесс, asyncio)     │
│ React SPA, статика   │  │                                           │
│ SPA fallback         │  │  /api/v1/…  REST API   /api/docs Swagger  │
└──────────────────────┘  │  /repository/{name}/…  APT proxy          │
                          │  /healthz /readyz /metrics                │
                          │                                           │
                          │  Auth: sessions · tokens · local · LDAP   │
                          │  Proxy core: classifier · cache policy ·  │
                          │              single-flight · httpx        │
                          │  Blob store: Filesystem (MVP) / S3 (later)│
                          │  Jobs: queue (PostgreSQL) · scheduler     │
                          └──────┬──────────────────────┬─────────────┘
                                 │                      │
                            PostgreSQL         Filesystem (blobs)
                                                        │
                                       Upstream APT repos (HTTP/HTTPS)
                                       AD (LDAP / LDAPS)
```

- **Backend** работает самостоятельно: REST API, Swagger, APT proxy, health и метрики. HTML не рендерит.
- **Frontend** — только статика SPA; не находится на пути apt-трафика и API-запросов автоматизации, может перезапускаться без влияния на apt.
- **Reverse proxy** маршрутизирует по пути (§17.2). UI и API на одном origin → без CORS, cookie-сессии работают.

Backend — один процесс (один uvicorn worker). Single-flight и in-memory кэши (права, rate limit логина) корректны в пределах процесса. Переход к нескольким процессам/нодам потребует распределённых блокировок (`pg_advisory_lock`) — вне MVP.

### 2.1. Стек

| Назначение | Выбор |
|---|---|
**Backend**

| Назначение | Выбор |
|---|---|
| Язык | Python 3.12+ |
| Web | FastAPI + uvicorn |
| HTTP-клиент upstream | httpx (async) |
| БД | PostgreSQL 15+, SQLAlchemy 2 (async) + asyncpg, Alembic |
| Валидация / схемы | Pydantic v2 |
| Пароли | argon2id (`argon2-cffi`) |
| LDAP | `ldap3` |
| Шифрование секретов в БД | `cryptography` (Fernet) |
| Метрики | `prometheus-client` |
| Тесты | pytest, pytest-asyncio |
| Линтер / форматтер | ruff |

**Frontend**

| Назначение | Выбор |
|---|---|
| Язык / сборка | TypeScript, Vite, Node 24 LTS (только сборка) |
| Фреймворк | React |
| UI-компоненты, темы | Mantine (тёмная / светлая тема) |
| Роутинг | React Router |
| Данные | TanStack Query |
| API-клиент | `openapi-typescript` + `openapi-fetch` (типы генерируются из OpenAPI backend) |
| i18n | i18next + react-i18next (ru, en) |
| Линтер / форматтер | ESLint, Prettier |
| Рантайм | nginx (unprivileged), только статика |

### 2.2. Структура репозитория (предварительно)

```text
backend/
  pyproject.toml
  Dockerfile
  src/repoman/
    main.py              # app factory
    config.py            # bootstrap-настройки из env
    db/                  # модели, сессии
    migrations/          # Alembic
    storage/             # BlobStore интерфейс, filesystem
    proxy/               # классификатор путей, cache policy, single-flight, upstream
    formats/apt/         # APT-специфика
    auth/                # пароли, сессии, токены, LDAP, RBAC
    jobs/                # очередь, воркеры, планировщик, задачи
    api/v1/              # REST API
  tests/
frontend/
  package.json
  Dockerfile
  nginx.conf             # статика + SPA fallback
  src/
    api/                 # сгенерированные типы + клиент
    i18n/                # ru.json, en.json
    pages/
    components/
deploy/
  nginx/repoman.conf     # reverse proxy: используется в dev compose и как пример для prod
docker-compose.dev.yml
.github/workflows/ci.yml
docs/
```

---

## 3. URL-схема

**Backend:**

| Путь | Назначение | Доступ |
|---|---|---|
| `/repository/{name}/{path}` | Контент репозитория | по правам репозитория |
| `/api/v1/...` | REST API | по ролям |
| `/api/docs`, `/api/openapi.json` | Swagger UI / OpenAPI | публичный |
| `/healthz`, `/readyz` | liveness / readiness | публичный |
| `/metrics` | Prometheus | опционально по токену (`REPOMAN_METRICS_TOKEN`) |
| `/` | JSON: имя, версия, ссылка на `/api/docs` (при обращении к backend напрямую) | публичный |

**Frontend:** все остальные пути (`/`, `/login`, `/repositories/...`, `/admin/...`) — SPA, неизвестные пути отдают `index.html`.

Префиксы `/api/` и `/repository/` зарезервированы за backend. RepoMan обслуживается от корня хоста; запуск на подпути не поддерживается.

Пример: `https://repo.company.local/repository/ubuntu/` → репозиторий `ubuntu`. URL одинаков при обращении через reverse proxy и напрямую в backend.

**Внешний base URL** (для готовых `sources.list` в UI): `GET /api/v1/system/info` возвращает `base_url` из `REPOMAN_BASE_URL`, если он задан; иначе frontend использует `window.location.origin`.

**IP клиента** (логи, rate limit входа): `X-Forwarded-For` / `X-Forwarded-Proto` учитываются только от адресов из `REPOMAN_TRUSTED_PROXIES`.

**Имя репозитория:** `^[a-z0-9][a-z0-9._-]{0,63}$`, уникально.

**Нормализация `path`:** запрещены `..`, пустые сегменты, `\`, NUL, percent-encoded обходы; путь нормализуется до использования в ключах хранилища и БД.

---

## 4. Модель репозитория

| Поле | Описание |
|---|---|
| `name` | имя (часть URL) |
| `format` | `apt` (в MVP единственный) |
| `type` | `proxy` (в будущем `hosted`, `group`) |
| `upstream_url` | например `http://archive.ubuntu.com/ubuntu/` |
| `blob_store_id` | ссылка на blob store |
| `metadata_ttl` | nullable; `NULL` = системный default |
| `negative_ttl` | nullable; `NULL` = системный default |
| `serve_stale` | nullable; `NULL` = системный default |
| `online` | выключенный репозиторий отвечает `503` |
| `status` | `active` / `deleting` (позже `migrating`, …) |
| `description` | |

Анонимный доступ — не отдельное поле, а право `read` у роли `anonymous` (в UI — галочка «Анонимный доступ» в форме репозитория).

---

## 5. Системные настройки (defaults)

Хранятся в БД, меняются через UI/API.

| Настройка | Default |
|---|---|
| `metadata_ttl` | 1800 с |
| `negative_ttl` | 300 с |
| `serve_stale` | `true` |
| `upstream_connect_timeout` | 10 с |
| `upstream_read_timeout` (между байтами) | 60 с |
| `upstream_max_redirects` | 5 |
| `ldap_sync_interval` | 3600 с |
| `ldap_sync_max_block_ratio` | 0.5 |
| `session_idle_timeout` | 12 ч |
| `session_absolute_timeout` | 7 д |

---

## 6. APT proxy

### 6.1. Классификация путей

Классификация по пути относительно корня репозитория (не по расширению). Работает и для Ubuntu archive/security/ports, и для сторонних APT-репозиториев.

| Класс | Пути | Поведение |
|---|---|---|
| **immutable** | `pool/**`, `dists/**/by-hash/**` | хранится бессрочно, без ревалидации |
| **metadata** | прочее под `dists/**` (`InRelease`, `Release`, `Release.gpg`, `Packages*`, `Sources*`, `Translation-*`, `Contents-*`, `dep11/*`, `cnf/*`, …) | TTL + условная ревалидация |
| **metadata (flat repo)** | `InRelease`, `Release`, `Release.gpg`, `Packages*`, `Sources*` в корне или подкаталоге без `dists/` | как metadata |
| **immutable (прочее)** | всё остальное | как immutable |

`dists/**/by-hash/**` адресуется по содержимому → immutable. Ubuntu 24.04+ использует `Acquire-By-Hash`, что снимает проблему рассогласования `InRelease` и индексов (`Hash Sum mismatch`).

RepoMan не модифицирует и не переподписывает метаданные: проверка подписи остаётся на клиенте.

### 6.2. Обработка запроса

```text
GET /repository/{name}/{path}
  1. Найти репозиторий, проверить право read (§8.5)
  2. Классифицировать путь
  3. Negative cache: свежая запись → 404 (X-RepoMan-Cache: NEGATIVE)
  4. Есть запись в cache_entries:
       immutable                 → отдать из blob store (HIT)
       metadata, TTL не истёк    → отдать (HIT)
       metadata, TTL истёк       → ревалидация через single-flight:
            304                  → обновить checked_at, отдать (REVALIDATED)
            200                  → записать новую версию, отдать (MISS)
            404/410              → удалить запись, negative cache, 404
            ошибка/5xx/таймаут   → serve_stale ? отдать старую (STALE) : 502/504
  5. Записи нет → fetch через single-flight:
            200                  → потоково отдать и сохранить (MISS)
            404/410              → negative cache, 404
            ошибка/5xx/таймаут   → 502/504 (не кэшируется)
```

- Поддерживаются `GET` и `HEAD`.
- `Range` (single range) поддерживается при отдаче из кэша; при отдаче во время скачивания — по мере поступления байтов.
- Условные запросы клиента (`If-Modified-Since`, `If-None-Match`) обрабатываются по данным кэша → `304`.
- Директивы `Cache-Control` клиента **игнорируются**: свежесть определяется политикой RepoMan.
- Заголовок ответа `X-RepoMan-Cache: HIT | MISS | REVALIDATED | STALE | NEGATIVE` — для диагностики.
- Upstream-запрос: всегда полный файл (без проброса клиентского `Range`), redirects следуются (лимит), учитываются `HTTPS_PROXY` / `NO_PROXY`, TLS-проверка всегда включена, дополнительный CA — `REPOMAN_CA_BUNDLE`.
- Кэшируются только `200`; `404`/`410` — в negative cache; `5xx`, таймауты, сетевые ошибки — не кэшируются.

### 6.3. Single-flight

Ключ: `(repository_id, path)`. Реестр активных загрузок — в памяти процесса.

1. Первый запрос создаёт загрузку (leader), остальные присоединяются к ней.
2. Загрузка выполняется **в отдельной задаче, не привязанной к клиентскому запросу**: отключение клиента не прерывает скачивание.
3. Загрузка пишет новый blob (§7), параллельно считает **sha256** и размер.
4. Все клиенты (включая первого) получают ответ **потоково, читая растущий локальный файл** — ни один не ждёт полного скачивания (иначе большие пакеты упираются в `Acquire::http::Timeout` apt). Для filesystem это временный файл самого blob; для S3 (позже) — локальный spool-файл, из которого объект выгружается в S3.
5. Ответ клиентам начинается после получения заголовков upstream: при `404` все получают `404`.
6. По завершении: проверка размера против `Content-Length`, commit blob, запись `blobs` + `cache_entries` в одной транзакции; заменённый blob (старая версия metadata) помечается удалённым.
7. Если upstream оборвался в процессе — незавершённый blob удаляется, клиентам рвётся соединение (apt повторит запрос).
8. Ревалидация metadata идёт через тот же механизм.

### 6.4. Нехватка места

При ошибке записи из-за нехватки места (`ENOSPC`) или при свободном месте ниже порога: запрос обслуживается в режиме **pass-through** (потоково из upstream без сохранения), в лог — error, метрика `repoman_storage_full`.

### 6.5. `last_accessed_at`

Для будущих политик очистки. Обращения к объектам накапливаются в памяти и сбрасываются в БД пачкой раз в минуту; запись обновляется не чаще раза в сутки на объект.

### 6.6. Очистка и удаление репозитория

Очистка мгновенна для клиентов и не требует остановки репозитория:

1. В одной транзакции: строки `cache_entries` / `negative_cache` репозитория удаляются, их blobs помечаются удалёнными (`deleted_at`).
2. Новые запросы — промахи, файлы заново скачиваются из upstream.
3. Активные загрузки, начатые до очистки, при commit обнаруживают, что очистка произошла (счётчик `purged_at` репозитория), и отбрасывают результат.
4. Физическое удаление объектов — задание `blob_gc` после grace period (§7.5).

При большом числе записей шаг 1 выполняется заданием `repository_purge` пачками; до его завершения репозиторий работает в режиме «всё — промах».

Удаление репозитория: `status=deleting`, задание `repository_delete` удаляет строки и помечает blobs удалёнными, затем удаляет сам репозиторий.

---

## 7. Хранилище (blob store)

### 7.1. Модель: blob ID

Объекты хранятся под **случайными идентификаторами**, а не под путями репозиториев (модель Nexus):

- **blob** — неизменяемый объект: `id` (UUID), `blob_store_id`, `size`, `sha256`, `created_at`, `deleted_at`;
- репозитории ссылаются на blob: `cache_entries.blob_id` (proxy), позже — компоненты hosted-репозиториев;
- **источник истины — БД**: объект без строки в `blobs` считается мусором.

Почему так, а не по пути:

- ключ известен до записи → в S3 объект пишется сразу в итоговый ключ (в S3 нет rename);
- перенос между хранилищами и переименования не трогают пути;
- удаление двухфазное с задержкой — безопасно для hosted-данных и бэкапов (§7.5);
- sha256 в БД — проверка целостности и задел на дедупликацию.

Цена — безымянные файлы на диске; соответствие «путь → blob» доступно в API/UI.

### 7.2. Интерфейс

```python
class BlobStorage(Protocol):
    async def open_write(self, blob_id: UUID) -> BlobWriter: ...  # write(), commit(), abort()
    async def open_read(self, blob_id: UUID, start: int = 0, end: int | None = None) -> AsyncIterator[bytes]: ...
    async def stat(self, blob_id: UUID) -> BlobStat | None: ...
    async def delete(self, blob_id: UUID) -> None: ...
    async def iterate(self) -> AsyncIterator[BlobStat]: ...         # для поиска сирот
    async def usage(self) -> StoreUsage | None: ...                 # total / free
```

Proxy- и hosted-логика работают только с этим интерфейсом и сервисом blobs поверх него.

### 7.3. Filesystem (MVP)

- Раскладка: `{root}/blobs/{id[0:2]}/{id[2:4]}/{id}`; временные файлы — `{root}/.tmp/` (**та же ФС**, иначе rename не атомарен).
- Запись: временный файл → `fsync` → `os.replace` в итоговый путь.
- Блокирующие файловые операции — в thread pool.
- Целевая платформа — Linux, хранилище — локальная ФС (ext4/xfs) через bind mount. NFS/SMB не поддерживаются (атомарность rename, блокировки).
- Windows/macOS — только для разработки, не гарантируются.

### 7.4. S3 (отдельный этап после APT proxy)

- Стандартный S3 API без привязки к конкретному продукту: endpoint, region, bucket, prefix, path-style, ключи доступа, свой CA. Ключи доступа шифруются в БД, как пароль LDAP.
- `open_write` → multipart upload в итоговый ключ, `commit` → complete, `abort` → abort multipart.
- Тесты — на SeaweedFS в контейнере. MinIO Community с декабря 2025 в режиме поддержки, официальные образы не публикуются, репозиторий архивирован — работать с ним можно, но целевой платформой не считается.

### 7.5. Удаление, сироты, нехватка места

- **Удаление двухфазное:** в транзакции бизнес-операции blob помечается `deleted_at`; задание `blob_gc` (раз в час) физически удаляет объекты, у которых `deleted_at` старше **grace period (default 24 ч)**, затем строки.
- **Сироты** (объект записан, транзакция не прошла; процесс упал): задание `blob_store_cleanup` (раз в сутки) удаляет объекты без строки в `blobs` старше 24 ч и незавершённые временные файлы старше 24 ч.
- **Нехватка места:** порог «мало места» — `max(5% объёма, 10 ГБ)`. Ниже порога новые blobs не создаются; proxy работает в режиме pass-through (§6.4).
- **Квота** (необязательная, на хранилище) — мягкая: когда объём всех blobs хранилища (включая ожидающие удаления) ≥ квоты, новые blobs не создаются (как при нехватке места); начатая запись дописывается, поэтому квота может быть немного превышена. Объём для проверки кэшируется в памяти на 30 с.
- Сирота определяется по паре (хранилище, blob id): копия blob в «чужом» хранилище (например, после прерванной миграции) — тоже сирота.

### 7.6. Управление хранилищами

Таблица `blob_stores` (`filesystem` / `s3` + параметры, `quota_bytes`). Управление — через UI/API (admin):

| Операция | Правила |
|---|---|
| Создать | имя `[a-z0-9-]`, уникальное; путь — **произвольный абсолютный** (внутри контейнера — путь в контейнере, каталог хоста монтируется bind mount); каталог создаётся при отсутствии; проверяются запись и отсутствие пересечения с путями других хранилищ (совпадение или вложенность) |
| Изменить | имя, квота — всегда; путь — только у пустого хранилища (нет blobs, включая ожидающие удаления, и нет миграции) |
| Удалить | только пустое хранилище без идущей миграции (позже — и без ссылок от репозиториев); файлы на диске не удаляются |
| Проверить | каталог существует (**не создаётся** — пропавшая точка монтирования не должна подменяться каталогом на другой ФС) и доступен для записи; в списке хранилище помечается «недоступно» |
| `default` | создаётся/обновляется при старте из `REPOMAN_STORAGE_PATH`; имя и путь не меняются, удалить нельзя; квота задаётся |

Произвольный путь означает, что администратор может направить запись в любой доступный процессу каталог; это допустимо, так как управление хранилищами есть только у роли `admin`.

### 7.7. Миграция между хранилищами

Задание `blob_migrate` (одновременно — одна миграция):

1. Blob копируется в целевое хранилище **под тем же id**, проверяются размер и sha256.
2. В БД `blob_store_id` переключается на целевое хранилище (только если blob не удалён за время копирования; иначе копия в цели удаляется).
3. Копия в источнике удаляется сразу; уже идущие чтения не ломаются (открытый файл в Linux переживает unlink).
4. Задание продолжается после рестарта с checkpoint, отменяемо; blobs, записанные в источник во время миграции, переносятся повторными проходами.
5. Отсутствующий в источнике или повреждённый blob пропускается и отражается в журнале; задание завершается ошибкой с числом пропущенных.

Сейчас доступен перенос всего содержимого хранилища (`POST /blob-stores/{id}/migrate`, с подтверждением в UI). Вместе с репозиториями: хранилище выбирается при создании репозитория, а смена хранилища в настройках репозитория запускает миграцию blobs этого репозитория (после подтверждения).

Удалённые (ожидающие grace period) blobs не переносятся — их удаляет `blob_gc` в исходном хранилище.

### 7.8. Бэкап

- **Proxy-кэш** восстановим из upstream: бэкап хранилища — по желанию, БД — обязательно.
- **Hosted-данные** невосстановимы: обязательно бэкап БД **и** хранилища, в порядке «сначала БД, затем хранилище». Grace period гарантирует, что объекты, на которые ссылается бэкап БД, ещё есть в хранилище на момент его бэкапа (бэкап хранилища должен завершиться быстрее grace period).
- **Во время миграции бэкап не снимать:** копия в источнике удаляется сразу после переключения, поэтому бэкап, снятый в процессе, может быть несогласованным.

---

## 8. Аутентификация и авторизация

### 8.1. Пользователи

- `username` уникален (хранится в нижнем регистре), `auth_source` = `local` | `ldap` фиксируется при создании.
- Атрибуты: `first_name`, `last_name`, `display_name`, `email`.
- `is_active` + `blocked_by` = `admin` | `ldap_sync`.
- Самостоятельной регистрации нет: пользователей создаёт admin (local) или они создаются при первом входе через AD.
- Создать локального пользователя с именем, существующим в AD, нельзя (проверка при создании, если LDAP включён).
- **Пароль** (local): минимум 8 символов; сложность и совпадение с логином не проверяются.
- **`must_change_password`:** выставляется при создании пользователя администратором и при сбросе пароля администратором. Пока пароль не сменён, пользователю доступны только `/me`, смена своего пароля и выход.
- **Удаление:** локальных пользователей — разрешено (кроме себя и последнего активного admin); доменных — только блокировка (иначе синхронизация/вход через AD пересоздаст запись).
- Профиль доменного пользователя (имя, email) не редактируется в RepoMan — источник AD.

### 8.2. Вход

1. Имя нормализуется: отрезается префикс `DOMAIN\`, приводится к нижнему регистру.
2. Пользователь есть в БД → проверка через его `auth_source`.
3. Пользователя нет и LDAP включён → поиск в AD; при успехе создаётся пользователь (`auth_source=ldap`).
4. Заблокированный пользователь войти не может.
5. Rate limit неудачных попыток по `username + IP` (в памяти процесса).

Локальные пользователи работают всегда, в т.ч. при недоступности AD (break-glass admin).

### 8.3. Сессии (UI)

- Серверные сессии в PostgreSQL; в cookie — случайный id, в БД — его хэш.
- Cookie: `HttpOnly`, `SameSite=Lax`, `Secure` при HTTPS.
- CSRF (double submit): при входе backend ставит cookie `repoman_csrf` (читаемую JS; сессионная cookie — `repoman_session`), SPA передаёт значение в заголовке `X-CSRF-Token` на всех изменяющих запросах с cookie-сессией. Запросы с Bearer/Basic-токеном CSRF не проверяют.
- Idle и absolute таймауты (§5).
- Блокировка пользователя или смена пароля удаляет все его сессии.

### 8.4. API-токены

- Формат: `rpm_` + 32 случайных байта (base64url). В БД — sha256 и префикс для отображения. Показывается один раз при создании.
- Срок действия: по умолчанию 90 дней, можно указать другой или «бессрочный». `last_used_at`, отзыв (удаление).
- Токен действителен, только пока пользователь активен.
- Использование:
  - API: `Authorization: Bearer <token>` или Basic `username:<token>`;
  - `/repository/**`: Basic `username:<token>` (apt: `/etc/apt/auth.conf.d/*.conf`).
- **Пароли (локальные и AD) в Basic не принимаются** — только токены. Пароль используется только в форме входа UI / `POST /api/v1/auth/login`.

### 8.5. RBAC

- Роль — набор прав на репозитории. В MVP одно право: `read` (в будущем `write`/`deploy`).
- Встроенные роли (не удаляются):
  - `anonymous` — права любого запроса;
  - `authenticated` — права любого вошедшего пользователя;
  - `admin` — полный доступ ко всему, включая управление.
- Пользовательские роли создаёт admin. CRUD пользовательских ролей и права в ролях добавляются по мере появления функционала (первыми — права `read` вместе с репозиториями); до этого назначается только встроенная роль `admin`.
- Роль назначается пользователю вручную (`source=manual`) или по маппингу группы AD (`source=ldap`).
- Эффективные роли запроса: `{anonymous}` ∪ (если аутентифицирован: `{authenticated}` ∪ роли пользователя).
- Права кэшируются в памяти процесса, кэш инвалидируется при изменении ролей/прав/пользователей.

**Видимость:** каждый видит в UI/API ровно те репозитории, которые может читать. Аноним — только анонимные, user — анонимные и выданные ему, admin — все.

**Отказ в доступе к `/repository/**`:**
- без аутентификации → `401` + `WWW-Authenticate: Basic` (одинаково для закрытого и несуществующего репозитория — не раскрываем существование);
- аутентифицирован, нет права → `404`.

**Права ролей пользователей (не admin):** просмотр доступных репозиториев, смена своего пароля (только local), управление своими API-токенами.

**Защита:** нельзя удалить, заблокировать или лишить роли `admin` последнего активного администратора.

### 8.6. Первый администратор

При старте, если в БД нет ни одного активного admin: создаётся локальный пользователь `REPOMAN_ADMIN_USER` (default `admin`) с паролем `REPOMAN_ADMIN_PASSWORD`. Если пароль не задан — генерируется и однократно выводится в лог.

---

## 9. Active Directory

### 9.1. Настройки (UI/API, хранятся в БД)

| Параметр | Описание |
|---|---|
| `enabled` | |
| `mode` | `ldap` / `starttls` / `ldaps` (default `ldaps`) |
| `host`, `port` | |
| `verify_certificate` | default `true`; `false` — сертификат сервера не проверяется (см. ниже) |
| `ca_certificate` | PEM корпоративного CA (если не задан — системные CA) |
| `bind_dn`, `bind_password` | сервисная учётка (`DOMAIN\user` или DN); пароль шифруется (Fernet, ключ из `REPOMAN_SECRET_KEY` через HKDF), через API только записывается |
| `user_base_dn` | **где искать пользователей** (поиск по поддереву); определяет, кто может войти |
| `user_filter` | необязательный дополнительный LDAP-фильтр (например, членство в группе) |
| `attribute_map` | default: `username=sAMAccountName`, `first_name=givenName`, `last_name=sn`, `display_name=displayName`, `email=mail` |
| `group_mappings` | группа AD (DN) → роль RepoMan (включая `admin`); только для ролей, не для доступа |

**Доступ** (модель GitLab/Nexus): войти может активный пользователь, найденный в `user_base_dn` с базовым фильтром `(&(objectCategory=person)(objectClass=user))` и `user_filter`. Привязки к группе для входа нет; войти без ролей → роль `authenticated`.

**TLS:**
- `ldaps` / `starttls` с `verify_certificate=true`: проверяются цепочка (CA из `ca_certificate` или системные) и имя хоста (должно быть в SAN сертификата DC).
- `verify_certificate=false`: сертификат не проверяется. Трафик зашифрован, но не защищён от MITM — пароли пользователей и сервисной учётки может перехватить атакующий в сети. UI показывает явное предупреждение.
- `ldap` без TLS: пароли передаются открытым текстом, UI показывает предупреждение. Работает только с DC без требования подписи LDAP (в Windows Server 2025 подпись требуется по умолчанию — тогда bind отклоняется с `strongerAuthRequired`, «Проверить подключение» показывает понятную ошибку). Подписанный bind без TLS (Kerberos/SASL) — вне MVP.

- Кнопка / endpoint «Проверить подключение» (опционально — с поиском тестового пользователя и показом его групп/ролей).
- Один домен; Kerberos/SSO — вне MVP.

### 9.2. Вход через AD

1. Логин нормализуется: `DOMAIN\user`, `user@domain` → `user` (в нижнем регистре).
2. Поиск под сервисной учёткой по `sAMAccountName` в `user_base_dn` + фильтры.
3. Bind под найденным DN с паролем пользователя.
4. Проверка: учётка не отключена (`userAccountControl`, бит `ACCOUNTDISABLE`).
5. Группы — по атрибуту `tokenGroups` пользователя (транзитивный список SID, включая вложенные группы и основную группу `primaryGroupID`, которую `member`/`memberOf` и `LDAP_MATCHING_RULE_IN_CHAIN` не отражают); сравнение с `objectSid` групп из маппинга.
6. Создание/обновление пользователя (атрибуты, `ldap_dn`, `ldap_object_guid`), пересчёт ролей `source=ldap`.
7. Пока LDAP включён, создать локального пользователя с именем, найденным в AD, нельзя.

### 9.3. Синхронизация по расписанию

Job `ldap_sync`, по расписанию (`ldap_sync_interval`, default 1 ч) и вручную (кнопка в UI / `POST /api/v1/ldap/sync`).

Для каждого пользователя с `auth_source=ldap` (поиск по `objectGUID` — стабилен при переименовании/перемещении):

| Состояние в AD | Действие |
|---|---|
| отключён / удалён / больше не находится в `user_base_dn` + фильтрах | блокировка (`blocked_by=ldap_sync`), сессии удаляются, токены перестают действовать; запись не удаляется |
| изменились атрибуты | обновление `first_name`, `last_name`, `display_name`, `email`, `username` (если нет коллизии) |
| изменились группы | пересчёт ролей `source=ldap`; роли `source=manual` не трогаются |
| снова активен | разблокировка, только если `blocked_by=ldap_sync` |

**Защиты:**
- Ошибка подключения/поиска → job `failed`, изменений нет, последнее известное состояние сохраняется.
- Если доля пользователей к блокировке превышает `ldap_sync_max_block_ratio` (default 50%) → job `failed` без изменений (защита от ошибки в Base DN/фильтре).

Следствия: в hot-path прокси нет LDAP-запросов; при недоступности AD apt-клиенты продолжают работать по токенам. Отзыв доступа — с задержкой до интервала синхронизации; для немедленного отзыва admin блокирует пользователя вручную.

UI показывает время, результат (проверено / заблокировано / изменено) и ошибку последней синхронизации.

---

## 10. Фоновые задания

### 10.1. Почему PostgreSQL, а не брокер

Задачи (синхронизация AD, очистка, реиндекс, миграция) — редкие, долгие (миграция 500 ГБ — часы), требуют состояния, прогресса, истории, отмены, продолжения после рестарта и эксклюзивности на ресурс. Брокер (RabbitMQ) этого не даёт — таблица заданий в PostgreSQL нужна в любом случае; кроме того: постановка задания в одной транзакции с изменением данных, нет проблемы `consumer_timeout` для долгих задач, нет дополнительного компонента в эксплуатации.

Очередь скрыта за интерфейсом `JobQueue` (`enqueue`, `claim`, `heartbeat`, `checkpoint`, `complete`, `fail`) — при переходе на multi-node можно добавить реализацию на брокере без переписывания задач.

### 10.2. Механика

- Таблица `jobs`: `queued → running → succeeded | failed | cancelled`.
- Воркеры — asyncio-задачи в том же процессе; забор через `SELECT … FOR UPDATE SKIP LOCKED`.
- `heartbeat_at` обновляется во время выполнения; задание с просроченным heartbeat (после падения процесса) возвращается в очередь и продолжается с `checkpoint`.
- `checkpoint` (jsonb) — курсор прогресса для продолжения после рестарта.
- `progress_done` / `progress_total`, журнал `job_logs`.
- Отмена: `cancel_requested=true`, задача проверяет флаг между шагами.
- Эксклюзивность: `resource_key` (например `repository:{id}`) + частичный уникальный индекс для статусов `queued`/`running`.
- Лимит параллельных тяжёлых (I/O) заданий — 1.
- Планировщик: таблица `schedules` (`job_type`, `interval`, `next_run_at`, `enabled`), проверка раз в 30 с.

### 10.3. Типы заданий

| Тип | MVP |
|---|---|
| `ldap_sync` | ✅ |
| `repository_purge` | ✅ |
| `repository_delete` | ✅ |
| `repository_reconcile` — сверка blob store и БД: объекты без записей (сироты), записи без объектов, проверка размера и sha256 | вне MVP |
| `blob_store_migrate` — копирование, проверка sha256, атомарное переключение, удаление старых объектов | вне MVP |
| `cleanup_policy` | вне MVP |

---

## 11. Модель данных

```text
blob_stores        id, name, type, config jsonb, quota_bytes, created_at

blobs              id uuid, blob_store_id, size, sha256, created_at, deleted_at
                   INDEX (deleted_at) WHERE deleted_at IS NOT NULL

repositories       id, name, format, type, upstream_url, blob_store_id,
                   metadata_ttl, negative_ttl, serve_stale, online, status,
                   purged_at, description, created_at, updated_at

cache_entries      id, repository_id, path, kind (immutable|metadata), blob_id,
                   content_type, upstream_etag, upstream_last_modified,
                   fetched_at, checked_at, last_accessed_at
                   UNIQUE (repository_id, path)

negative_cache     repository_id, path, status_code, expires_at
                   PK (repository_id, path)

users              id, username (lowercase, unique), auth_source, password_hash,
                   must_change_password,
                   first_name, last_name, display_name, email,
                   is_active, blocked_by, ldap_dn, ldap_object_guid,
                   ldap_synced_at, last_login_at, created_at, updated_at

roles              id, name, builtin, description
role_permissions   role_id, repository_id, permission       PK (role_id, repository_id, permission)
user_roles         user_id, role_id, source (manual|ldap)   PK (user_id, role_id, source)

api_tokens         id, user_id, name, prefix, token_hash, expires_at,
                   last_used_at, created_at, revoked_at

sessions           id_hash, user_id, csrf_token, created_at, last_seen_at,
                   expires_at, ip, user_agent

ldap_settings      singleton (§9.1), bind_password_encrypted
ldap_group_mappings id, group_dn, role_id

system_settings    key, value jsonb

jobs               id, type, resource_key, status, params jsonb, checkpoint jsonb,
                   progress_done, progress_total, attempts, max_attempts, error,
                   cancel_requested, created_by, created_at, scheduled_at,
                   started_at, heartbeat_at, finished_at
job_logs           id, job_id, ts, level, message
schedules          job_type, interval_seconds, next_run_at, enabled
```

Миграции схемы — Alembic, применяются при старте.

---

## 12. REST API (v1)

Формат ошибок: `{"error": {"code": "...", "message": "...", "details": {...}}}`. `code` — стабильный машиночитаемый идентификатор (например `repository_not_found`, `last_admin`); frontend переводит ошибки по `code`, `message` — на английском для потребителей API. Пагинация: `limit` / `offset`. Секреты только записываются и никогда не возвращаются.

**Система (публично)**
```text
GET    /api/v1/system/info                # версия, base_url (если задан), включён ли LDAP
```

**Аутентификация и профиль**
```text
POST   /api/v1/auth/login                 # username + password → сессия
POST   /api/v1/auth/logout
GET    /api/v1/me
PUT    /api/v1/me/password                # только local
GET    /api/v1/me/tokens
POST   /api/v1/me/tokens                  # токен возвращается один раз
DELETE /api/v1/me/tokens/{id}
```

**Репозитории**
```text
GET    /api/v1/repositories               # только доступные на чтение
POST   /api/v1/repositories               # admin
GET    /api/v1/repositories/{name}        # + статистика: объектов, объём
PATCH  /api/v1/repositories/{name}        # admin
DELETE /api/v1/repositories/{name}        # admin → 202 + job
POST   /api/v1/repositories/{name}/purge  # admin → 202 + job
```

**Пользователи и роли (admin)**
```text
GET|POST         /api/v1/users
GET|PATCH|DELETE /api/v1/users/{id}
POST             /api/v1/users/{id}/block
POST             /api/v1/users/{id}/unblock
PUT              /api/v1/users/{id}/password      # только local
PUT              /api/v1/users/{id}/roles         # роли source=manual
GET              /api/v1/users/{id}/tokens
DELETE           /api/v1/users/{id}/tokens/{tid}

GET|POST         /api/v1/roles
GET|PATCH|DELETE /api/v1/roles/{id}
PUT              /api/v1/roles/{id}/permissions
```

**LDAP (admin)**
```text
GET|PUT          /api/v1/ldap/settings
POST             /api/v1/ldap/test
POST             /api/v1/ldap/sync                 # → 202 + job
GET              /api/v1/ldap/sync/status
GET|POST         /api/v1/ldap/group-mappings
DELETE           /api/v1/ldap/group-mappings/{id}
```

**Система (admin)**
```text
GET|PATCH        /api/v1/settings
GET|POST         /api/v1/blob-stores
GET|PATCH|DELETE /api/v1/blob-stores/{id}
POST             /api/v1/blob-stores/{id}/check
POST             /api/v1/blob-stores/{id}/migrate   # → 202 + job
GET              /api/v1/jobs
GET              /api/v1/jobs/{id}
GET              /api/v1/jobs/{id}/logs
POST             /api/v1/jobs/{id}/cancel
```

---

## 13. Web UI

SPA (React + Mantine) в отдельном контейнере, работает только через REST API.

| Страница | Доступ |
|---|---|
| `/` — главная: описание проекта и таблица форматов из README, ссылки на UI и Swagger | публичная |
| `/login` | публичная |
| `/repositories` — список доступных репозиториев | по правам |
| `/repositories/{name}` — детали, готовые конфиги apt (one-line и deb822 `.sources`), статистика; для admin — редактирование, «Очистить», «Удалить» | по правам |
| `/profile` — смена пароля (local), API-токены | вошедший |
| `/admin/users`, `/admin/roles` | admin |
| `/admin/ldap` — настройки, проверка, маппинг групп, статус синхронизации, «Синхронизировать сейчас» | admin |
| `/admin/settings` — системные defaults | admin |
| `/admin/jobs` — задания, прогресс, логи, отмена | admin |

Ограничение доступа к страницам на frontend — только UX; права всегда проверяет backend.

**Темы:** светлая и тёмная; по умолчанию — по настройке ОС (`prefers-color-scheme`), переключатель в шапке, выбор сохраняется в `localStorage`.

**i18n:** ru и en с первой версии.
- Все строки UI — через ключи i18next (`src/i18n/ru.json`, `en.json`), без захардкоженного текста в компонентах.
- Язык: сохранённый выбор → язык браузера (если ru/en) → ru. Переключатель в шапке.
- Даты, числа, размеры — через `Intl` с учётом языка.
- Ошибки API переводятся по `error.code` (§12).
- CI проверяет, что наборы ключей в `ru.json` и `en.json` совпадают.

Пример конфига, который показывает UI (deb822, Ubuntu 24.04+):

```text
Types: deb
URIs: https://repo.company.local/repository/ubuntu/
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

Для закрытого репозитория дополнительно — пример `/etc/apt/auth.conf.d/repoman.conf` с токеном.

---

## 14. Bootstrap-конфигурация (env)

| Переменная | Описание |
|---|---|
| `REPOMAN_DATABASE_URL` | DSN PostgreSQL (обязательно) |
| `REPOMAN_STORAGE_PATH` | корень default filesystem blob store (обязательно) |
| `REPOMAN_SECRET_KEY` | ключ шифрования секретов в БД (обязательно) |
| `REPOMAN_LISTEN` | default `0.0.0.0:8000` |
| `REPOMAN_BASE_URL` | внешний URL (опционально) |
| `REPOMAN_TRUSTED_PROXIES` | CIDR доверенных reverse proxy |
| `REPOMAN_ADMIN_USER`, `REPOMAN_ADMIN_PASSWORD` | первый администратор |
| `REPOMAN_CA_BUNDLE` | дополнительный CA для upstream |
| `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` | egress-прокси к upstream |
| `REPOMAN_METRICS_TOKEN` | если задан — `/metrics` требует Bearer |
| `REPOMAN_LOG_LEVEL` | default `INFO` |

Потеря `REPOMAN_SECRET_KEY` → потребуется заново ввести пароль сервисной учётки LDAP. Ротация ключа — вне MVP.

---

## 15. Наблюдаемость

- Логи в JSON (stdout), access log с репозиторием, путём, статусом, `X-RepoMan-Cache`, размером, длительностью, пользователем.
- `/healthz` — процесс жив; `/readyz` — БД доступна, хранилище доступно на запись.
- Метрики Prometheus:
  - `repoman_requests_total{repository,cache_status,code}`
  - `repoman_bytes_served_total{repository}`, `repoman_bytes_fetched_total{repository}`
  - `repoman_upstream_errors_total{repository,reason}`
  - `repoman_singleflight_joins_total{repository}`
  - `repoman_stale_served_total{repository}`
  - `repoman_storage_free_bytes`, `repoman_storage_full`
  - `repoman_jobs{type,status}`, `repoman_ldap_sync_last_success_timestamp`

---

## 16. Безопасность

- TLS-проверка upstream и LDAPS всегда включена.
- Пароли — argon2id; токены и id сессий — хранится только хэш.
- Секреты в БД (bind-пароль) — зашифрованы, через API не возвращаются, не логируются.
- CSRF для UI, безопасные cookie, rate limit входа.
- Нормализация путей против path traversal (§3).
- Basic для `/repository/**` и API — только с токенами.
- Аудит-лог действий администратора — вне MVP (кандидат на следующую итерацию).

---

## 17. Развёртывание

| Контейнер | Образ | Порт |
|---|---|---|
| `backend` | `backend/Dockerfile` (`python:3.12-slim`), один uvicorn worker | 8000 |
| `frontend` | `frontend/Dockerfile`: сборка на Node 24 LTS → `nginx-unprivileged`, только статика + SPA fallback | 8080 |
| `postgres` | PostgreSQL 15+ | 5432 |
| `proxy` | nginx с `deploy/nginx/repoman.conf` (только в dev compose; в prod — свой reverse proxy) | 80 |

- `docker-compose.dev.yml`: `postgres` + `backend` + `frontend` + `proxy`; образы backend и frontend собираются при запуске (`build:`), volume для хранилища. Снаружи публикуются `proxy` (основная точка входа) и `backend` (для работы с API/Swagger напрямую).
- Готовые образы на этапе MVP не собираются и не публикуются.
- Целевая ОС — Linux.
- Запуск на подпути (`/repoman/...`) не поддерживается: RepoMan обслуживается от корня хоста.
- **Хранилище в prod — bind mount** каталога хоста (например, `/srv/repoman/storage` → `/var/lib/repoman`) на локальной ФС (ext4/xfs, не NFS). Процесс в контейнере работает под uid `10001`: каталог `chown 10001:10001`, либо uid переопределяется через `user:` в compose. Объём — с запасом над размером кэша (для 500 ГБ — от 600 ГБ). Бэкап — §7.8.

### 17.1. CI

GitHub Actions на push и pull request, два независимых job:
- **backend:** `ruff check`, `ruff format --check`, `pytest` (unit-тесты без внешних зависимостей);
- **frontend:** `npm ci`, `eslint`, `prettier --check`, `tsc --noEmit`, проверка совпадения ключей i18n, `vite build`.

Сборка и публикация образов — вне MVP.

### 17.2. Reverse proxy

Маршрутизация выполняется внешним reverse proxy (nginx / LB), который также терминирует TLS:

```text
/              → frontend:8080
/api/          → backend:8000
/repository/   → backend:8000
```

Frontend не находится на пути apt-трафика и запросов автоматизации. Backend доступен и напрямую (без UI).

Требования к location `/repository/` (пример — `deploy/nginx/repoman.conf`):

```nginx
location /repository/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    proxy_buffering off;              # отдавать по мере получения
    proxy_request_buffering off;
    proxy_max_temp_file_size 0;       # не откладывать большие ответы во временные файлы
    proxy_read_timeout 300s;          # больше upstream_read_timeout backend
    proxy_send_timeout 300s;

    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
}
```

- На `/repository/` не включать `proxy_cache` и `gzip`: кэш — в backend, пакеты и индексы уже сжаты.
- `Range`, `HEAD`, условные заголовки пробрасываются nginx по умолчанию.
- Адрес reverse proxy должен входить в `REPOMAN_TRUSTED_PROXIES`.

---

## 18. Тестирование и приёмка

- **Unit:** классификация путей, TTL/serve_stale-логика, нормализация путей, вычисление эффективных прав, нормализация логина, защита от массовой блокировки.
- **Integration** (pytest + реальный PostgreSQL + локальный fake upstream):
  - 50 параллельных запросов одного отсутствующего файла → ровно 1 запрос к upstream, все клиенты получают корректный файл;
  - отключение первого клиента не прерывает загрузку;
  - upstream недоступен + истёкший metadata → `STALE` при `serve_stale=true`, `502/504` при `false`;
  - negative cache, `Range`, `HEAD`, `304`;
  - очистка во время активной загрузки;
  - RBAC: аноним / user / admin, `401` vs `404`, видимость репозиториев;
  - jobs: продолжение с checkpoint после «падения», эксклюзивность, отмена.
- **LDAP:** unit с `ldap3` MOCK; интеграционно — Samba AD DC в контейнере (вложенные группы, `userAccountControl`).
- **E2E:** контейнеры `ubuntu:24.04` и `ubuntu:26.04` выполняют `apt update && apt install <пакеты>` через RepoMan (archive, security, один сторонний репозиторий, например docker-ce); повтор при недоступном upstream.

---

## 19. Этапы реализации

1. **Каркас:**
   - backend: pyproject, конфигурация, БД + Alembic, Dockerfile, `/healthz`, `/readyz`, `/api/v1/system/info`, Swagger;
   - frontend: Vite + React + Mantine, темы, i18n ru/en, layout с шапкой, главная страница, Dockerfile;
   - `deploy/nginx/repoman.conf`, `docker-compose.dev.yml`, CI (GitHub Actions).
2. **Локальные пользователи:** пользователи, встроенные роли, сессии, CSRF, API-токены, первый admin, rate limit входа; API `/auth`, `/me`, `/users`, `/roles`; UI: вход, профиль (пароль, токены), администрирование пользователей.
3. **AD:** фреймворк заданий (очередь, воркеры, планировщик), настройки LDAP, проверка подключения, вход, маппинг групп, `ldap_sync`; UI настроек AD.
4. **Хранилище:** модель blob ID, BlobStore (filesystem), таблицы `blob_stores` / `blobs`, сервис записи/чтения blobs, задания `blob_gc` и `blob_store_cleanup`, контроль свободного места; API и UI хранилищ.
5. **APT proxy:** классификатор, cache policy, single-flight, negative cache, serve_stale, Range/HEAD, pass-through при нехватке места; CRUD репозиториев, пользовательские роли и право `read`, Basic с токеном для apt; очистка и удаление репозиториев; UI репозиториев и ролей.
6. **S3 blob store** (стандартный S3 API, тесты на SeaweedFS).
7. **Наблюдаемость и приёмка:** метрики, JSON-логи, E2E на Ubuntu 24.04 / 26.04, документация по развёртыванию.

UI каждой функции делается в том же этапе, что и её API.

---

## 20. Решения, принятые по умолчанию

Не обсуждались явно, приняты как предложения:

1. Стек §2.1.
2. Поддержка `HTTPS_PROXY` / `NO_PROXY` и `REPOMAN_CA_BUNDLE` для upstream.
3. Сторонние APT-репозитории поддерживаются за счёт классификации по пути; в E2E проверяется один (docker-ce).
4. Default TTL: metadata 30 мин, negative 5 мин, `serve_stale=true`.
5. При нехватке места — pass-through без кэширования.
6. `/metrics` открыт, если не задан `REPOMAN_METRICS_TOKEN`.
7. Целевая ОС — Linux; Windows/macOS не гарантируются для filesystem blob store.

## 21. Открытые вопросы

Нет.
