import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { setLanguage } from '../../i18n'

export default function LanguageToggle() {
  const { t, i18n } = useTranslation()
  const [error, setError] = useState('')

  async function changeLanguage(language) {
    try {
      await setLanguage(language)
      setError('')
    } catch (storageError) {
      console.error('Could not save language preference:', storageError)
      setError('Your language changed, but could not be saved on this device.')
    }
  }

  return <div className="language-controls">
    <div className="language-toggle" role="group" aria-label={t('Language')}>
      {['en', 'es'].map((language) => <button key={language} type="button" lang={language}
        aria-label={language === 'en' ? 'English' : 'Español'}
        aria-pressed={i18n.resolvedLanguage === language}
        onClick={() => changeLanguage(language)}>{language.toUpperCase()}</button>)}
    </div>
    {error && <span role="alert" className="error-message">{t(error)}</span>}
  </div>
}
