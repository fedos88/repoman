import {
  ActionIcon,
  Button,
  Group,
  Loader,
  Menu,
  Pagination,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue, useDisclosure } from '@mantine/hooks';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconDots,
  IconEdit,
  IconKey,
  IconLock,
  IconLockOpen,
  IconPlus,
  IconSearch,
  IconShield,
  IconShieldOff,
  IconTicket,
  IconTrash,
} from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMe } from '../../api/auth';
import type { User } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { useBlockUser, useDeleteUser, useSetRoles, useUsers } from '../../api/users';
import { RoleBadges, SourceBadge, StatusBadge } from '../../components/UserBadges';
import { formatDateTime } from '../../utils/format';
import { ResetPasswordModal } from './ResetPasswordModal';
import { UserFormModal } from './UserFormModal';
import { UserTokensModal } from './UserTokensModal';

const PAGE_SIZE = 25;

export function UsersPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'ru';
  const { data: me } = useMe();

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [page, setPage] = useState(1);
  const users = useUsers({
    q: debouncedSearch.trim(),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  const [formOpened, formModal] = useDisclosure(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [tokensOf, setTokensOf] = useState<User | null>(null);

  const blockUser = useBlockUser();
  const deleteUser = useDeleteUser();
  const setRoles = useSetRoles();

  const onError = (error: unknown) =>
    notifications.show({ color: 'red', message: errorMessage(t, error) });

  const openForm = (user: User | null) => {
    setEditing(user);
    formModal.open();
  };

  const toggleAdmin = (user: User) => {
    const isAdmin = user.roles.includes('admin');
    const roles = isAdmin
      ? user.roles.filter((role) => role !== 'admin')
      : [...user.roles, 'admin'];
    setRoles.mutate({ id: user.id, roles }, { onError });
  };

  const confirmBlock = (user: User) =>
    modals.openConfirmModal({
      title: user.is_active ? t('users.blockTitle') : t('users.unblockTitle'),
      children: (
        <Text size="sm">
          {t(user.is_active ? 'users.blockConfirm' : 'users.unblockConfirm', {
            username: user.username,
          })}
        </Text>
      ),
      labels: {
        confirm: user.is_active ? t('users.block') : t('users.unblock'),
        cancel: t('common.cancel'),
      },
      confirmProps: { color: user.is_active ? 'red' : undefined },
      onConfirm: () => blockUser.mutate({ id: user.id, blocked: user.is_active }, { onError }),
    });

  const confirmDelete = (user: User) =>
    modals.openConfirmModal({
      title: t('users.deleteTitle'),
      children: <Text size="sm">{t('users.deleteConfirm', { username: user.username })}</Text>,
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteUser.mutate(user.id, { onError }),
    });

  const total = users.data?.total ?? 0;

  return (
    <Stack gap="lg" py="xl">
      <Group justify="space-between">
        <Title order={1}>{t('users.title')}</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => openForm(null)}>
          {t('users.create')}
        </Button>
      </Group>

      <TextInput
        leftSection={<IconSearch size={16} />}
        placeholder={t('users.searchPlaceholder')}
        value={search}
        onChange={(event) => {
          setSearch(event.currentTarget.value);
          setPage(1);
        }}
        maw={400}
      />

      {users.isPending ? (
        <Loader />
      ) : users.isError ? (
        <Text c="red">{errorMessage(t, users.error)}</Text>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table highlightOnHover withTableBorder verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('users.username')}</Table.Th>
                <Table.Th>{t('users.email')}</Table.Th>
                <Table.Th>{t('users.source')}</Table.Th>
                <Table.Th>{t('users.roles')}</Table.Th>
                <Table.Th>{t('users.statusTitle')}</Table.Th>
                <Table.Th>{t('users.lastLogin')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {users.data.items.map((user) => {
                const isSelf = user.id === me?.id;
                const isLocal = user.auth_source === 'local';
                const isAdmin = user.roles.includes('admin');
                return (
                  <Table.Tr key={user.id}>
                    <Table.Td>
                      <Text fw={500}>{user.username}</Text>
                      {user.display_name && (
                        <Text size="xs" c="dimmed">
                          {user.display_name}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>{user.email || '—'}</Table.Td>
                    <Table.Td>
                      <SourceBadge source={user.auth_source} />
                    </Table.Td>
                    <Table.Td>
                      <RoleBadges roles={user.roles} />
                    </Table.Td>
                    <Table.Td>
                      <StatusBadge user={user} />
                    </Table.Td>
                    <Table.Td>{formatDateTime(user.last_login_at, language)}</Table.Td>
                    <Table.Td>
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <ActionIcon variant="subtle" aria-label={t('common.actions')}>
                            <IconDots size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          {isLocal && (
                            <Menu.Item
                              leftSection={<IconEdit size={16} />}
                              onClick={() => openForm(user)}
                            >
                              {t('common.edit')}
                            </Menu.Item>
                          )}
                          {isLocal && (
                            <Menu.Item
                              leftSection={<IconKey size={16} />}
                              onClick={() => setResetting(user)}
                            >
                              {t('users.resetPassword')}
                            </Menu.Item>
                          )}
                          <Menu.Item
                            leftSection={<IconTicket size={16} />}
                            onClick={() => setTokensOf(user)}
                          >
                            {t('users.tokens')}
                          </Menu.Item>
                          <Menu.Item
                            leftSection={
                              isAdmin ? <IconShieldOff size={16} /> : <IconShield size={16} />
                            }
                            onClick={() => toggleAdmin(user)}
                          >
                            {isAdmin ? t('users.revokeAdmin') : t('users.grantAdmin')}
                          </Menu.Item>
                          {!isSelf && (
                            <Menu.Item
                              leftSection={
                                user.is_active ? <IconLock size={16} /> : <IconLockOpen size={16} />
                              }
                              onClick={() => confirmBlock(user)}
                            >
                              {user.is_active ? t('users.block') : t('users.unblock')}
                            </Menu.Item>
                          )}
                          {isLocal && !isSelf && (
                            <>
                              <Menu.Divider />
                              <Menu.Item
                                color="red"
                                leftSection={<IconTrash size={16} />}
                                onClick={() => confirmDelete(user)}
                              >
                                {t('common.delete')}
                              </Menu.Item>
                            </>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
          {users.data.items.length === 0 && (
            <Text c="dimmed" py="md">
              {t('users.empty')}
            </Text>
          )}
        </Table.ScrollContainer>
      )}

      {total > PAGE_SIZE && (
        <Pagination total={Math.ceil(total / PAGE_SIZE)} value={page} onChange={setPage} />
      )}

      <UserFormModal opened={formOpened} onClose={formModal.close} user={editing} />
      <ResetPasswordModal user={resetting} onClose={() => setResetting(null)} />
      <UserTokensModal user={tokensOf} onClose={() => setTokensOf(null)} />
    </Stack>
  );
}
