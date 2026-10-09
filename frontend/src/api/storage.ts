import { useQuery } from '@tanstack/react-query';

import { api, type Schemas } from './client';
import { unwrap } from './errors';

export type BlobStoreInfo = Schemas['BlobStoreOut'];

export function useBlobStores() {
  return useQuery({
    queryKey: ['blob-stores'],
    queryFn: async () => unwrap(await api.GET('/api/v1/blob-stores')),
    refetchInterval: 30_000,
  });
}
