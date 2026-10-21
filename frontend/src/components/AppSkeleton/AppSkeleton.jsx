/**
 * @file Accessible startup placeholder while backend and session checks settle.
 */
import StartupScreen from '../StartupScreen/StartupScreen'

/**
 * Renders a localized busy status without mounting user-dependent features.
 * Accepts no props; reads translation context and owns no asynchronous state.
 * @returns {import('react').ReactElement} Accessible loading shell.
 */
export default function AppSkeleton() {
  return <StartupScreen />
}
