import { SegmentedControl } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { SUPPORTED_LANGUAGES } from '../i18n';

export function LanguageSwitch() {
  const { t, i18n } = useTranslation();

  return (
    <SegmentedControl
      size="xs"
      aria-label={t('header.language')}
      value={i18n.resolvedLanguage ?? 'ru'}
      onChange={(language) => void i18n.changeLanguage(language)}
      data={SUPPORTED_LANGUAGES.map((language) => ({
        value: language,
        label: language.toUpperCase(),
      }))}
    />
  );
}
