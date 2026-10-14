import { useState } from 'react'

export function usePipelineExpansion() {
  const [expanded, setExpanded] = useState(true)

  function toggleExpansion() {
    setExpanded((current) => !current)
  }

  return { expanded, toggleExpansion }
}
