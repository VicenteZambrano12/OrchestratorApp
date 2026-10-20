/** @file Pure appearance mapping shared by reusable brand marks. */

/**
 * Selects the CSS class contract without coupling presentation to context state.
 * @param {boolean} small - Whether compact sizing is requested.
 * @returns {{className: string}} Brand wrapper attributes.
 */
export function getBrandAppearance(small) {
  return {
    className: `brand-mark ${small ? 'small' : ''}`,
  }
}
