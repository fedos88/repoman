import { Button, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <Stack align="center" py={80} gap="md">
      <Title order={1}>404</Title>
      <Title order={3}>{t('notFound.title')}</Title>
      <Text c="dimmed">{t('notFound.text')}</Text>
      <Button component={Link} to="/" variant="light">
        {t('notFound.back')}
      </Button>
    </Stack>
  );
}
