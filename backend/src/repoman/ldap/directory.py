"""Active Directory access over LDAP (ldap3).

ldap3 is synchronous: callers run these methods in a thread (see repoman.ldap.service).
"""

import ssl
import struct
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import ldap3
from ldap3.core.exceptions import (
    LDAPException,
    LDAPInvalidFilterError,
    LDAPSocketOpenError,
    LDAPStartTLSError,
)
from ldap3.utils.conv import escape_filter_chars

# userAccountControl flag
ACCOUNTDISABLE = 0x2
BASE_USER_FILTER = "(&(objectCategory=person)(objectClass=user))"
CONNECT_TIMEOUT = 10
RECEIVE_TIMEOUT = 30


@dataclass(frozen=True)
class LdapConfig:
    mode: str  # ldap | starttls | ldaps
    host: str
    port: int
    verify_certificate: bool
    ca_certificate: str | None
    bind_dn: str
    bind_password: str
    user_base_dn: str
    user_filter: str | None
    attr_username: str = "sAMAccountName"
    attr_first_name: str = "givenName"
    attr_last_name: str = "sn"
    attr_display_name: str = "displayName"
    attr_email: str = "mail"


@dataclass
class DirectoryUser:
    dn: str
    guid: str
    username: str
    first_name: str | None
    last_name: str | None
    display_name: str | None
    email: str | None
    disabled: bool
    # Transitive group membership (tokenGroups), as SID strings.
    group_sids: set[str] = field(default_factory=set)


