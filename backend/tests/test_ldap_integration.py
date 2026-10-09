"""Ldap3Directory against a real AD-compatible server (skipped unless configured).

Environment:
  REPOMAN_TEST_LDAP_MODE           ldap | starttls | ldaps
  REPOMAN_TEST_LDAP_HOST, _PORT
  REPOMAN_TEST_LDAP_VERIFY         "true" (default) or "false"
  REPOMAN_TEST_LDAP_CA_FILE        optional PEM file
  REPOMAN_TEST_LDAP_BIND_DN, _BIND_PASSWORD
  REPOMAN_TEST_LDAP_BASE_DN
  REPOMAN_TEST_LDAP_USER, _USER_PASSWORD   an active user
  REPOMAN_TEST_LDAP_GROUP_DN               a group the user belongs to (directly or nested)
  REPOMAN_TEST_LDAP_DISABLED_USER          optional disabled user
"""

import os
from pathlib import Path

import pytest

from repoman.ldap.directory import Ldap3Directory, LdapConfig


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"REPOMAN_TEST_LDAP_{name}", default)


pytestmark = pytest.mark.skipif(not env("HOST"), reason="REPOMAN_TEST_LDAP_HOST is not set")


@pytest.fixture
def directory() -> Ldap3Directory:
    ca_file = env("CA_FILE")
    mode = env("MODE", "ldaps")
    return Ldap3Directory(
        LdapConfig(
            mode=mode,
            host=env("HOST"),
            port=int(env("PORT", "636" if mode == "ldaps" else "389")),
            verify_certificate=env("VERIFY", "true") == "true",
            ca_certificate=Path(ca_file).read_text() if ca_file else None,
            bind_dn=env("BIND_DN"),
            bind_password=env("BIND_PASSWORD"),
            user_base_dn=env("BASE_DN"),
            user_filter=None,
        )
    )


def test_connection(directory: Ldap3Directory) -> None:
    directory.check_connection()


def test_authenticate_and_groups(directory: Ldap3Directory) -> None:
    username = env("USER")
    user = directory.authenticate(username, env("USER_PASSWORD"))
    assert user is not None and user.username == username.lower() and not user.disabled
    assert directory.authenticate(username, "definitely-wrong-password") is None
    assert directory.authenticate(username, "") is None

    group_dn = env("GROUP_DN")
    sids = directory.group_sids([group_dn])
    assert sids[group_dn] in user.group_sids

    same = directory.find_by_guid(user.guid)
    assert same is not None and same.dn == user.dn


def test_disabled_user(directory: Ldap3Directory) -> None:
    name = env("DISABLED_USER")
    if not name:
        pytest.skip("REPOMAN_TEST_LDAP_DISABLED_USER is not set")
    found = directory.find_user(name)
    assert found is not None and found.disabled
    assert directory.authenticate(name, env("USER_PASSWORD")) is None
