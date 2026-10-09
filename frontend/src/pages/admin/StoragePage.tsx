import {
  Alert,
  Badge,
  Card,
  Code,
  Group,
  Loader,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../../api/errors';
import { type BlobStoreInfo, useBlobStores } from '../../api/storage';
import { formatBytes } from '../../utils/format';

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

function StoreCard({ store }: { store: BlobStoreInfo }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'ru';
  const bytes = (value: number | null | undefined) => formatBytes(value, language);
  const total = store.total_bytes ?? 0;
  const usedOnDisk = total - (store.free_bytes ?? 0);
  const percent = total ? Math.round((100 * usedOnDisk) / total) : 0;

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Group justify="space-between">
          <Group gap="xs">
            <Title order={3}>{store.name}</Title>
            <Badge variant="light">{t(`storage.types.${store.type}`, store.type)}</Badge>
          </Group>
          {store.path && <Code>{store.path}</Code>}
        </Group>

        {store.low_space && (
          <Alert color="red" icon={<IconAlertTriangle />} title={t('storage.lowSpaceTitle')}>
            {t('storage.lowSpace', { threshold: bytes(store.low_space_threshold_bytes) })}
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

  return (
    <Stack gap="lg" py="xl">
      <Title order={1}>{t('storage.title')}</Title>
      {stores.isPending ? (
        <Loader />
      ) : stores.isError ? (
        <Text c="red">{errorMessage(t, stores.error)}</Text>
      ) : (
        stores.data.map((store) => <StoreCard key={store.id} store={store} />)
      )}
    </Stack>
  );
}
