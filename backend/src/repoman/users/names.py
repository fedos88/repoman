import re

LOCAL_USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,63}$"
_LOCAL_USERNAME_RE = re.compile(LOCAL_USERNAME_PATTERN)


def normalize_login(value: str) -> str:
    """Normalize a login name: trim, drop `DOMAIN\\` and `@domain`, lowercase.

    Local usernames cannot contain `\\` or `@`, so this never changes a local name.
    """
    return value.strip().rpartition("\\")[2].partition("@")[0].lower()


def is_valid_local_username(value: str) -> bool:
    return _LOCAL_USERNAME_RE.fullmatch(value) is not None
