import {
  Accordion,
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  PasswordInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconAlertTriangle,
  IconCheck,
  IconPlugConnected,
  IconRefresh,
  IconTrash,
  IconX,
} from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../../api/errors';
import { isJobActive } from '../../api/jobs';
import {
  type LdapSettings,
  type LdapSettingsInput,
  type LdapTestResult,
  useCreateGroupMapping,
  useDeleteGroupMapping,
  useGroupMappings,
  useLdapSettings,
  useSaveLdapSettings,
  useStartSync,
  useSyncStatus,
  useTestLdap,
} from '../../api/ldap';
import { useRoles } from '../../api/users';
import { JobStatusBadge } from '../../components/JobStatusBadge';
import { formatDateTime } from '../../utils/format';

type Mode = LdapSettings['mode'];
const DEFAULT_PORTS: Record<Mode, number> = { ldap: 389, starttls: 389, ldaps: 636 };

type FormValues = Omit<
  LdapSettingsInput,
  | 'ca_certificate'
  | 'user_filter'
  | 'bind_password'
  | 'sync_interval_seconds'
  | 'sync_max_block_ratio'
> & {
  ca_certificate: string;
  user_filter: string;
  bind_password: string;
  sync_interval_minutes: number;
  sync_max_block_percent: number;
};

function toForm(settings: LdapSettings): FormValues {
  return {
    enabled: settings.enabled,
    mode: settings.mode,
    host: settings.host,
    port: settings.port,
    verify_certificate: settings.verify_certificate,
    ca_certificate: settings.ca_certificate ?? '',
    bind_dn: settings.bind_dn,
    bind_password: '',
    user_base_dn: settings.user_base_dn,
    user_filter: settings.user_filter ?? '',
    attr_username: settings.attr_username,
    attr_first_name: settings.attr_first_name,
    attr_last_name: settings.attr_last_name,
    attr_display_name: settings.attr_display_name,
    attr_email: settings.attr_email,
    sync_interval_minutes: Math.round((settings.sync_interval_seconds ?? 3600) / 60),
    sync_max_block_percent: Math.round((settings.sync_max_block_ratio ?? 0.5) * 100),
  };
}

function toInput(values: FormValues): LdapSettingsInput {
  const { sync_interval_minutes, sync_max_block_percent, bind_password, ...rest } = values;
  return {
    ...rest,
    ca_certificate: values.ca_certificate.trim() || null,
    user_filter: values.user_filter.trim() || null,
    // Empty: keep the saved password.
    bind_password: bind_password || null,
    sync_interval_seconds: sync_interval_minutes * 60,
    sync_max_block_ratio: sync_max_block_percent / 100,
  };
}

function TestResult({ result }: { result: LdapTestResult }) {
  const { t } = useTranslation();
  if (!result.ok) {
    return (
      <Alert color="red" icon={<IconX />} title={t('ldap.test.failed')}>
        <Text size="sm">
          {t(`errors.${result.error_code}`, { defaultValue: result.error_code ?? '' })}
        </Text>
        {result.message && (
          <Text size="xs" c="dimmed" mt={4}>
            {result.message}
          </Text>
        )}
      </Alert>
    );
  }
  return (
    <Alert color="teal" icon={<IconCheck />} title={t('ldap.test.ok')}>
      {result.user_found === false && <Text size="sm">{t('ldap.test.userNotFound')}</Text>}
      {result.user && (
        <Stack gap={2}>
          <Text size="sm">
            {t('ldap.test.userFound')}: <b>{result.user.username}</b>{' '}
            {result.user.display_name && `(${result.user.display_name})`}
          </Text>
          <Text size="xs" c="dimmed">
            {result.user.dn}
          </Text>
          <Group gap={4}>
            {result.user.disabled && (
              <Badge color="red" variant="light">
                {t('ldap.test.disabled')}
              </Badge>
            )}
            <Text size="sm">{t('ldap.test.roles')}:</Text>
            {result.user.roles.length === 0 ? (
              <Text size="sm" c="dimmed">
                —
              </Text>
            ) : (
              result.user.roles.map((role) => (
                <Badge key={role} variant="light">
                  {role}
                </Badge>
              ))
            )}
          </Group>
        </Stack>
      )}
    </Alert>
  );
}

