import { QUADRANT_COLOR, QUADRANT_LABEL, type Quadrant } from '../api'

export interface Dot {
  key: string
  fit: number
  readiness: number
  quadrant: Quadrant
  overtrading?: boolean
  label?: string
}

const W = 560
const H = 410
const PAD = { l: 50, r: 14, t: 14, b: 42 }
const THRESHOLD = 60
const x = (fit: number) => PAD.l + (fit / 100) * (W - PAD.l - PAD.r)
const y = (ready: number) => H - PAD.b - (ready / 100) * (H - PAD.t - PAD.b)

/** Plain SVG, no chart library. Fit on x, readiness on y, gridlines at the 60 threshold. */
export default function QuadrantChart({ dots, onSelect }: { dots: Dot[]; onSelect?: (key: string) => void }) {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 640, display: 'block' }} role="img"
         aria-label="Fit on the horizontal axis, readiness on the vertical axis, one dot per SME">
      <rect x={x(THRESHOLD)} y={PAD.t} width={x(100) - x(THRESHOLD)} height={y(THRESHOLD) - PAD.t} fill="#f5f0ff" rx="6" />
      <rect x={x(THRESHOLD)} y={y(THRESHOLD)} width={x(100) - x(THRESHOLD)} height={y(0) - y(THRESHOLD)} fill="#fffbeb" rx="6" />
      {[0, 20, 40, 60, 80, 100].map((t) => {
        const strong = t === THRESHOLD
        return (
          <g key={t} fontSize="10" fill="#8590a3">
            <line x1={x(t)} x2={x(t)} y1={PAD.t} y2={H - PAD.b} stroke={strong ? '#475467' : '#e8edf5'} strokeDasharray={strong ? '4 3' : undefined} />
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke={strong ? '#475467' : '#e8edf5'} strokeDasharray={strong ? '4 3' : undefined} />
            <text x={x(t)} y={H - PAD.b + 15} textAnchor="middle">{t}</text>
            <text x={PAD.l - 8} y={y(t) + 3} textAnchor="end">{t}</text>
          </g>
        )
      })}
      <text x={(W + PAD.l) / 2} y={H - 8} textAnchor="middle" fontSize="12" fontWeight="600" fill="#344054">Fit</text>
      <text transform={`translate(13 ${H / 2}) rotate(-90)`} textAnchor="middle" fontSize="12" fontWeight="600" fill="#344054">Readiness</text>
      <text x={x(THRESHOLD) + 8} y={PAD.t + 16} fontSize="11" fontWeight="700" fill={QUADRANT_COLOR.award_now}>{QUADRANT_LABEL.award_now}</text>
      <text x={x(THRESHOLD) + 8} y={y(0) - 8} fontSize="11" fontWeight="700" fill="#b45309">{QUADRANT_LABEL.coachable}</text>
      <text x={PAD.l + 8} y={PAD.t + 16} fontSize="11" fontWeight="700" fill={QUADRANT_COLOR.ready_weak_fit}>{QUADRANT_LABEL.ready_weak_fit}</text>
      <text x={PAD.l + 8} y={y(0) - 8} fontSize="11" fontWeight="700" fill="#667085">{QUADRANT_LABEL.develop}</text>
      {dots.map((d) => (
        <circle key={d.key} cx={x(d.fit)} cy={y(d.readiness)} r={d.overtrading ? 8 : 6.5}
                fill={QUADRANT_COLOR[d.quadrant]} fillOpacity="0.9"
                stroke={d.overtrading ? '#dc2626' : '#fff'} strokeWidth={d.overtrading ? 2.5 : 1.5}
                style={{ cursor: onSelect ? 'pointer' : 'default' }}
                tabIndex={onSelect ? 0 : undefined} role={onSelect ? 'link' : undefined}
                aria-label={d.label ? `${d.label}: fit ${d.fit}, readiness ${d.readiness}` : undefined}
                onClick={onSelect ? () => onSelect(d.key) : undefined}
                onKeyDown={onSelect ? (e) => e.key === 'Enter' && onSelect(d.key) : undefined}>
          <title>{`${d.label ? d.label + ': ' : ''}fit ${d.fit}, readiness ${d.readiness}${d.overtrading ? ' (overtrading risk)' : ''}`}</title>
        </circle>
      ))}
    </svg>
  )
}

export function QuadrantLegend() {
  return (
    <div className="quad-legend">
      {(Object.keys(QUADRANT_LABEL) as Quadrant[]).map((q) => (
        <span key={q}><i style={{ background: QUADRANT_COLOR[q] }} />{QUADRANT_LABEL[q]}</span>
      ))}
      <span><i style={{ background: '#fff', border: '2.5px solid #dc2626' }} />Overtrading risk</span>
    </div>
  )
}
