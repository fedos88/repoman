import copy
import uuid
from dataclasses import dataclass, field

from repoman.ldap.directory import DirectoryUser, LdapConfig, LdapError

ADMINS_DN = "CN=RepoMan-Admins,OU=Groups,DC=example,DC=test"
USERS_DN = "CN=RepoMan-Users,OU=Groups,DC=example,DC=test"
ADMINS_SID = "S-1-5-21-1-2-3-1106"
USERS_SID = "S-1-5-21-1-2-3-1107"
DOMAIN_USERS_SID = "S-1-5-21-1-2-3-513"


@dataclass
class FakeDirectory:
    """In-memory replacement of Ldap3Directory."""

    users: dict[str, tuple[DirectoryUser, str]] = field(default_factory=dict)
    groups: dict[str, str] = field(
        default_factory=lambda: {ADMINS_DN: ADMINS_SID, USERS_DN: USERS_SID}
    )
    error: LdapError | None = None
    configs: list[LdapConfig] = field(default_factory=list)

    def add_user(
        self,
        username: str,
        password: str = "domain-pass",
        *,
        groups: set[str] | None = None,
        disabled: bool = False,
        display_name: str | None = None,
        email: str | None = None,
    ) -> DirectoryUser:
        user = DirectoryUser(
            dn=f"CN={username},OU=Users,DC=example,DC=test",
            guid=str(uuid.uuid4()),
            username=username,
            first_name=None,
            last_name=None,
            display_name=display_name or username,
            email=email,
            disabled=disabled,
            group_sids={DOMAIN_USERS_SID, *(groups or set())},
        )
        self.users[username] = (user, password)
        return user

    def factory(self, config: LdapConfig) -> "FakeDirectory":
        self.configs.append(config)
        return self

    def _check(self) -> None:
        if self.error is not None:
            raise self.error

    def check_connection(self) -> None:
        self._check()

    def find_user(self, username: str) -> DirectoryUser | None:
        self._check()
        entry = self.users.get(username)
        return copy.deepcopy(entry[0]) if entry else None

    def authenticate(self, username: str, password: str) -> DirectoryUser | None:
        self._check()
        entry = self.users.get(username)
        if entry is None or not password or entry[1] != password or entry[0].disabled:
            return None
        return copy.deepcopy(entry[0])

    def find_by_guid(self, guid: str) -> DirectoryUser | None:
        self._check()
        for user, _ in self.users.values():
            if user.guid == guid:
                return copy.deepcopy(user)
        return None

    def group_sids(self, group_dns: list[str]) -> dict[str, str]:
        self._check()
        return {dn: self.groups[dn] for dn in group_dns if dn in self.groups}
