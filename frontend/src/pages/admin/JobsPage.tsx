import {
  ActionIcon,
  Code,
  Group,
  Loader,
  Modal,
  Pagination,
  Progress,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconFileText, IconPlayerStop } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../../api/errors';
import {
  isJobActive,
  type Job,
  type JobStatus,
  useCancelJob,
  useJobLogs,
  useJobs,
} from '../../api/jobs';
import { JobStatusBadge } from '../../components/JobStatusBadge';
import { formatDateTime } from '../../utils/format';

const PAGE_SIZE = 25;
const STATUSES: JobStatus[] = ['queued', 'running', 'succeeded', 'failed', 'cancelled'];

function JobLogsModal({ job, onClose }: { job: Job | null; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const logs = useJobLogs(job?.id ?? null, job !== null && isJobActive(job));

  return (
    <Modal
      opened={job !== null}
      onClose={onClose}
      title={t('jobs.logsTitle', {
        id: job?.id,
        type: job ? t(`jobs.types.${job.type}`, job.type) : '',
      })}
      size="xl"
    >
      {logs.isPending ? (
        <Loader />
      ) : (
        <ScrollArea.Autosize mah={480}>
          <Stack gap={4}>
            {(logs.data ?? []).map((entry, index) => (
              <Group key={index} gap="sm" wrap="nowrap" align="flex-start">
                <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                  {formatDateTime(entry.ts, i18n.resolvedLanguage ?? 'ru')}
                </Text>
                <Code
                  color={
                    entry.level === 'error'
                      ? 'red'
                      : entry.level === 'warning'
                        ? 'yellow'
                        : undefined
                  }
                  style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                >
                  {entry.message}
                </Code>
              </Group>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      )}
    </Modal>
  );
}

export function JobsPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'ru';
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [page, setPage] = useState(1);
  const [logsOf, setLogsOf] = useState<Job | null>(null);
  const jobs = useJobs({
    status: status ?? undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const cancelJob = useCancelJob();
  const total = jobs.data?.total ?? 0;

  return (
    <Stack gap="lg" py="xl">
      <Title order={1}>{t('jobs.title')}</Title>

      <Select
        placeholder={t('jobs.allStatuses')}
        clearable
        maw={240}
        value={status}
        onChange={(value) => {
          setStatus(value as JobStatus | null);
          setPage(1);
        }}
        data={STATUSES.map((value) => ({ value, label: t(`jobs.statuses.${value}`) }))}
      />

      {jobs.isPending ? (
        <Loader />
      ) : jobs.isError ? (
        <Text c="red">{errorMessage(t, jobs.error)}</Text>
      ) : jobs.data.items.length === 0 ? (
        <Text c="dimmed">{t('jobs.empty')}</Text>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table highlightOnHover withTableBorder verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>{t('jobs.type')}</Table.Th>
                <Table.Th>{t('jobs.status')}</Table.Th>
                <Table.Th>{t('jobs.progress')}</Table.Th>
                <Table.Th>{t('jobs.created')}</Table.Th>
                <Table.Th>{t('jobs.finished')}</Table.Th>
                <Table.Th>{t('jobs.error')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {jobs.data.items.map((job) => {
                const percent = job.progress_total
                  ? Math.round((100 * job.progress_done) / job.progress_total)
                  : null;
                return (
                  <Table.Tr key={job.id}>
                    <Table.Td>{job.id}</Table.Td>
                    <Table.Td>{t(`jobs.types.${job.type}`, job.type)}</Table.Td>
                    <Table.Td>
                      <JobStatusBadge status={job.status} />
                    </Table.Td>
                    <Table.Td miw={140}>
                      {percent === null ? (
                        '—'
                      ) : (
                        <Tooltip label={`${job.progress_done} / ${job.progress_total}`}>
                          <Progress value={percent} size="lg" />
                        </Tooltip>
                      )}
                    </Table.Td>
                    <Table.Td>{formatDateTime(job.created_at, language)}</Table.Td>
                    <Table.Td>{formatDateTime(job.finished_at, language)}</Table.Td>
                    <Table.Td maw={320}>
                      <Text size="sm" c="red" lineClamp={2}>
                        {job.error}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <Tooltip label={t('jobs.logs')}>
                          <ActionIcon
                            variant="subtle"
                            aria-label={t('jobs.logs')}
                            onClick={() => setLogsOf(job)}
                          >
                            <IconFileText size={16} />
                          </ActionIcon>
                        </Tooltip>
                        {isJobActive(job) && (
                          <Tooltip label={t('jobs.cancel')}>
                            <ActionIcon
                              variant="subtle"
                              color="red"
                              aria-label={t('jobs.cancel')}
                              disabled={job.cancel_requested}
                              onClick={() =>
                                cancelJob.mutate(job.id, {
                                  onError: (error) =>
                                    notifications.show({
                                      color: 'red',
                                      message: errorMessage(t, error),
                                    }),
                                })
                              }
                            >
                              <IconPlayerStop size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {total > PAGE_SIZE && (
        <Pagination total={Math.ceil(total / PAGE_SIZE)} value={page} onChange={setPage} />
      )}
      <JobLogsModal job={logsOf} onClose={() => setLogsOf(null)} />
    </Stack>
  );
}
