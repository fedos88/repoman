import { Alert, Button, Paper, PasswordInput, Stack, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Navigate, useNavigate, useSearchParams } from 'react-router';

import { useLogin, useMe } from '../api/auth';
import { errorMessage } from '../api/errors';
import { CHANGE_PASSWORD_PATH } from '../auth/guards';

/** Only same-site relative paths are accepted as a redirect target. */
function safeNext(value: string | null): string {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/';
}

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get('next'));
  const { data: me } = useMe();
  const login = useLogin();

  const form = useForm({
    initialValues: { username: '', password: '' },
    validate: {
      username: (value) => (value.trim() ? null : t('validation.required')),
      password: (value) => (value ? null : t('validation.required')),
    },
  });

  if (me && !login.isPending) {
    return <Navigate to={me.must_change_password ? CHANGE_PASSWORD_PATH : next} replace />;
  }

  return (
    <Stack align="center" py={60}>
      <Paper withBorder shadow="sm" p="xl" w="100%" maw={400}>
        <form
          onSubmit={form.onSubmit((values) =>
            login.mutate(values, {
              onSuccess: (result) =>
                navigate(result.must_change_password ? CHANGE_PASSWORD_PATH : next, {
                  replace: true,
                }),
            }),
          )}
        >
          <Stack>
            <Title order={2}>{t('auth.signInTitle')}</Title>
            {login.isError && (
              <Alert color="red" icon={<IconAlertCircle />}>
                {errorMessage(t, login.error)}
              </Alert>
            )}
            <TextInput
              label={t('auth.username')}
              autoComplete="username"
              autoFocus
              {...form.getInputProps('username')}
            />
            <PasswordInput
              label={t('auth.password')}
              autoComplete="current-password"
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={login.isPending} fullWidth>
              {t('auth.signIn')}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Stack>
  );
}
