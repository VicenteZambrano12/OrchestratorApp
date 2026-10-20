/**
 * @file Shared English/Spanish localization bootstrap and locale persistence.
 * Uses literal translation keys and updates the document language for accessibility.
 * Locale selection also informs the language sent by the chat view to the backend.
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './languages/en.json'
import es from './languages/es.json'
import { createLogger, errorType } from '../lib/observability/logger'

const logger = createLogger('i18n')

export const languageStorageKey = 'form-language'

/**
 * Resolves a supported saved preference, otherwise derives one from the browser.
 * Storage failures and invalid saved values are logged before browser fallback.
 * @returns {'en'|'es'} Initial supported locale.
 */
export function getInitialLanguage() {
  try {
    const saved = localStorage.getItem(languageStorageKey)
    if (saved === 'en' || saved === 'es') return saved
    if (saved !== null) logger.warn('language.invalid_preference')
  } catch (error) {
    logger.error('language.restore_failed', { error_type: errorType(error) })
  }
  return navigator.language?.toLowerCase().startsWith('es') ? 'es' : 'en'
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, es: { translation: es } },
  lng: getInitialLanguage(),
  fallbackLng: 'en',
  supportedLngs: ['en', 'es'],
  keySeparator: false,
  nsSeparator: false,
  interpolation: { escapeValue: false },
})

/**
 * Keeps document-level language metadata aligned with i18next notifications.
 * @param {string} language - Resolved locale emitted by i18next.
 * @returns {void}
 */
function updateDocumentLanguage(language) {
  document.documentElement.lang = language
}

updateDocumentLanguage(i18n.resolvedLanguage)
i18n.on('languageChanged', updateDocumentLanguage)

/**
 * Activates a supported locale before persisting it for the next visit.
 * @param {'en'|'es'} language - Requested locale.
 * @returns {Promise<void>} Resolves after activation and persistence.
 * @throws {Error} For unsupported locales or failed activation/storage; callers
 * must distinguish visible language changes from failed device persistence.
 */
export async function setLanguage(language) {
  // 1. Reject unsupported locales before notifying translation subscribers.
  if (!['en', 'es'].includes(language)) throw new Error(`Unsupported language: ${language}`)
  // 2. Update the UI, then persist; a storage failure does not undo activation.
  await i18n.changeLanguage(language)
  localStorage.setItem(languageStorageKey, language)
}

export default i18n
