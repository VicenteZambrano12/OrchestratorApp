/**
 * @file Exercise-explainer response validation, instruction normalization, and
 * media URL resolution. Database image paths are served through the backend API;
 * only supported web/root-relative image sources reach the gallery.
 *
 * @typedef {object} Exercise
 * @property {number} id - Integer catalog identifier.
 * @property {string} name - Nonempty catalog name.
 * @property {string|null} description - Optional catalog description.
 * @property {string|string[]} instructions - Text or already-separated instructions.
 * @property {string|null} [icon_url] - Catalog thumbnail path.
 * @property {string|null} [anatomy_diagram_url] - Anatomy image path.
 * @property {string[]|null} [media_urls] - Ordered movement frames.
 * @property {string} llm_explanation - Nonempty agent-generated Markdown.
 */

/**
 * Validates the nonempty structured exercise response before card rendering.
 * @param {unknown} value - Untrusted specialist output.
 * @returns {boolean} Whether every exercise satisfies the supported card contract.
 */
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

/**
 * Normalizes numbered text or string arrays into nonblank instruction steps.
 * @param {string|string[]} instructions - Validated instruction content.
 * @returns {string[]} Steps without their source numbering.
 */
export function parseInstructions(instructions) {
  const steps = Array.isArray(instructions) ? instructions : instructions.split(/\r?\n|(?=\b\d+\.\s)/)
  return steps.map((step) => step.replace(/^\s*\d+\.\s*/, '').trim()).filter(Boolean)
}

/**
 * Resolves stored backend image paths and accepts supported external/root URLs.
 * @param {string|null|undefined} path - Optional catalog asset path.
 * @returns {string|null} Usable image URL or null for missing/unsupported sources.
 */
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
