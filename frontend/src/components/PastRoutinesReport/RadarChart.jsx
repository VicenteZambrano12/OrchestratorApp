const SIZE = 320
const CENTER = SIZE / 2
const RADIUS = 104
const RINGS = [0.25, 0.5, 0.75, 1]

function point(index, total, ratio) {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2
  return [CENTER + Math.cos(angle) * RADIUS * ratio, CENTER + Math.sin(angle) * RADIUS * ratio]
}

const polygon = (values) => values.map((value, index) => point(index, values.length, value).join(',')).join(' ')

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
