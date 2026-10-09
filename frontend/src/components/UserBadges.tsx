import { Badge, Group, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import type { User } from '../api/client';

export function SourceBadge({ source }: { source: User['auth_source'] }) {
  const { t } = useTranslation();
  return (
    <Badge variant="light" color={source === 'ldap' ? 'grape' : 'gray'}>
      {t(`users.sources.${source}`)}
    </Badge>
  );
}

export function RoleBadges({ roles }: { roles: string[] }) {
  if (roles.length === 0) {
    return <Text c="dimmed">—</Text>;
  }
  return (
    <Group gap={4}>
      {roles.map((role) => (
        <Badge key={role} variant="light" color={role === 'admin' ? 'red' : 'blue'}>
          {role}
        </Badge>
      ))}
    </Group>
  );
}

export function StatusBadge({ user }: { user: User }) {
  const { t } = useTranslation();
  if (user.is_active) {
    return (
      <Badge variant="light" color="teal">
        {t('users.status.active')}
      </Badge>
    );
  }
  return (
    <Badge variant="light" color="red">
      {user.blocked_by === 'ldap_sync'
        ? t('users.status.blockedByLdap')
        : t('users.status.blocked')}
    </Badge>
  );
}
