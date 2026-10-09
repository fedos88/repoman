import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from './client';
import { unwrap } from './errors';

const USERS_KEY = ['users'] as const;

export function useUsers(params: { q: string; limit: number; offset: number }) {
  return useQuery({
    queryKey: [...USERS_KEY, 'list', params],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/users', {
          params: {
            query: { q: params.q || undefined, limit: params.limit, offset: params.offset },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

function useUsersMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

const path = (userId: number) => ({ params: { path: { user_id: userId } } });

export function useCreateUser() {
  return useUsersMutation(async (body: Schemas['UserCreateIn']) =>
    unwrap(await api.POST('/api/v1/users', { body })),
  );
}

export function useUpdateUser() {
  return useUsersMutation(async ({ id, body }: { id: number; body: Schemas['UserUpdateIn'] }) =>
    unwrap(await api.PATCH('/api/v1/users/{user_id}', { ...path(id), body })),
  );
}

export function useDeleteUser() {
  return useUsersMutation(async (id: number) =>
    unwrap(await api.DELETE('/api/v1/users/{user_id}', path(id))),
  );
}

export function useBlockUser() {
  return useUsersMutation(async ({ id, blocked }: { id: number; blocked: boolean }) =>
    unwrap(
      blocked
        ? await api.POST('/api/v1/users/{user_id}/block', path(id))
        : await api.POST('/api/v1/users/{user_id}/unblock', path(id)),
    ),
  );
}

export function useResetPassword() {
  return useUsersMutation(async ({ id, body }: { id: number; body: Schemas['ResetPasswordIn'] }) =>
    unwrap(await api.PUT('/api/v1/users/{user_id}/password', { ...path(id), body })),
  );
}

export function useSetRoles() {
  return useUsersMutation(async ({ id, roles }: { id: number; roles: string[] }) =>
    unwrap(await api.PUT('/api/v1/users/{user_id}/roles', { ...path(id), body: { roles } })),
  );
}

export function useRoles() {
  return useQuery({
    queryKey: ['roles'],
    queryFn: async () => unwrap(await api.GET('/api/v1/roles')),
    staleTime: 60_000,
  });
}
