import {
  Alert,
  Button,
  Checkbox,
  Group,
  Modal,
  PasswordInput,
  SimpleGrid,
  Stack,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle } from '@tabler/icons-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import type { User } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { useCreateUser, useUpdateUser } from '../../api/users';
import { EMAIL_RE, LOCAL_USERNAME_RE, PASSWORD_MIN_LENGTH } from '../../utils/validation';

type Props = {
  opened: boolean;
  onClose: () => void;
  /** User to edit; null opens the form for a new user. */
  user: User | null;
};

const emptyToNull = (value: string) => (value.trim() ? value.trim() : null);

export function UserFormModal({ opened, onClose, user }: Props) {
  const { t } = useTranslation();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const mutation = user ? updateUser : createUser;
  const isNew = user === null;

  const form = useForm({
    initialValues: {
      username: '',
      password: '',
      first_name: '',
      last_name: '',
      display_name: '',
      email: '',
      admin: false,
      must_change_password: true,
    },
    validate: {
      username: (value) =>
        !isNew || LOCAL_USERNAME_RE.test(value.trim().toLowerCase())
          ? null
          : t('validation.username'),
      password: (value) =>
        !isNew || value.length >= PASSWORD_MIN_LENGTH
          ? null
          : t('validation.passwordMinLength', { count: PASSWORD_MIN_LENGTH }),
      email: (value) =>
        !value.trim() || EMAIL_RE.test(value.trim()) ? null : t('validation.email'),
    },
  });

  useEffect(() => {
    if (!opened) {
      return;
    }
    form.setValues({
      username: user?.username ?? '',
      password: '',
      first_name: user?.first_name ?? '',
      last_name: user?.last_name ?? '',
      display_name: user?.display_name ?? '',
      email: user?.email ?? '',
      admin: false,
      must_change_password: true,
    });
    form.resetDirty();
    mutation.reset();
    // The form is re-initialized only when the modal opens for a user.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, user]);

  const submit = form.onSubmit((values) => {
    const profile = {
      first_name: emptyToNull(values.first_name),
      last_name: emptyToNull(values.last_name),
      display_name: emptyToNull(values.display_name),
      email: emptyToNull(values.email),
    };
    if (user) {
      updateUser.mutate({ id: user.id, body: profile }, { onSuccess: onClose });
    } else {
      createUser.mutate(
        {
          ...profile,
          username: values.username.trim().toLowerCase(),
          password: values.password,
          roles: values.admin ? ['admin'] : [],
          must_change_password: values.must_change_password,
        },
        { onSuccess: onClose },
      );
    }
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={isNew ? t('users.createTitle') : t('users.editTitle', { username: user.username })}
      size="lg"
    >
      <form onSubmit={submit}>
        <Stack>
          {mutation.isError && (
            <Alert color="red" icon={<IconAlertCircle />}>
              {errorMessage(t, mutation.error)}
            </Alert>
          )}
          {isNew && (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput
                label={t('users.username')}
                description={t('users.usernameHint')}
                withAsterisk
                data-autofocus
                {...form.getInputProps('username')}
              />
              <PasswordInput
                label={t('auth.password')}
                description={t('validation.passwordMinLength', { count: PASSWORD_MIN_LENGTH })}
                withAsterisk
                autoComplete="new-password"
                {...form.getInputProps('password')}
              />
            </SimpleGrid>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label={t('users.firstName')} {...form.getInputProps('first_name')} />
            <TextInput label={t('users.lastName')} {...form.getInputProps('last_name')} />
            <TextInput label={t('users.displayName')} {...form.getInputProps('display_name')} />
            <TextInput label={t('users.email')} {...form.getInputProps('email')} />
          </SimpleGrid>
          {isNew && (
            <Stack gap="xs">
              <Checkbox
                label={t('users.grantAdmin')}
                {...form.getInputProps('admin', { type: 'checkbox' })}
              />
              <Checkbox
                label={t('users.mustChangePassword')}
                {...form.getInputProps('must_change_password', { type: 'checkbox' })}
              />
            </Stack>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {isNew ? t('common.create') : t('common.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