function SettingsCard({ settings }: { settings: LdapSettings }) {
  const { t } = useTranslation();
  const save = useSaveLdapSettings();
  const test = useTestLdap();
  const [testUsername, setTestUsername] = useState('');

  const form = useForm<FormValues>({
    initialValues: toForm(settings),
    validate: {
      host: (value, values) => (values.enabled && !value.trim() ? t('validation.required') : null),
      bind_dn: (value, values) =>
        values.enabled && !value.trim() ? t('validation.required') : null,
      user_base_dn: (value, values) =>
        values.enabled && !value.trim() ? t('validation.required') : null,
      bind_password: (value, values) =>
        values.enabled && !value && !settings.has_bind_password ? t('validation.required') : null,
    },
  });

  useEffect(() => {
    form.setValues(toForm(settings));
    form.resetDirty();
    // Re-initialize only when saved settings change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  const values = form.getValues();
  const tls = values.mode !== 'ldap';

  const onModeChange = (mode: string) => {
    const current = form.getValues();
    form.setFieldValue('mode', mode as Mode);
    if (current.port === DEFAULT_PORTS[current.mode]) {
      form.setFieldValue('port', DEFAULT_PORTS[mode as Mode]);
    }
  };

  return (
    <Card withBorder padding="lg">
      <form
        onSubmit={form.onSubmit((formValues) =>
          save.mutate(toInput(formValues), {
            onSuccess: () => notifications.show({ color: 'teal', message: t('ldap.saved') }),
          }),
        )}
      >
        <Stack>
          <Group justify="space-between">
            <Title order={3}>{t('ldap.connection')}</Title>
            <Switch
              label={t('ldap.enabled')}
              {...form.getInputProps('enabled', { type: 'checkbox' })}
            />
          </Group>

          {save.isError && (
            <Alert color="red" icon={<IconX />}>
              {errorMessage(t, save.error)}
            </Alert>
          )}

          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                {t('ldap.mode')}
              </Text>
              <SegmentedControl
                value={values.mode}
                onChange={onModeChange}
                data={[
                  { value: 'ldaps', label: 'LDAPS' },
                  { value: 'starttls', label: 'StartTLS' },
                  { value: 'ldap', label: t('ldap.modes.ldap') },
                ]}
              />
            </Stack>
            <TextInput
              label={t('ldap.host')}
              placeholder="dc01.example.com"
              withAsterisk
              {...form.getInputProps('host')}
            />
            <NumberInput
              label={t('ldap.port')}
              min={1}
              max={65535}
              {...form.getInputProps('port')}
            />
          </SimpleGrid>

          {!tls && (
            <Alert color="red" icon={<IconAlertTriangle />} title={t('ldap.warnings.plainTitle')}>
              {t('ldap.warnings.plain')}
            </Alert>
          )}
          {tls && (
            <>
              <Switch
                label={t('ldap.verifyCertificate')}
                {...form.getInputProps('verify_certificate', { type: 'checkbox' })}
              />
              {values.verify_certificate ? (
                <Textarea
                  label={t('ldap.caCertificate')}
                  description={t('ldap.caCertificateHint')}
                  placeholder="-----BEGIN CERTIFICATE-----"
                  autosize
                  minRows={2}
                  maxRows={8}
                  styles={{ input: { fontFamily: 'monospace', fontSize: 12 } }}
                  {...form.getInputProps('ca_certificate')}
                />
              ) : (
                <Alert
                  color="red"
                  icon={<IconAlertTriangle />}
                  title={t('ldap.warnings.noVerifyTitle')}
                >
                  {t('ldap.warnings.noVerify')}
                </Alert>
              )}
            </>
          )}

          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              label={t('ldap.bindDn')}
              description={t('ldap.bindDnHint')}
              placeholder="DOMAIN\svc-repoman"
              withAsterisk
              {...form.getInputProps('bind_dn')}
            />
            <PasswordInput
              label={t('ldap.bindPassword')}
              description={settings.has_bind_password ? t('ldap.bindPasswordSaved') : undefined}
              placeholder={settings.has_bind_password ? '••••••••' : undefined}
              autoComplete="new-password"
              withAsterisk={!settings.has_bind_password}
              {...form.getInputProps('bind_password')}
            />
          </SimpleGrid>

          <TextInput
            label={t('ldap.userBaseDn')}
            description={t('ldap.userBaseDnHint')}
            placeholder="OU=Users,DC=example,DC=com"
            withAsterisk
            {...form.getInputProps('user_base_dn')}
          />
          <Textarea
            label={t('ldap.userFilter')}
            description={t('ldap.userFilterHint')}
            placeholder="(memberOf:1.2.840.113556.1.4.1941:=CN=RepoMan-Users,OU=Groups,DC=example,DC=com)"
            autosize
            minRows={1}
            styles={{ input: { fontFamily: 'monospace', fontSize: 12 } }}
            {...form.getInputProps('user_filter')}
          />

          <Accordion variant="contained">
            <Accordion.Item value="advanced">
              <Accordion.Control>{t('ldap.advanced')}</Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  <SimpleGrid cols={{ base: 1, sm: 3 }}>
                    <TextInput
                      label={t('ldap.attrs.username')}
                      {...form.getInputProps('attr_username')}
                    />
                    <TextInput
                      label={t('ldap.attrs.firstName')}
                      {...form.getInputProps('attr_first_name')}
                    />
                    <TextInput
                      label={t('ldap.attrs.lastName')}
                      {...form.getInputProps('attr_last_name')}
                    />
                    <TextInput
                      label={t('ldap.attrs.displayName')}
                      {...form.getInputProps('attr_display_name')}
                    />
                    <TextInput
                      label={t('ldap.attrs.email')}
                      {...form.getInputProps('attr_email')}
                    />
                  </SimpleGrid>
                  <SimpleGrid cols={{ base: 1, sm: 2 }}>
                    <NumberInput
                      label={t('ldap.syncInterval')}
                      suffix={` ${t('ldap.minutes')}`}
                      min={5}
                      max={10080}
                      {...form.getInputProps('sync_interval_minutes')}
                    />
                    <NumberInput
                      label={t('ldap.maxBlockRatio')}
                      description={t('ldap.maxBlockRatioHint')}
                      suffix="%"
                      min={1}
                      max={100}
                      {...form.getInputProps('sync_max_block_percent')}
                    />
                  </SimpleGrid>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>

          <Group justify="space-between" align="flex-end">
            <Group align="flex-end">
              <TextInput
                label={t('ldap.test.username')}
                placeholder="ivanov"
                value={testUsername}
                onChange={(event) => setTestUsername(event.currentTarget.value)}
              />
              <Button
                variant="default"
                leftSection={<IconPlugConnected size={16} />}
                loading={test.isPending}
                onClick={() =>
                  test.mutate({
                    ...toInput(form.getValues()),
                    test_username: testUsername.trim() || null,
                  })
                }
              >
                {t('ldap.test.run')}
              </Button>
            </Group>
            <Button type="submit" loading={save.isPending}>
              {t('common.save')}
            </Button>
          </Group>
          {test.isError && (
            <Alert color="red" icon={<IconX />}>
              {errorMessage(t, test.error)}
            </Alert>
          )}
          {test.data && <TestResult result={test.data} />}
        </Stack>
      </form>
    </Card>
  );
}

function GroupMappingsCard() {
  const { t } = useTranslation();
  const mappings = useGroupMappings();
  const roles = useRoles();
  const create = useCreateGroupMapping();
  const remove = useDeleteGroupMapping();

  const form = useForm({
    initialValues: { group_dn: '', role: 'admin' },
    validate: { group_dn: (value) => (value.trim() ? null : t('validation.required')) },
  });

  const onError = (error: unknown) =>
    notifications.show({ color: 'red', message: errorMessage(t, error) });

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Title order={3}>{t('ldap.mappings.title')}</Title>
        <Text size="sm" c="dimmed">
          {t('ldap.mappings.description')}
        </Text>
        {mappings.data && mappings.data.length > 0 && (
          <Table withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('ldap.mappings.group')}</Table.Th>
                <Table.Th>{t('ldap.mappings.role')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {mappings.data.map((mapping) => (
                <Table.Tr key={mapping.id}>
                  <Table.Td style={{ wordBreak: 'break-all' }}>{mapping.group_dn}</Table.Td>
                  <Table.Td>
                    <Badge variant="light">{mapping.role}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={t('common.delete')}
                      onClick={() =>
                        modals.openConfirmModal({
                          title: t('ldap.mappings.deleteTitle'),
                          children: <Text size="sm">{mapping.group_dn}</Text>,
                          labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
                          confirmProps: { color: 'red' },
                          onConfirm: () => remove.mutate(mapping.id, { onError }),
                        })
                      }
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
        <form
          onSubmit={form.onSubmit((values) =>
            create.mutate(
              { group_dn: values.group_dn.trim(), role: values.role },
              { onSuccess: () => form.reset(), onError },
            ),
          )}
        >
          <Group align="flex-end">
            <TextInput
              style={{ flex: 1 }}
              label={t('ldap.mappings.groupDn')}
              placeholder="CN=RepoMan-Admins,OU=Groups,DC=example,DC=com"
              {...form.getInputProps('group_dn')}
            />
            <Select
              label={t('ldap.mappings.role')}
              allowDeselect={false}
              w={180}
              data={(roles.data ?? []).filter((role) => role.assignable).map((role) => role.name)}
              {...form.getInputProps('role')}
            />
            <Button type="submit" loading={create.isPending}>
              {t('ldap.mappings.add')}
            </Button>
          </Group>
        </form>
      </Stack>
    </Card>
  );
}

function SyncCard() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'ru';
  const status = useSyncStatus();
  const start = useStartSync();
  const job = status.data?.last_job;
  const result = job?.result as Record<string, number> | null | undefined;

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Group justify="space-between">
          <Title order={3}>{t('ldap.sync.title')}</Title>
          <Button
            leftSection={<IconRefresh size={16} />}
            disabled={!status.data?.enabled || (job ? isJobActive(job) : false)}
            loading={start.isPending}
            onClick={() =>
              start.mutate(undefined, {
                onError: (error) =>
                  notifications.show({ color: 'red', message: errorMessage(t, error) }),
              })
            }
          >
            {t('ldap.sync.run')}
          </Button>
        </Group>
        <Text size="sm" c="dimmed">
          {t('ldap.sync.description')}
        </Text>
        {!status.data?.enabled ? (
          <Text c="dimmed">{t('ldap.sync.disabled')}</Text>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <Stack gap={2}>
              <Text size="xs" c="dimmed">
                {t('ldap.sync.lastRun')}
              </Text>
              {job ? (
                <Group gap="xs">
                  <JobStatusBadge status={job.status} />
                  <Text size="sm">
                    {formatDateTime(job.finished_at ?? job.created_at, language)}
                  </Text>
                </Group>
              ) : (
                <Text size="sm">—</Text>
              )}
            </Stack>
            <Stack gap={2}>
              <Text size="xs" c="dimmed">
                {t('ldap.sync.result')}
              </Text>
              <Text size="sm">
                {result && 'checked' in result ? t('ldap.sync.resultText', result) : '—'}
              </Text>
            </Stack>
            <Stack gap={2}>
              <Text size="xs" c="dimmed">
                {t('ldap.sync.nextRun')}
              </Text>
              <Text size="sm">{formatDateTime(status.data.next_run_at, language)}</Text>
            </Stack>
          </SimpleGrid>
        )}
        {job?.error && (
          <Alert color="red" icon={<IconX />}>
            {job.error}
          </Alert>
        )}
      </Stack>
    </Card>
  );
}

export function LdapPage() {
  const { t } = useTranslation();
  const settings = useLdapSettings();

  return (
    <Stack gap="lg" py="xl">
      <Title order={1}>{t('ldap.title')}</Title>
      {settings.isPending ? (
        <Loader />
      ) : settings.isError ? (
        <Text c="red">{errorMessage(t, settings.error)}</Text>
      ) : (
        <>
          <SettingsCard settings={settings.data} />
          <GroupMappingsCard />
          <SyncCard />
        </>
      )}
    </Stack>
  );
}
