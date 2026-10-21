/** @file Localized-key selection for demo versus live Markdown routine previews. */

/**
 * Chooses review copy without interpreting or persisting the routine Markdown.
 * @param {boolean} demo - Whether the preview is explicitly illustrative.
 * @returns {{title: string, description: string}} Translation keys for preview copy.
 */
export function getPlanSummary(demo) {
  return {
    title: demo ? 'Your next chapter starts here' : 'Your coach’s recommendation',
    description: demo ? '3-day Push / Pull / Legs · Example plan' : 'Markdown plan · Ready to review',
  }
}
