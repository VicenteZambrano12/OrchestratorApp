/**
 * @file Browser theme utilities shared by React preference management.
 * Resolves system appearance and synchronizes document classes, color scheme,
 * preference metadata, and the browser chrome theme color without persisting state.
 */
export const themeStorageKey = 'form-theme'

/**
 * Tests whether a value is a supported theme preference.
 * @param {unknown} value - Candidate preference.
 * @returns {boolean} Whether light, dark, or system was supplied.
 */
export function isThemePreference(value) {
  return ['light', 'dark', 'system'].includes(value)
}

/**
 * Resolves system mode using the browser's current color-scheme media query.
 * @param {'light'|'dark'|'system'} preference - Validated preference.
 * @returns {'light'|'dark'} Appearance to apply.
 */
export function resolveTheme(preference) {
  return preference === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : preference
}

/**
 * Applies document appearance without changing local storage.
 * @param {'light'|'dark'|'system'} preference - Validated preference.
 * @param {HTMLElement} [root=document.documentElement] - Theme class/metadata target.
 * @returns {'light'|'dark'} Resolved appearance for React state synchronization.
 */
export function applyTheme(preference, root = document.documentElement) {
  const resolvedTheme = resolveTheme(preference)
  root.classList.toggle('dark', resolvedTheme === 'dark')
  root.dataset.themePreference = preference
  root.style.colorScheme = resolvedTheme
  const themeColor = document.querySelector('meta[name="theme-color"]')
  if (themeColor) themeColor.content = resolvedTheme === 'dark' ? '#0A0D0C' : '#F8FAFC'
  return resolvedTheme
}
