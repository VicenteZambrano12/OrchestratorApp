/**
 * @file Browser entry point composing localization, styles, observability, and
 * the React root. ErrorBoundary protects rendering, ThemeProvider owns appearance,
 * and App gates backend/session readiness. StrictMode exercises effect cleanup;
 * hot-module disposal removes the global observability listeners before reload.
 */
import { StrictMode } from 'react'
import './i18n'
import { createRoot } from 'react-dom/client'
import './index.css'
import './App.css'
import './theme.css'
import App from './App.jsx'
import { ThemeProvider } from './components/ThemeProvider/ThemeProvider'
import ErrorBoundary from './components/ErrorBoundary/ErrorBoundary'
import { initializeObservability } from './lib/observability/browser'

const disposeObservability = initializeObservability()
if (import.meta.hot) import.meta.hot.dispose(disposeObservability)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary><ThemeProvider><App /></ThemeProvider></ErrorBoundary>
  </StrictMode>,
)
