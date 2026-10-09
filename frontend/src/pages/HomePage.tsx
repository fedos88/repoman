import {
  Alert,
  Badge,
  Blockquote,
  Button,
  Card,
  Group,
  List,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import {
  IconApi,
  IconBrandDocker,
  IconBrandOpenSource,
  IconBrandUbuntu,
  IconCheck,
  IconChartBar,
  IconInfoCircle,
  IconPackages,
  IconRefresh,
  IconRocket,
  IconStack2,
} from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

const BENEFITS = ['traffic', 'ci', 'availability', 'central', 'downloads', 'single'] as const;

const FEATURES: { key: string; icon: ReactNode }[] = [
  { key: 'free', icon: <IconRocket size={20} /> },
  { key: 'proxy', icon: <IconRefresh size={20} /> },
  { key: 'formats', icon: <IconStack2 size={20} /> },
  { key: 'openSource', icon: <IconBrandOpenSource size={20} /> },
  { key: 'deploy', icon: <IconPackages size={20} /> },
  { key: 'container', icon: <IconBrandDocker size={20} /> },
  { key: 'linux', icon: <IconBrandUbuntu size={20} /> },
  { key: 'ops', icon: <IconChartBar size={20} /> },
  { key: 'api', icon: <IconApi size={20} /> },
];

const FORMATS: { name: string; key: string }[] = [
  { name: 'Raw / HTTP', key: 'raw' },
  { name: 'npm', key: 'npm' },
  { name: 'Go', key: 'go' },
  { name: 'APT', key: 'apt' },
  { name: 'YUM / RPM', key: 'yum' },
  { name: 'Docker / OCI', key: 'docker' },
];

export function HomePage() {
  const { t } = useTranslation();

  return (
    <Stack gap={48} py="xl">
      <Stack gap="md">
        <Title order={1}>{t('app.name')}</Title>
        <Text size="xl" fw={500}>
          {t('home.tagline')}
        </Text>
        <Text c="dimmed">{t('home.intro')}</Text>
        <Group>
          <Button component="a" href="/api/docs" target="_blank" rel="noreferrer">
            {t('home.openApiDocs')}
          </Button>
        </Group>
        <Alert
          variant="light"
          color="yellow"
          icon={<IconInfoCircle />}
          title={t('home.status.title')}
        >
          {t('home.status.text')}
        </Alert>
      </Stack>

      <Stack gap="md">
        <Title order={2}>{t('home.why.title')}</Title>
        <Text>{t('home.why.text')}</Text>
        <List
          spacing="xs"
          icon={
            <ThemeIcon size={20} radius="xl" color="teal">
              <IconCheck size={14} />
            </ThemeIcon>
          }
        >
          {BENEFITS.map((key) => (
            <List.Item key={key}>{t(`home.why.benefits.${key}`)}</List.Item>
          ))}
        </List>
      </Stack>

      <Stack gap="md">
        <Title order={2}>{t('home.features.title')}</Title>
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {FEATURES.map(({ key, icon }) => (
            <Card key={key} withBorder padding="lg">
              <Group gap="sm" wrap="nowrap" align="flex-start">
                <ThemeIcon variant="light" size="lg">
                  {icon}
                </ThemeIcon>
                <Stack gap={4}>
                  <Text fw={600}>{t(`home.features.${key}.title`)}</Text>
                  <Text size="sm" c="dimmed">
                    {t(`home.features.${key}.text`)}
                  </Text>
                </Stack>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      </Stack>

      <Stack gap="md">
        <Title order={2}>{t('home.formats.title')}</Title>
        <Table.ScrollContainer minWidth={480}>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('home.formats.columns.format')}</Table.Th>
                <Table.Th>{t('home.formats.columns.purpose')}</Table.Th>
                <Table.Th>{t('home.formats.columns.status')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {FORMATS.map(({ name, key }) => (
                <Table.Tr key={key}>
                  <Table.Td fw={500}>{name}</Table.Td>
                  <Table.Td>{t(`home.formats.${key}`)}</Table.Td>
                  <Table.Td>
                    <Badge variant="light" color="orange">
                      {t('home.formats.statusInDevelopment')}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Stack>

      <Stack gap="md">
        <Title order={2}>{t('home.principle.title')}</Title>
        <Text>{t('home.principle.text')}</Text>
        <Blockquote>{t('home.principle.quote')}</Blockquote>
      </Stack>
    </Stack>
  );
}
