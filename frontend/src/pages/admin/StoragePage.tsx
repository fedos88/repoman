import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  Menu,
  Modal,
  NumberInput,
  Progress,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconAlertTriangle,
  IconDots,
  IconEdit,
  IconPlugConnected,
  IconPlus,
  IconTransfer,
  IconTrash,
  IconX,
} from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { errorMessage } from '../../api/errors';
import {
  type BlobStoreInfo,
  useBlobStores,
  useCheckBlobStore,
  useCreateBlobStore,
  useDeleteBlobStore,
  useMigrateBlobStore,
  useUpdateBlobStore,
} from '../../api/storage';
import { formatBytes } from '../../utils/format';

const GiB = 1024 ** 3;
const STORE_NAME_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={500}>{value}</Text>
    </Stack>
  );
}

function StoreFormModal({
  opened,
  store,
  onClose,
}: {
  opened: boolean;
  store: BlobStoreInfo | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const create = useCreateBlobStore();
  const update = useUpdateBlobStore();
  const mutation = store ? update : create;
  const pathLocked =
    store !== null && (store.is_default || store.blob_count + store.pending_delete_count > 0);

  const form = useForm({
    initialValues: { name: '', path: '', quota_gb: '' as number | string },
    validate: {
      name: (value) =>
        STORE_NAME_RE.test(value.trim().toLowerCase()) ? null : t('storage.validation.name'),
      path: (value) => (value.trim().startsWith('/') ? null : t('storage.validation.path')),
      quota_gb: (value) =>
        value === '' || Number(value) > 0 ? null : t('storage.validation.quota'),
    },
  });

  useEffect(() => {
    if (!opened) {
      return;
    }
    form.setValues({
      name: store?.name ?? '',
      path: store?.path ?? '',
      quota_gb: store?.quota_bytes ? Number((store.quota_bytes / GiB).toFixed(2)) : '',
    });
    mutation.reset();
    // Re-initialize only when the modal opens for a store.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, store]);

  const submit = form.onSubmit((values) => {
    const quota_bytes = values.quota_gb === '' ? null : Math.round(Number(values.quota_gb) * GiB);
    if (store) {
      const body: Record<string, unknown> = { quota_bytes };
      if (!store.is_default) {
        body.name = values.name.trim().toLowerCase();
      }
      if (!pathLocked) {
        body.path = values.path.trim();
      }
      update.mutate({ id: store.id, body }, { onSuccess: onClose });
    } else {
      create.mutate(
        {
          name: values.name.trim().toLowerCase(),
          type: 'filesystem',
          path: values.path.trim(),
          quota_bytes,
        },
        { onSuccess: onClose },
      );
    }
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={store ? t('storage.editTitle', { name: store.name }) : t('storage.createTitle')}
      size="lg"
    >
      <form onSubmit={submit}>
        <Stack>
          {mutation.isError && (
            <Alert color="red" icon={<IconX />}>
              {errorMessage(t, mutation.error)}
            </Alert>
          )}
          <TextInput
            label={t('storage.name')}
            description={t('storage.nameHint')}
            withAsterisk
            disabled={store?.is_default}
            data-autofocus
            {...form.getInputProps('name')}
          />
          <TextInput
            label={t('storage.path')}
            description={
              pathLocked
                ? store?.is_default
                  ? t('storage.pathDefaultHint')
                  : t('storage.pathLockedHint')
                : t('storage.pathHint')
            }
            placeholder="/mnt/disk2/repoman"
            withAsterisk
            disabled={pathLocked}
            styles={{ input: { fontFamily: 'monospace' } }}
            {...form.getInputProps('path')}
          />
          <NumberInput
            label={t('storage.quota')}
            description={t('storage.quotaHint')}
            suffix=" GB"
            min={0}
            decimalScale={2}
            {...form.getInputProps('quota_gb')}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {store ? t('common.save') : t('common.create')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function MigrateModal({
  source,
  stores,
  onClose,
}: {
  source: BlobStoreInfo | null;
  stores: BlobStoreInfo[];
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const migrate = useMigrateBlobStore();
  const [targetId, setTargetId] = useState<string | null>(null);
  const targets = stores.filter((store) => store.id !== source?.id);
  const target = targets.find((store) => String(store.id) === targetId);

  const close = () => {
    setTargetId(null);
    migrate.reset();
    onClose();
  };

  return (
    <Modal
      opened={source !== null}
      onClose={close}
      title={t('storage.migrateTitle', { name: source?.name })}
      size="lg"
    >
      <Stack>
        {migrate.isError && (
          <Alert color="red" icon={<IconX />}>
            {errorMessage(t, migrate.error)}
          </Alert>
        )}
        <Text size="sm">
          {t('storage.migrateDescription', {
            count: source?.blob_count ?? 0,
            size: formatBytes(source?.used_bytes, i18n.resolvedLanguage ?? 'ru'),
          })}
        </Text>
        <Select
          label={t('storage.migrateTarget')}
          placeholder={t('storage.migrateTargetPlaceholder')}
          data={targets.map((store) => ({ value: String(store.id), label: store.name }))}
          value={targetId}
          onChange={setTargetId}
        />
        {target && (
          <Alert color="yellow" icon={<IconAlertTriangle />} title={t('storage.migrateConfirm')}>
            {t('storage.migrateWarning', { source: source?.name, target: target.name })}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>
            {t('common.cancel')}
          </Button>
          <Button
            color="yellow"
            disabled={!target}
            loading={migrate.isPending}
            onClick={() =>
              source &&
              target &&
              migrate.mutate(
                { id: source.id, targetId: target.id },
                {
                  onSuccess: () => {
                    notifications.show({ color: 'teal', message: t('storage.migrateStarted') });
                    close();
                  },
                },
              )
            }
          >
            {t('storage.migrate')}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function StoreCard({
  store,
  onEdit,
  onMigrate,
}: {
  store: BlobStoreInfo;
  onEdit: () => void;
  onMigrate: () => void;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'ru';
  const bytes = (value: number | null | undefined) => formatBytes(value, language);
  const check = useCheckBlobStore();
  const remove = useDeleteBlobStore();
  const total = store.total_bytes ?? 0;
  const usedOnDisk = total - (store.free_bytes ?? 0);
  const percent = total ? Math.round((100 * usedOnDisk) / total) : 0;
  const stored = store.used_bytes + store.pending_delete_bytes;
  const quotaPercent = store.quota_bytes
    ? Math.min(100, Math.round((100 * stored) / store.quota_bytes))
    : 0;
  const onError = (error: unknown) =>
    notifications.show({ color: 'red', message: errorMessage(t, error) });

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs">
            <Title order={3}>{store.name}</Title>
            <Badge variant="light">{t(`storage.types.${store.type}`, store.type)}</Badge>
            {store.is_default && <Badge variant="outline">{t('storage.default')}</Badge>}
            {!store.available && (
              <Badge color="red" variant="filled">
                {t('storage.unavailable')}
              </Badge>
            )}
            {store.migration_job_id !== null && (
              <Badge
                color="yellow"
                variant="light"
                component={Link}
                to="/admin/jobs"
                style={{ cursor: 'pointer' }}
              >
                {t('storage.migrating')}
              </Badge>
            )}
          </Group>
          <Group gap="xs" wrap="nowrap">
            {store.path && <Code>{store.path}</Code>}
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <ActionIcon variant="subtle" aria-label={t('common.actions')}>
                  <IconDots size={16} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconEdit size={16} />} onClick={onEdit}>
                  {t('common.edit')}
                </Menu.Item>
                <Menu.Item
                  leftSection={<IconPlugConnected size={16} />}
                  onClick={() =>
                    check.mutate(store.id, {
                      onSuccess: (result) =>
                        notifications.show(
                          result.ok
                            ? { color: 'teal', message: t('storage.checkOk') }
                            : {
                                color: 'red',
                                title: t(`errors.${result.error_code}`, {
                                  defaultValue: result.error_code ?? '',
                                }),
                                message: result.message,
                              },
                        ),
                      onError,
                    })
                  }
                >
                  {t('storage.check')}
                </Menu.Item>
                <Menu.Item
                  leftSection={<IconTransfer size={16} />}
                  disabled={store.blob_count === 0 || store.migration_job_id !== null}
                  onClick={onMigrate}
                >
                  {t('storage.migrate')}
                </Menu.Item>
                {!store.is_default && (
                  <>
                    <Menu.Divider />
                    <Menu.Item
                      color="red"
                      leftSection={<IconTrash size={16} />}
                      onClick={() =>
                        modals.openConfirmModal({
                          title: t('storage.deleteTitle'),
                          children: (
                            <Text size="sm">
                              {t('storage.deleteConfirm', { name: store.name })}
                            </Text>
                          ),
                          labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
                          confirmProps: { color: 'red' },
                          onConfirm: () => remove.mutate(store.id, { onError }),
                        })
                      }
                    >
                      {t('common.delete')}
                    </Menu.Item>
                  </>
                )}
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>

        {store.low_space && (
          <Alert color="red" icon={<IconAlertTriangle />} title={t('storage.lowSpaceTitle')}>
            {t('storage.lowSpace', { threshold: bytes(store.low_space_threshold_bytes) })}
          </Alert>
        )}
        {store.quota_exceeded && (
          <Alert color="red" icon={<IconAlertTriangle />} title={t('storage.quotaExceededTitle')}>
            {t('storage.quotaExceeded')}
          </Alert>
        )}

        {store.total_bytes !== null && (
          <Stack gap={4}>
            <Group justify="space-between">
              <Text size="sm">{t('storage.disk')}</Text>
              <Text size="sm" c="dimmed">
                {t('storage.diskUsage', {
                  used: bytes(usedOnDisk),
                  total: bytes(store.total_bytes),
                  free: bytes(store.free_bytes),
                })}
              </Text>
            </Group>
            <Progress
              value={percent}
              size="lg"
              color={store.low_space ? 'red' : percent > 85 ? 'yellow' : 'blue'}
            />
          </Stack>
        )}
        {store.quota_bytes !== null && (
          <Stack gap={4}>
            <Group justify="space-between">
              <Text size="sm">{t('storage.quota')}</Text>
              <Text size="sm" c="dimmed">
                {t('storage.quotaUsage', { used: bytes(stored), quota: bytes(store.quota_bytes) })}
              </Text>
            </Group>
            <Progress
              value={quotaPercent}
              size="lg"
              color={store.quota_exceeded ? 'red' : quotaPercent > 85 ? 'yellow' : 'teal'}
            />
          </Stack>
        )}

        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Stat label={t('storage.blobCount')} value={store.blob_count.toLocaleString(language)} />
          <Stat label={t('storage.usedBytes')} value={bytes(store.used_bytes)} />
          <Stat
            label={t('storage.pendingDelete')}
            value={`${store.pending_delete_count.toLocaleString(language)} / ${bytes(store.pending_delete_bytes)}`}
          />
          <Stat
            label={t('storage.lowSpaceThreshold')}
            value={bytes(store.low_space_threshold_bytes)}
          />
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          {t('storage.pendingDeleteHint')}
        </Text>
      </Stack>
    </Card>
  );
}

export function StoragePage() {
  const { t } = useTranslation();
  const stores = useBlobStores();
  const [formOpened, setFormOpened] = useState(false);
  const [editing, setEditing] = useState<BlobStoreInfo | null>(null);
  const [migrating, setMigrating] = useState<BlobStoreInfo | null>(null);

  const openForm = (store: BlobStoreInfo | null) => {
    setEditing(store);
    setFormOpened(true);
  };

  return (
    <Stack gap="lg" py="xl">
      <Group justify="space-between">
        <Title order={1}>{t('storage.title')}</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => openForm(null)}>
          {t('storage.create')}
        </Button>
      </Group>
      {stores.isPending ? (
        <Loader />
      ) : stores.isError ? (
        <Text c="red">{errorMessage(t, stores.error)}</Text>
      ) : (
        stores.data.map((store) => (
          <StoreCard
            key={store.id}
            store={store}
            onEdit={() => openForm(store)}
            onMigrate={() => setMigrating(store)}
          />
        ))
      )}
      <StoreFormModal opened={formOpened} store={editing} onClose={() => setFormOpened(false)} />
      <MigrateModal
        source={migrating}
        stores={stores.data ?? []}
        onClose={() => setMigrating(null)}
      />
    </Stack>
  );
}
