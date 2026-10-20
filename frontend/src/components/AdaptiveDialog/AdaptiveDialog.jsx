/** @file Shared native modal with responsive sheet motion and exit-owned focus restoration. */
import { useEffect, useRef } from 'react'
import { motion, useIsPresent, useReducedMotion } from 'framer-motion'
import './AdaptiveDialog.css'

/**
 * Native focus trapping and Escape semantics, with presence-owned exit motion.
 * Render conditionally inside AnimatePresence so the dialog stays modal until exit.
 */
export default function AdaptiveDialog({ children, className = '', onClose, dismissible = true, ...props }) {
  const dialogRef = useRef(null)
  const isPresent = useIsPresent()
  const reducedMotion = useReducedMotion() !== false

  useEffect(() => {
    const dialog = dialogRef.current
    const document = dialog.ownerDocument
    const trigger = document.activeElement
    dialog.showModal()
    return () => {
      dialog.close()
      const target = trigger?.isConnected ? trigger : document.getElementById('workspace-content')
      target?.focus({ preventScroll: true })
    }
  }, [])

  function dismiss() {
    if (dismissible && isPresent) onClose()
  }

  return <motion.dialog
    {...props}
    ref={dialogRef}
    className={`adaptive-dialog ${className}`}
    inert={!isPresent}
    initial={reducedMotion ? false : { opacity: 0, y: 'var(--dialog-offset)' }}
    animate={{ opacity: 1, y: 0 }}
    exit={reducedMotion ? { opacity: 1 } : { opacity: 0, y: 'var(--dialog-offset)' }}
    transition={{ duration: reducedMotion ? 0 : 0.18, ease: 'easeOut' }}
    onCancel={(event) => { event.preventDefault(); dismiss() }}
    onClick={(event) => {
      if (event.target !== event.currentTarget) return
      const { left, right, top, bottom } = event.currentTarget.getBoundingClientRect()
      if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) dismiss()
    }}
  >{children}</motion.dialog>
}
