"""Authentication policy constants.

Session timeouts become configurable once system settings are stored in the database.
"""

from datetime import timedelta

SESSION_COOKIE = "repoman_session"
CSRF_COOKIE = "repoman_csrf"
CSRF_HEADER = "X-CSRF-Token"

SESSION_IDLE_TIMEOUT = timedelta(hours=12)
SESSION_ABSOLUTE_TIMEOUT = timedelta(days=7)
# last_seen_at / last_used_at are written at most this often to avoid a write per request.
ACTIVITY_UPDATE_INTERVAL = timedelta(minutes=1)

API_TOKEN_DEFAULT_LIFETIME_DAYS = 90
API_TOKEN_MAX_LIFETIME_DAYS = 3650

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
