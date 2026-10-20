/**
 * @file Stateless SVG radar renderer for already-normalized muscle metrics.
 * Geometry uses a fixed view box; callers normalize independent series so the
 * chart can compare distribution shapes without conflating raw units.
 */
const SIZE = 320
const CENTER = SIZE / 2
const RADIUS = 104
const RINGS = [0.25, 0.5, 0.75, 1]

/**
 * Converts a normalized radial value to chart coordinates, starting at the top.
 * @param {number} index - Axis index.
 * @param {number} total - Number of axes.
 * @param {number} ratio - Radius multiplier.
 * @returns {[number, number]} SVG x/y coordinates.
 */
function point(index, total, ratio) {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2
  return [CENTER + Math.cos(angle) * RADIUS * ratio, CENTER + Math.sin(angle) * RADIUS * ratio]
}

/**
 * Serializes radial values to SVG polygon points.
 * @param {number[]} values - Ordered normalized axis values.
 * @returns {string} Space-separated coordinate pairs.
 */
const polygon = (values) => values.map((value, index) => point(index, values.length, value).join(',')).join(' ')

/**
 * Renders normalized series, axis labels, and point-specific native tooltips.
 * @param {object} props - Chart properties.
 * @param {Array<{label: string, active: boolean, values: number[], tooltips?: string[]}>} props.axes - Metrics aligned with series indices.
 * @param {Array<{name: string, color: string}>} props.series - Legend names and SVG colors.
 * @param {string} props.label - Accessible chart description.
 * @returns {import('react').ReactElement} Accessible SVG chart.
 */
export default function RadarChart({ axes, series, label }) {
  const total = axes.length
  return <svg className="radar-chart" viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={label}>
    {RINGS.map((ring) => <polygon key={ring} className="radar-ring" points={polygon(axes.map(() => ring))} />)}
    {axes.map((axis, index) => {
      const [x, y] = point(index, total, 1)
      const [lx, ly] = point(index, total, 1.2)
      const anchor = Math.abs(lx - CENTER) < 8 ? 'middle' : lx > CENTER ? 'start' : 'end'
      return <g key={axis.label}>
        <line className="radar-spoke" x1={CENTER} y1={CENTER} x2={x} y2={y} />
        <text className={axis.active ? 'radar-label active' : 'radar-label'} x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle">{axis.label}</text>
      </g>
    })}
    {series.map((serie, serieIndex) => {
      const values = axes.map((axis) => axis.values[serieIndex])
      return <g key={serie.name} style={{ '--serie-color': serie.color }}>
        <polygon className={`radar-area radar-area-${serieIndex}`} points={polygon(values)} />
        {values.map((value, index) => {
          const [x, y] = point(index, total, value)
          return value > 0 && <circle key={axes[index].label} className="radar-dot" cx={x} cy={y} r="3.2">
            <title>{`${serie.name} · ${axes[index].label}: ${axes[index].tooltips?.[serieIndex] ?? ''}`}</title>
          </circle>
        })}
      </g>
    })}
  </svg>
}
