import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from './client';
import { unwrap } from './errors';

export type BlobStoreInfo = Schemas['BlobStoreOut'];

const STORES_KEY = ['blob-stores'] as const;

export function useBlobStores() {
  return useQuery({
    queryKey: STORES_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/blob-stores')),
    // Faster while a migration is running.
    refetchInterval: (query) =>
      query.state.data?.some((store) => store.migration_job_id !== null) ? 3000 : 30_000,
  });
}

function useStoresMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: STORES_KEY });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

const path = (storeId: number) => ({ params: { path: { store_id: storeId } } });

export function useCreateBlobStore() {
  return useStoresMutation(async (body: Schemas['BlobStoreCreateIn']) =>
    unwrap(await api.POST('/api/v1/blob-stores', { body })),
  );
}

export function useUpdateBlobStore() {
  return useStoresMutation(
    async ({ id, body }: { id: number; body: Schemas['BlobStoreUpdateIn'] }) =>
      unwrap(await api.PATCH('/api/v1/blob-stores/{store_id}', { ...path(id), body })),
  );
}

export function useDeleteBlobStore() {
  return useStoresMutation(async (id: number) =>
    unwrap(await api.DELETE('/api/v1/blob-stores/{store_id}', path(id))),
  );
}

export function useCheckBlobStore() {
  return useStoresMutation(async (id: number) =>
    unwrap(await api.POST('/api/v1/blob-stores/{store_id}/check', path(id))),
  );
}

export function useMigrateBlobStore() {
  return useStoresMutation(async ({ id, targetId }: { id: number; targetId: number }) =>
    unwrap(
      await api.POST('/api/v1/blob-stores/{store_id}/migrate', {
        ...path(id),
        body: { target_store_id: targetId },
      }),
    ),
  );
}
