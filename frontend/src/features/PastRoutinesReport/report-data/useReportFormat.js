/** @file Locale-aware report formatting hook shared by history visualizations. */
import { useTranslation } from 'react-i18next'
import { formatNumber } from './reportData'

/**
 * Derives formatting helpers from the current translation locale; owns no state.
 * @returns {{t: import('i18next').TFunction, language: string,
 * number: (value: number, digits?: number) => string,
 * weight: (value: number, unit: string) => string}} Locale-bound formatters.
 */
export function useReportFormat() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage || 'en'
  /**
   * Formats numeric report measurements with the current locale.
   * @param {number} value - Measurement.
   * @param {number} [digits=0] - Maximum decimal places.
   * @returns {string} Localized number.
   */
  const number = (value, digits = 0) => formatNumber(value, language, digits)
  /**
   * Labels positive external load or the report's bodyweight category.
   * @param {number} value - Measured load.
   * @param {string} unit - Display unit, without conversion.
   * @returns {string} Localized load label.
   */
  const weight = (value, unit) => (value > 0 ? `${number(value, 1)} ${unit}` : t('Bodyweight'))
  return { t, language, number, weight }
}
