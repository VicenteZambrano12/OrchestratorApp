/** @file Shared decorative brand image with feature-owned sizing classes. */
import { getBrandAppearance } from '../../features/BrandMark/appearance/getBrandAppearance'

/**
 * Renders the brand image without duplicating an accessible name in surrounding UI.
 * @param {object} props - Appearance properties.
 * @param {boolean} [props.small=false] - Selects compact sizing.
 * @returns {import('react').ReactElement} Decorative image wrapper.
 */
export default function BrandMark({ small = false }) {
  const { className } = getBrandAppearance(small)
  return <span className={className}><img src="/icon.jpeg" alt="" /></span>
}
