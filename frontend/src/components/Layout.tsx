import { Anchor, AppShell, Button, Container, Group, Menu, Text } from '@mantine/core';
import {
  IconChevronDown,
  IconListCheck,
  IconPackages,
  IconSitemap,
  IconUsers,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, Outlet } from 'react-router';

import { useMe } from '../api/auth';
import { useSystemInfo } from '../api/system';
import { LanguageSwitch } from './LanguageSwitch';
import { ThemeToggle } from './ThemeToggle';
import { UserMenu } from './UserMenu';

function AdminMenu() {
  const { t } = useTranslation();
  return (
    <Menu position="bottom-start" withinPortal>
      <Menu.Target>
        <Button variant="subtle" size="xs" rightSection={<IconChevronDown size={14} />}>
          {t('nav.admin')}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={Link} to="/admin/users" leftSection={<IconUsers size={16} />}>
          {t('nav.users')}
        </Menu.Item>
        <Menu.Item component={Link} to="/admin/ldap" leftSection={<IconSitemap size={16} />}>
          {t('nav.ldap')}
        </Menu.Item>
        <Menu.Item component={Link} to="/admin/jobs" leftSection={<IconListCheck size={16} />}>
          {t('nav.jobs')}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function Layout() {
  const { t } = useTranslation();
  const systemInfo = useSystemInfo();
  const { data: me } = useMe();

  return (
    <AppShell header={{ height: 60 }} footer={{ height: 48 }} padding="md">
      <AppShell.Header>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between" wrap="nowrap">
            <Group gap="lg" wrap="nowrap">
              <Anchor component={Link} to="/" underline="never" c="inherit">
                <Group gap={8} wrap="nowrap">
                  <IconPackages size={26} />
                  <Text fw={700} size="lg">
                    {t('app.name')}
                  </Text>
                </Group>
              </Anchor>
              {me?.is_admin && !me.must_change_password && <AdminMenu />}
              <Anchor href="/api/docs" target="_blank" rel="noreferrer" size="sm">
                {t('nav.apiDocs')}
              </Anchor>
            </Group>
            <Group gap="sm" wrap="nowrap">
              <LanguageSwitch />
              <ThemeToggle />
              <UserMenu />
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="lg">
          <Outlet />
        </Container>
      </AppShell.Main>

      <AppShell.Footer>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between">
            <Text size="xs" c="dimmed">
              {t('footer.license')}
            </Text>
            {systemInfo.data && (
              <Text size="xs" c="dimmed">
                {t('footer.version', { version: systemInfo.data.version })}
              </Text>
            )}
          </Group>
        </Container>
      </AppShell.Footer>
    </AppShell>
  );
}
