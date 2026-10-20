/**
 * @file Shared theme context separated from its provider for reusable consumers.
 * A null default deliberately makes missing-provider usage detectable by useTheme.
 */
import { createContext } from 'react'

/**
 * @type {import('react').Context<null|{
 *   theme: 'light'|'dark'|'system',
 *   resolvedTheme: 'light'|'dark',
 *   setTheme: (next: 'light'|'dark'|'system') => void
 * }>}
 */
export const ThemeContext = createContext(null)
