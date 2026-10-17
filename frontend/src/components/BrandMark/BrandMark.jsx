import { getBrandAppearance } from '../../features/BrandMark/appearance/getBrandAppearance'

export default function BrandMark({ small = false }) {
  const { className } = getBrandAppearance(small)
  return <span className={className}><img src="/icon.jpeg" alt="" /></span>
}
