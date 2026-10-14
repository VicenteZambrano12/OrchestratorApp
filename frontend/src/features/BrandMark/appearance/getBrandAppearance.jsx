export function getBrandAppearance(small) {
  return {
    className: `brand-mark ${small ? 'small' : ''}`,
    iconSize: small ? 17 : 22,
  }
}
