/**
 * @file Backend-unavailable page shared by startup health and runtime outage recovery.
 * Retry semantics belong to the caller: startup repeats health checks, while the
 * workspace reveals its preserved shell so the user can retry the failed action.
 */
import StartupScreen from '../../components/StartupScreen/StartupScreen'

/**
 * Presents a localized backend failure alert with language controls and recovery.
 * @param {object} props - Recovery view properties.
 * @param {() => void} props.onRetry - Caller-specific recovery action.
 * @returns {import('react').ReactElement} Full-page backend-unavailable message.
 */
function FailingView({ onRetry }) {
  return <StartupScreen kind="backend" onRetry={onRetry} />
}

export default FailingView
