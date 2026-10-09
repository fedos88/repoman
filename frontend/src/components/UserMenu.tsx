import { Button, Menu } from '@mantine/core';
import { IconChevronDown, IconLogout, IconUser } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { useLogout, useMe } from '../api/auth';
import { displayName } from '../utils/format';

export function UserMenu() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: me, isPending } = useMe();
  const logout = useLogout();

  if (isPending) {
    return null;
  }
  if (!me) {
    return (
      <Button component={Link} to="/login" variant="light" size="xs">
        {t('auth.signIn')}
      </Button>
    );
  }

  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="subtle" size="xs" rightSection={<IconChevronDown size={14} />}>
          {displayName(me)}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={Link} to="/profile" leftSection={<IconUser size={16} />}>
          {t('nav.profile')}
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item
          leftSection={<IconLogout size={16} />}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/') })}
        >
          {t('auth.signOut')}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
