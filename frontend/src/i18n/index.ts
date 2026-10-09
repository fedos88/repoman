import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import en from './en.json';
import ru from './ru.json';

export const SUPPORTED_LANGUAGES = ['ru', 'en'] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

// Language: saved choice -> browser language (if supported) -> Russian.
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      en: { translation: en },
    },
    supportedLngs: SUPPORTED_LANGUAGES,
    nonExplicitSupportedLngs: true,
    load: 'languageOnly',
    fallbackLng: 'ru',
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'repoman-language',
      caches: ['localStorage'],
    },
  });

const syncDocumentLanguage = (language: string | undefined) => {
  if (language) {
    document.documentElement.lang = language;
  }
};
syncDocumentLanguage(i18n.resolvedLanguage);
i18n.on('languageChanged', () => syncDocumentLanguage(i18n.resolvedLanguage));

export default i18n;
