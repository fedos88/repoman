import { ActionIcon, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconMoon, IconSun } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

export function ThemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  // Until the user picks a theme explicitly, the OS preference is used.
  const computed = useComputedColorScheme('light', { getInitialValueInEffect: true });

  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label={t('header.toggleTheme')}
      title={t('header.toggleTheme')}
      onClick={() => setColorScheme(computed === 'dark' ? 'light' : 'dark')}
    >
      {computed === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
    </ActionIcon>
  );
}
