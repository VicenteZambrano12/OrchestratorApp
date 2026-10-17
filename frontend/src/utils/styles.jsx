export const themeStorageKey = 'form-theme'

export function isThemePreference(value) {
  return ['light', 'dark', 'system'].includes(value)
}

export function resolveTheme(preference) {
  return preference === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : preference
}

export function applyTheme(preference, root = document.documentElement) {
  const resolvedTheme = resolveTheme(preference)
  root.classList.toggle('dark', resolvedTheme === 'dark')
  root.dataset.themePreference = preference
  root.style.colorScheme = resolvedTheme
  const themeColor = document.querySelector('meta[name="theme-color"]')
  if (themeColor) themeColor.content = resolvedTheme === 'dark' ? '#0A0D0C' : '#F8FAFC'
  return resolvedTheme
}
