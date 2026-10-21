/** @file Consumer hook enforcing the application's ThemeProvider boundary. */
import { useContext } from 'react'
import { ThemeContext } from './ThemeContext'

/**
 * Reads the current theme preference, resolved appearance, and preference setter.
 * Rerenders when ThemeProvider publishes a new value; owns no additional state.
 * @returns {{theme: 'light'|'dark'|'system', resolvedTheme: 'light'|'dark',
 * setTheme: (next: 'light'|'dark'|'system') => void}} Active theme context.
 * @throws {Error} When called outside ThemeProvider.
 */
export function useTheme() {
  const theme = useContext(ThemeContext)
  if (!theme) throw new Error('useTheme must be used within ThemeProvider.')
  return theme
}
