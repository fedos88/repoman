import { Alert, Button, Checkbox, Group, Modal, PasswordInput, Stack } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import type { User } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { useResetPassword } from '../../api/users';
import { PASSWORD_MIN_LENGTH } from '../../utils/validation';

export function ResetPasswordModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const { t } = useTranslation();
  const resetPassword = useResetPassword();

  const form = useForm({
    initialValues: { password: '', must_change_password: true },
    validate: {
      password: (value) =>
        value.length >= PASSWORD_MIN_LENGTH
          ? null
          : t('validation.passwordMinLength', { count: PASSWORD_MIN_LENGTH }),
    },
  });

  const close = () => {
    form.reset();
    resetPassword.reset();
    onClose();
  };

  return (
    <Modal
      opened={user !== null}
      onClose={close}
      title={t('users.resetPasswordTitle', { username: user?.username })}
    >
      <form
        onSubmit={form.onSubmit((values) =>
          resetPassword.mutate(
            { id: user!.id, body: values },
            {
              onSuccess: () => {
                notifications.show({ color: 'teal', message: t('users.passwordReset') });
                close();
              },
            },
          ),
        )}
      >
        <Stack>
          {resetPassword.isError && (
            <Alert color="red" icon={<IconAlertCircle />}>
              {errorMessage(t, resetPassword.error)}
            </Alert>
          )}
          <PasswordInput
            label={t('profile.newPassword')}
            autoComplete="new-password"
            data-autofocus
            {...form.getInputProps('password')}
          />
          <Checkbox
            label={t('users.mustChangePassword')}
            {...form.getInputProps('must_change_password', { type: 'checkbox' })}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={resetPassword.isPending}>
              {t('users.resetPassword')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
