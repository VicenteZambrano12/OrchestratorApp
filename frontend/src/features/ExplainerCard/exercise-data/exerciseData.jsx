export function isExerciseList(value) {
  return Array.isArray(value) && value.length > 0 && value.every((exercise) =>
    exercise && Number.isInteger(exercise.id) &&
    typeof exercise.name === 'string' && exercise.name.trim() &&
    (exercise.description === null || typeof exercise.description === 'string') &&
    (typeof exercise.instructions === 'string' ||
      (Array.isArray(exercise.instructions) && exercise.instructions.every((step) => typeof step === 'string'))) &&
    [exercise.icon_url, exercise.anatomy_diagram_url].every((url) => url == null || typeof url === 'string') &&
    (exercise.media_urls == null || (Array.isArray(exercise.media_urls) &&
      exercise.media_urls.every((url) => typeof url === 'string'))) &&
    typeof exercise.llm_explanation === 'string' && exercise.llm_explanation.trim())
}

export function parseInstructions(instructions) {
  const steps = Array.isArray(instructions) ? instructions : instructions.split(/\r?\n|(?=\b\d+\.\s)/)
  return steps.map((step) => step.replace(/^\s*\d+\.\s*/, '').trim()).filter(Boolean)
}

export function resolveExerciseAsset(path) {
  if (!path) return null
  const storedPath = path.replace(/^\/+/, '')
  if (storedPath.startsWith('database/images/')) {
    const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
    return `${baseUrl}/${storedPath}`
  }
  // Only web URLs and root-relative paths are usable image sources.
  if (/^https?:\/\//i.test(path) || (/^\/[^/]/.test(path))) return path
  return null
}