class LdapError(Exception):
    """LDAP failure with a stable code for the API (see errors in the frontend)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Directory(Protocol):
    def check_connection(self) -> None: ...

    def find_user(self, username: str) -> DirectoryUser | None: ...

    def authenticate(self, username: str, password: str) -> DirectoryUser | None: ...

    def find_by_guid(self, guid: str) -> DirectoryUser | None: ...

    def group_sids(self, group_dns: list[str]) -> dict[str, str]: ...


def sid_to_str(raw: bytes) -> str:
    revision = raw[0]
    count = raw[1]
    authority = int.from_bytes(raw[2:8], "big")
    subs = struct.unpack(f"<{count}I", raw[8 : 8 + 4 * count])
    return "S-" + "-".join(str(part) for part in (revision, authority, *subs))


def guid_filter_value(guid: str) -> str:
    return "".join(f"\\{byte:02x}" for byte in uuid.UUID(guid).bytes_le)


def _first(entry: dict, name: str) -> object | None:
    value = entry.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _text(entry: dict, name: str) -> str | None:
    value = _first(entry, name)
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value).strip() or None


def normalize_filter(user_filter: str | None) -> str:
    if not user_filter or not user_filter.strip():
        return ""
    value = user_filter.strip()
    return value if value.startswith("(") else f"({value})"


class Ldap3Directory:
    def __init__(self, config: LdapConfig) -> None:
        self.config = config

    # --- connection -----------------------------------------------------------------------

    def _server(self) -> ldap3.Server:
        tls = None
        if self.config.mode in ("ldaps", "starttls"):
            tls = ldap3.Tls(
                validate=ssl.CERT_REQUIRED if self.config.verify_certificate else ssl.CERT_NONE,
                ca_certs_data=self.config.ca_certificate or None,
            )
        return ldap3.Server(
            self.config.host,
            port=self.config.port,
            use_ssl=self.config.mode == "ldaps",
            tls=tls,
            get_info=ldap3.NONE,
            connect_timeout=CONNECT_TIMEOUT,
        )

    def _connect(self, user: str, password: str) -> ldap3.Connection:
        """Open a connection and bind; raises LdapError with a specific code."""
        connection = ldap3.Connection(
            self._server(),
            user=user,
            password=password,
            read_only=True,
            receive_timeout=RECEIVE_TIMEOUT,
            raise_exceptions=False,
        )
        try:
            connection.open()
            if self.config.mode == "starttls":
                connection.start_tls()
        except (OSError, LDAPSocketOpenError, LDAPStartTLSError) as exc:
            text = str(exc)
            if "CERTIFICATE_VERIFY_FAILED" in text or "certificate" in text.lower():
                raise LdapError(
                    "ldap_tls_error", f"TLS certificate validation failed: {text}"
                ) from None
            raise LdapError(
                "ldap_connection_failed", f"Cannot connect to LDAP server: {text}"
            ) from None
        except LDAPException as exc:
            raise LdapError(
                "ldap_connection_failed", f"Cannot connect to LDAP server: {exc}"
            ) from None
        if not connection.bind():
            result = connection.result or {}
            description = result.get("description")
            connection.unbind()
            if description == "strongerAuthRequired":
                raise LdapError(
                    "ldap_signing_required",
                    "The server requires LDAP signing: use LDAPS or StartTLS",
                )
            if description == "invalidCredentials":
                raise LdapError("ldap_invalid_credentials", "Invalid credentials")
            raise LdapError(
                "ldap_bind_failed", f"LDAP bind failed: {description} {result.get('message', '')}"
            )
        return connection

    def _service_connection(self) -> ldap3.Connection:
        try:
            return self._connect(self.config.bind_dn, self.config.bind_password)
        except LdapError as exc:
            if exc.code == "ldap_invalid_credentials":
                raise LdapError("ldap_bind_failed", "Service account bind failed") from None
            raise

    # --- queries --------------------------------------------------------------------------

    @property
    def _attributes(self) -> list[str]:
        c = self.config
        return [
            "objectGUID",
            "userAccountControl",
            c.attr_username,
            c.attr_first_name,
            c.attr_last_name,
            c.attr_display_name,
            c.attr_email,
        ]

    def _user_filter(self, condition: str) -> str:
        return f"(&{BASE_USER_FILTER}{condition}{normalize_filter(self.config.user_filter)})"

    def _search(self, connection: ldap3.Connection, base: str, ldap_filter: str, **kwargs) -> list:
        """Search returning entries; maps failures to LdapError."""
        try:
            connection.search(base, ldap_filter, **kwargs)
        except LDAPInvalidFilterError:
            raise LdapError("ldap_invalid_filter", "Invalid LDAP user filter") from None
        except LDAPException as exc:
            raise LdapError("ldap_search_failed", f"LDAP search failed: {exc}") from None
        result = connection.result or {}
        description = result.get("description")
        if description == "noSuchObject":
            raise LdapError("ldap_base_dn_not_found", f"Base DN not found: {base}")
        if description == "filterError":
            raise LdapError("ldap_invalid_filter", "Invalid LDAP user filter")
        if description not in ("success", "sizeLimitExceeded"):
            raise LdapError(
                "ldap_search_failed",
                f"LDAP search failed: {description} {result.get('message', '')}",
            )
        return [e for e in connection.response or [] if e.get("type") == "searchResEntry"]

    def _search_user(self, connection: ldap3.Connection, condition: str) -> DirectoryUser | None:
        entries = self._search(
            connection,
            self.config.user_base_dn,
            self._user_filter(condition),
            search_scope=ldap3.SUBTREE,
            attributes=self._attributes,
            size_limit=2,
        )
        if len(entries) != 1:
            return None
        entry = entries[0]
        attrs = entry.get("raw_attributes", {})
        guid_raw = _first(attrs, "objectGUID")
        uac = _text(attrs, "userAccountControl")
        c = self.config
        return DirectoryUser(
            dn=entry["dn"],
            guid=str(uuid.UUID(bytes_le=guid_raw)) if isinstance(guid_raw, bytes) else "",
            username=(_text(attrs, c.attr_username) or "").lower(),
            first_name=_text(attrs, c.attr_first_name),
            last_name=_text(attrs, c.attr_last_name),
            display_name=_text(attrs, c.attr_display_name),
            email=_text(attrs, c.attr_email),
            disabled=bool(int(uac) & ACCOUNTDISABLE) if uac and uac.isdigit() else False,
        )

    def _load_groups(self, connection: ldap3.Connection, user: DirectoryUser) -> None:
        # tokenGroups is computed by AD and can be read only with a base-scope search.
        entries = self._search(
            connection,
            user.dn,
            "(objectClass=*)",
            search_scope=ldap3.BASE,
            attributes=["tokenGroups"],
        )
        for entry in entries:
            for raw in entry.get("raw_attributes", {}).get("tokenGroups", []):
                user.group_sids.add(sid_to_str(raw))

    def check_connection(self) -> None:
        """Bind with the service account, check the base DN and the user filter."""
        connection = self._service_connection()
        try:
            self._search(
                connection,
                self.config.user_base_dn,
                "(objectClass=*)",
                search_scope=ldap3.BASE,
                attributes=["distinguishedName"],
            )
            self._search(
                connection,
                self.config.user_base_dn,
                self._user_filter(""),
                search_scope=ldap3.SUBTREE,
                attributes=["distinguishedName"],
                size_limit=1,
            )
        finally:
            connection.unbind()

    def find_user(self, username: str) -> DirectoryUser | None:
        attr = self.config.attr_username
        connection = self._service_connection()
        try:
            user = self._search_user(connection, f"({attr}={escape_filter_chars(username)})")
            if user is not None:
                self._load_groups(connection, user)
            return user
        finally:
            connection.unbind()

    def authenticate(self, username: str, password: str) -> DirectoryUser | None:
        # An empty password would be an unauthenticated bind, which LDAP servers accept.
        if not password:
            return None
        user = self.find_user(username)
        if user is None:
            return None
        try:
            self._connect(user.dn, password).unbind()
        except LdapError as exc:
            if exc.code == "ldap_invalid_credentials":
                return None
            raise
        return user

    def find_by_guid(self, guid: str) -> DirectoryUser | None:
        connection = self._service_connection()
        try:
            user = self._search_user(connection, f"(objectGUID={guid_filter_value(guid)})")
            if user is not None:
                self._load_groups(connection, user)
            return user
        finally:
            connection.unbind()

    def group_sids(self, group_dns: list[str]) -> dict[str, str]:
        if not group_dns:
            return {}
        connection = self._service_connection()
        result: dict[str, str] = {}
        try:
            for dn in group_dns:
                try:
                    entries = self._search(
                        connection,
                        dn,
                        "(objectClass=group)",
                        search_scope=ldap3.BASE,
                        attributes=["objectSid"],
                    )
                except LdapError as exc:
                    if exc.code == "ldap_base_dn_not_found":
                        continue  # mapped group no longer exists
                    raise
                for entry in entries:
                    raw = _first(entry.get("raw_attributes", {}), "objectSid")
                    if isinstance(raw, bytes):
                        result[dn] = sid_to_str(raw)
            return result
        finally:
            connection.unbind()
