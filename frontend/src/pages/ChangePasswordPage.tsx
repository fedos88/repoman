import { Alert, Paper, Stack, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { ChangePasswordForm } from '../components/ChangePasswordForm';

/** Shown when the password must be changed before using RepoMan. */
export function ChangePasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Stack align="center" py={60}>
      <Paper withBorder shadow="sm" p="xl" w="100%" maw={460}>
        <Stack>
          <Title order={2}>{t('profile.changePasswordTitle')}</Title>
          <Alert variant="light" icon={<IconInfoCircle />}>
            {t('profile.changePasswordRequired')}
          </Alert>
          <ChangePasswordForm onSuccess={() => navigate('/', { replace: true })} />
        </Stack>
      </Paper>
    </Stack>
  );
}
