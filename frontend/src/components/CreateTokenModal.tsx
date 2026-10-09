import {
  ActionIcon,
  Alert,
  Button,
  Code,
  CopyButton,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle, IconCheck, IconCopy } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CreatedToken } from '../api/client';
import { errorMessage } from '../api/errors';
import { useCreateOwnToken } from '../api/tokens';

const NEVER = 'never';
const LIFETIME_OPTIONS = ['30', '90', '180', '365', NEVER];
const DEFAULT_LIFETIME = '90';

export function CreateTokenModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const createToken = useCreateOwnToken();
  const [created, setCreated] = useState<CreatedToken | null>(null);

  const form = useForm({
    initialValues: { name: '', lifetime: DEFAULT_LIFETIME },
    validate: { name: (value) => (value.trim() ? null : t('validation.required')) },
  });

  const close = () => {
    form.reset();
    createToken.reset();
    setCreated(null);
    onClose();
  };

  return (
    <Modal opened={opened} onClose={close} title={t('tokens.createTitle')} size="lg">
      {created ? (
        <Stack>
          <Alert color="yellow" icon={<IconAlertCircle />}>
            {t('tokens.shownOnce')}
          </Alert>
          <Group wrap="nowrap" gap="xs">
            <Code block style={{ flex: 1, wordBreak: 'break-all' }}>
              {created.token}
            </Code>
            <CopyButton value={created.token}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? t('common.copied') : t('common.copy')}>
                  <ActionIcon variant="light" onClick={copy} aria-label={t('common.copy')}>
                    {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                  </ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
          <Text size="sm" c="dimmed">
            {t('tokens.usageHint')}
          </Text>
          <Group justify="flex-end">
            <Button onClick={close}>{t('common.done')}</Button>
          </Group>
        </Stack>
      ) : (
        <form
          onSubmit={form.onSubmit((values) =>
            createToken.mutate(
              {
                name: values.name.trim(),
                expires_in_days: values.lifetime === NEVER ? null : Number(values.lifetime),
              },
              { onSuccess: setCreated },
            ),
          )}
        >
          <Stack>
            {createToken.isError && (
              <Alert color="red" icon={<IconAlertCircle />}>
                {errorMessage(t, createToken.error)}
              </Alert>
            )}
            <TextInput
              label={t('tokens.name')}
              placeholder={t('tokens.namePlaceholder')}
              data-autofocus
              {...form.getInputProps('name')}
            />
            <Select
              label={t('tokens.lifetime')}
              allowDeselect={false}
              data={LIFETIME_OPTIONS.map((value) => ({
                value,
                label:
                  value === NEVER ? t('tokens.never') : t('tokens.days', { count: Number(value) }),
              }))}
              {...form.getInputProps('lifetime')}
            />
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" loading={createToken.isPending}>
                {t('tokens.create')}
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}
