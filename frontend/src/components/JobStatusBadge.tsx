import { Badge } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import type { JobStatus } from '../api/jobs';

const COLORS: Record<JobStatus, string> = {
  queued: 'gray',
  running: 'blue',
  succeeded: 'teal',
  failed: 'red',
  cancelled: 'yellow',
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { t } = useTranslation();
  return (
    <Badge variant="light" color={COLORS[status]}>
      {t(`jobs.statuses.${status}`)}
    </Badge>
  );
}
