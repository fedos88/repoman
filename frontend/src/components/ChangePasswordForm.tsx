import { Alert, Button, PasswordInput, Stack } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { useChangeOwnPassword } from '../api/auth';
import { errorMessage } from '../api/errors';
import { PASSWORD_MIN_LENGTH } from '../utils/validation';

export function ChangePasswordForm({ onSuccess }: { onSuccess?: () => void }) {
  const { t } = useTranslation();
  const changePassword = useChangeOwnPassword();

  const form = useForm({
    initialValues: { current: '', password: '', confirm: '' },
    validate: {
      current: (value) => (value ? null : t('validation.required')),
      password: (value) =>
        value.length >= PASSWORD_MIN_LENGTH
          ? null
          : t('validation.passwordMinLength', { count: PASSWORD_MIN_LENGTH }),
      confirm: (value, values) =>
        value === values.password ? null : t('validation.passwordsDoNotMatch'),
    },
  });

  return (
    <form
      onSubmit={form.onSubmit((values) =>
        changePassword.mutate(
          { current_password: values.current, new_password: values.password },
          {
            onSuccess: () => {
              form.reset();
              onSuccess?.();
            },
          },
        ),
      )}
    >
      <Stack maw={400}>
        {changePassword.isError && (
          <Alert color="red" icon={<IconAlertCircle />}>
            {errorMessage(t, changePassword.error)}
          </Alert>
        )}
        <PasswordInput
          label={t('profile.currentPassword')}
          autoComplete="current-password"
          {...form.getInputProps('current')}
        />
        <PasswordInput
          label={t('profile.newPassword')}
          autoComplete="new-password"
          {...form.getInputProps('password')}
        />
        <PasswordInput
          label={t('profile.confirmPassword')}
          autoComplete="new-password"
          {...form.getInputProps('confirm')}
        />
        <Button type="submit" loading={changePassword.isPending} w="fit-content">
          {t('profile.changePassword')}
        </Button>
      </Stack>
    </form>
  );
}
