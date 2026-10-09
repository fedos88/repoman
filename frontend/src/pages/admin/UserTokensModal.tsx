import { Loader, Modal, Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { useTranslation } from 'react-i18next';

import type { User } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { useDeleteUserToken, useUserTokens } from '../../api/tokens';
import { TokensTable } from '../../components/TokensTable';

export function UserTokensModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const { t } = useTranslation();
  const tokens = useUserTokens(user?.id ?? null);
  const deleteToken = useDeleteUserToken(user?.id ?? 0);

  return (
    <Modal
      opened={user !== null}
      onClose={onClose}
      title={t('users.tokensTitle', { username: user?.username })}
      size="xl"
    >
      {tokens.isPending ? (
        <Loader />
      ) : (
        <TokensTable
          tokens={tokens.data ?? []}
          onRevoke={(token) =>
            modals.openConfirmModal({
              title: t('tokens.revokeTitle'),
              children: <Text size="sm">{t('tokens.revokeConfirm', { name: token.name })}</Text>,
              labels: { confirm: t('tokens.revoke'), cancel: t('common.cancel') },
              confirmProps: { color: 'red' },
              onConfirm: () =>
                deleteToken.mutate(token.id, {
                  onError: (error) =>
                    notifications.show({ color: 'red', message: errorMessage(t, error) }),
                }),
            })
          }
        />
      )}
    </Modal>
  );
}
