import { Badge, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconPlus } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useMe } from '../api/auth';
import { errorMessage } from '../api/errors';
import { useDeleteOwnToken, useOwnTokens } from '../api/tokens';
import { ChangePasswordForm } from '../components/ChangePasswordForm';
import { CreateTokenModal } from '../components/CreateTokenModal';
import { RoleBadges, SourceBadge } from '../components/UserBadges';
import { TokensTable } from '../components/TokensTable';
import { formatDateTime } from '../utils/format';

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text component="div">{value || '—'}</Text>
    </Stack>
  );
}

export function ProfilePage() {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const tokens = useOwnTokens();
  const deleteToken = useDeleteOwnToken();
  const [createOpened, createModal] = useDisclosure(false);

  if (!me) {
    return null;
  }

  const confirmRevoke = (tokenId: number, name: string) =>
    modals.openConfirmModal({
      title: t('tokens.revokeTitle'),
      children: <Text size="sm">{t('tokens.revokeConfirm', { name })}</Text>,
      labels: { confirm: t('tokens.revoke'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        deleteToken.mutate(tokenId, {
          onError: (error) => notifications.show({ color: 'red', message: errorMessage(t, error) }),
        }),
    });

  return (
    <Stack gap="xl" py="xl">
      <Title order={1}>{t('profile.title')}</Title>

      <Card withBorder padding="lg">
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg">
          <Field label={t('users.username')} value={me.username} />
          <Field label={t('users.displayName')} value={me.display_name} />
          <Field label={t('users.email')} value={me.email} />
          <Field label={t('users.source')} value={<SourceBadge source={me.auth_source} />} />
          <Field label={t('users.roles')} value={<RoleBadges roles={me.roles} />} />
          <Field
            label={t('users.lastLogin')}
            value={formatDateTime(me.last_login_at, i18n.resolvedLanguage ?? 'ru')}
          />
        </SimpleGrid>
      </Card>

      {me.auth_source === 'local' && (
        <Stack>
          <Title order={3}>{t('profile.changePassword')}</Title>
          <ChangePasswordForm
            onSuccess={() =>
              notifications.show({ color: 'teal', message: t('profile.passwordChanged') })
            }
          />
        </Stack>
      )}

      <Stack>
        <Group justify="space-between">
          <Group gap="xs">
            <Title order={3}>{t('tokens.title')}</Title>
            {tokens.data && <Badge variant="light">{tokens.data.length}</Badge>}
          </Group>
          <Button leftSection={<IconPlus size={16} />} onClick={createModal.open}>
            {t('tokens.create')}
          </Button>
        </Group>
        <Text size="sm" c="dimmed">
          {t('tokens.description')}
        </Text>
        {tokens.data && (
          <TokensTable
            tokens={tokens.data}
            onRevoke={(token) => confirmRevoke(token.id, token.name)}
          />
        )}
      </Stack>

      <CreateTokenModal opened={createOpened} onClose={createModal.close} />
    </Stack>
  );
}
