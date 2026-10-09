import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Me } from './client';
import { unwrap } from './errors';

export const ME_QUERY_KEY = ['me'] as const;

/** Current user, or null for anonymous visitors. */
export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async (): Promise<Me | null> => {
      const result = await api.GET('/api/v1/me');
      if (result.response.status === 401) {
        return null;
      }
      return unwrap(result);
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { username: string; password: string }) =>
      unwrap(await api.POST('/api/v1/auth/login', { body })),
    onSuccess: (me) => {
      queryClient.clear();
      queryClient.setQueryData(ME_QUERY_KEY, me);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST('/api/v1/auth/logout');
    },
    onSettled: () => {
      queryClient.clear();
      queryClient.setQueryData(ME_QUERY_KEY, null);
    },
  });
}

export function useChangeOwnPassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) =>
      unwrap(await api.PUT('/api/v1/me/password', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}
