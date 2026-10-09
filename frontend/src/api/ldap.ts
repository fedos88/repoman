import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from './client';
import { unwrap } from './errors';

export type LdapSettings = Schemas['LdapSettingsOut'];
export type LdapSettingsInput = Schemas['LdapSettingsIn'];
export type LdapTestResult = Schemas['LdapTestOut'];
export type GroupMapping = Schemas['GroupMappingOut'];
export type SyncStatus = Schemas['SyncStatusOut'];

const LDAP_KEY = ['ldap'] as const;
const SETTINGS_KEY = [...LDAP_KEY, 'settings'] as const;
const MAPPINGS_KEY = [...LDAP_KEY, 'mappings'] as const;
const SYNC_KEY = [...LDAP_KEY, 'sync'] as const;

export function useLdapSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/ldap/settings')),
  });
}

export function useSaveLdapSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: LdapSettingsInput) =>
      unwrap(await api.PUT('/api/v1/ldap/settings', { body })),
    onSuccess: (saved) => {
      queryClient.setQueryData(SETTINGS_KEY, saved);
      void queryClient.invalidateQueries({ queryKey: SYNC_KEY });
      void queryClient.invalidateQueries({ queryKey: ['system'] });
    },
  });
}

export function useTestLdap() {
  return useMutation({
    mutationFn: async (body: Schemas['LdapTestIn']) =>
      unwrap(await api.POST('/api/v1/ldap/test', { body })),
  });
}

export function useGroupMappings() {
  return useQuery({
    queryKey: MAPPINGS_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/ldap/group-mappings')),
  });
}

export function useCreateGroupMapping() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas['GroupMappingIn']) =>
      unwrap(await api.POST('/api/v1/ldap/group-mappings', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MAPPINGS_KEY }),
  });
}

export function useDeleteGroupMapping() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (mappingId: number) =>
      unwrap(
        await api.DELETE('/api/v1/ldap/group-mappings/{mapping_id}', {
          params: { path: { mapping_id: mappingId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MAPPINGS_KEY }),
  });
}

const isActive = (status: SyncStatus | undefined) =>
  status?.last_job?.status === 'queued' || status?.last_job?.status === 'running';

export function useSyncStatus() {
  return useQuery({
    queryKey: SYNC_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/ldap/sync/status')),
    // Poll while a synchronization is in progress.
    refetchInterval: (query) => (isActive(query.state.data) ? 2000 : false),
  });
}

export function useStartSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/v1/ldap/sync')),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SYNC_KEY });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}
