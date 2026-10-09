import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import { unwrap } from './errors';

const OWN_TOKENS_KEY = ['me', 'tokens'] as const;
const userTokensKey = (userId: number) => ['users', userId, 'tokens'] as const;

export function useOwnTokens() {
  return useQuery({
    queryKey: OWN_TOKENS_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/me/tokens')),
  });
}

export function useCreateOwnToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; expires_in_days: number | null }) =>
      unwrap(await api.POST('/api/v1/me/tokens', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: OWN_TOKENS_KEY }),
  });
}

export function useDeleteOwnToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (tokenId: number) =>
      unwrap(
        await api.DELETE('/api/v1/me/tokens/{token_id}', {
          params: { path: { token_id: tokenId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: OWN_TOKENS_KEY }),
  });
}

export function useUserTokens(userId: number | null) {
  return useQuery({
    queryKey: userTokensKey(userId ?? 0),
    enabled: userId !== null,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/users/{user_id}/tokens', {
          params: { path: { user_id: userId! } },
        }),
      ),
  });
}

export function useDeleteUserToken(userId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (tokenId: number) =>
      unwrap(
        await api.DELETE('/api/v1/users/{user_id}/tokens/{token_id}', {
          params: { path: { user_id: userId, token_id: tokenId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userTokensKey(userId) }),
  });
}
