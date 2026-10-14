import { Layers3 } from 'lucide-react'
import { getBrandAppearance } from '../../features/BrandMark/appearance/getBrandAppearance'

export default function BrandMark({ small = false }) {
  const { className, iconSize } = getBrandAppearance(small)
  return <span className={className}><Layers3 size={iconSize} strokeWidth={2.5} /></span>
}
