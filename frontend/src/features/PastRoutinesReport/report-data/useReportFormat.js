import { useTranslation } from 'react-i18next'
import { formatNumber } from './reportData'

export function useReportFormat() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage || 'en'
  const number = (value, digits = 0) => formatNumber(value, language, digits)
  const weight = (value, unit) => (value > 0 ? `${number(value, 1)} ${unit}` : t('Bodyweight'))
  return { t, language, number, weight }
}
