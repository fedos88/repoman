import { ActionIcon, Badge, Code, Table, Text, Tooltip } from '@mantine/core';
import { IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import type { Token } from '../api/client';
import { formatDateTime } from '../utils/format';

type Props = {
  tokens: Token[];
  onRevoke: (token: Token) => void;
};

export function TokensTable({ tokens, onRevoke }: Props) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'ru';

  if (tokens.length === 0) {
    return <Text c="dimmed">{t('tokens.empty')}</Text>;
  }

  return (
    <Table.ScrollContainer minWidth={640}>
      <Table highlightOnHover withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t('tokens.name')}</Table.Th>
            <Table.Th>{t('tokens.prefix')}</Table.Th>
            <Table.Th>{t('tokens.created')}</Table.Th>
            <Table.Th>{t('tokens.expires')}</Table.Th>
            <Table.Th>{t('tokens.lastUsed')}</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {tokens.map((token) => {
            const expired = token.expires_at !== null && new Date(token.expires_at) <= new Date();
            return (
              <Table.Tr key={token.id}>
                <Table.Td>{token.name}</Table.Td>
                <Table.Td>
                  <Code>{token.prefix}…</Code>
                </Table.Td>
                <Table.Td>{formatDateTime(token.created_at, language)}</Table.Td>
                <Table.Td>
                  {token.expires_at === null ? (
                    t('tokens.never')
                  ) : expired ? (
                    <Badge color="red" variant="light">
                      {t('tokens.expired')}
                    </Badge>
                  ) : (
                    formatDateTime(token.expires_at, language)
                  )}
                </Table.Td>
                <Table.Td>{formatDateTime(token.last_used_at, language)}</Table.Td>
                <Table.Td>
                  <Tooltip label={t('tokens.revoke')}>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={t('tokens.revoke')}
                      onClick={() => onRevoke(token)}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
