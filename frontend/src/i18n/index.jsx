import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './languages/en.json'
import es from './languages/es.json'

export const languageStorageKey = 'form-language'

export function getInitialLanguage() {
  try {
    const saved = localStorage.getItem(languageStorageKey)
    if (saved === 'en' || saved === 'es') return saved
    if (saved !== null) console.warn('Unrecognized language preference:', saved)
  } catch (error) {
    console.error('Could not restore language preference:', error)
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

function updateDocumentLanguage(language) {
  document.documentElement.lang = language
}

updateDocumentLanguage(i18n.resolvedLanguage)
i18n.on('languageChanged', updateDocumentLanguage)

export async function setLanguage(language) {
  if (!['en', 'es'].includes(language)) throw new Error(`Unsupported language: ${language}`)
  await i18n.changeLanguage(language)
  localStorage.setItem(languageStorageKey, language)
}

export default i18n
