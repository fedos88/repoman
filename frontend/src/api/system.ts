import { useQuery } from '@tanstack/react-query';

import { api } from './client';

export function useSystemInfo() {
  return useQuery({
    queryKey: ['system', 'info'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/system/info');
      if (error) {
        throw error;
      }
      return data;
    },
    staleTime: Infinity,
    retry: false,
  });
}
