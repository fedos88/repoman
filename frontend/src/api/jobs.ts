import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from './client';
import { unwrap } from './errors';

export type Job = Schemas['JobOut'];
export type JobStatus = Job['status'];

const JOBS_KEY = ['jobs'] as const;

export const isJobActive = (job: Pick<Job, 'status'>) =>
  job.status === 'queued' || job.status === 'running';

export function useJobs(params: { status?: JobStatus; limit: number; offset: number }) {
  return useQuery({
    queryKey: [...JOBS_KEY, 'list', params],
    queryFn: async () => unwrap(await api.GET('/api/v1/jobs', { params: { query: params } })),
    placeholderData: keepPreviousData,
    // Poll while jobs are in progress.
    refetchInterval: (query) => (query.state.data?.items.some(isJobActive) ? 3000 : false),
  });
}

export function useJobLogs(jobId: number | null, active: boolean) {
  return useQuery({
    queryKey: [...JOBS_KEY, jobId, 'logs'],
    enabled: jobId !== null,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/jobs/{job_id}/logs', { params: { path: { job_id: jobId! } } })),
    refetchInterval: active ? 2000 : false,
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: number) =>
      unwrap(
        await api.POST('/api/v1/jobs/{job_id}/cancel', { params: { path: { job_id: jobId } } }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: JOBS_KEY }),
  });
}
