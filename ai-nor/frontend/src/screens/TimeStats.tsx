// Home: statistics for the current month, quarter or year, each compared with the previous period of the same length.
// Computed from the cases (created_at, confirmed_at, FHIR state, AI confidence) and the export log (GET /api/exports).
import { useEffect, useState } from 'react'
import { api, type Case, type ExportInfo } from '../api'
import { caseStatus, panel } from '../lib'

type Period = 'month' | 'quarter' | 'year'
const PERIODS: [Period, string][] = [['month', 'Měsíc'], ['quarter', 'Kvartál'], ['year', 'Rok']]
const PREVIOUS: Record<Period, string> = { month: 'minulý měsíc', quarter: 'minulé čtvrtletí', year: 'minulý rok' }
const MONTHS = ['leden', 'únor', 'březen', 'duben', 'květen', 'červen', 'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec']

/** [start, end) of the period containing `now`, shifted by `back` periods. */
function range(period: Period, now: Date, back = 0): [Date, Date] {
  const y = now.getFullYear()
  if (period === 'year') return [new Date(y - back, 0, 1), new Date(y - back + 1, 0, 1)]
  const len = period === 'month' ? 1 : 3
  const first = (period === 'month' ? now.getMonth() : Math.floor(now.getMonth() / 3) * 3) - back * len
  return [new Date(y, first, 1), new Date(y, first + len, 1)]
}

function title(period: Period, [start]: [Date, Date]): string {
  if (period === 'month') return `${MONTHS[start.getMonth()]} ${start.getFullYear()}`
  if (period === 'quarter') return `${Math.floor(start.getMonth() / 3) + 1}. čtvrtletí ${start.getFullYear()}`
  return `rok ${start.getFullYear()}`
}

const inside = (iso: string | null | undefined, [a, b]: [Date, Date]) => {
  if (!iso) return false
  const t = new Date(iso)
  return t >= a && t < b
}

interface Numbers {
  created: number
  confirmed: number
  fhir: number
  exported: number
  hours: number | null // mean time from upload to confirmation
  score: number | null // mean AI confidence of the reports created in the period
}

function compute(cases: Case[], exports: Record<string, ExportInfo>, r: [Date, Date]): Numbers {
  const created = cases.filter((c) => inside(c.created_at, r))
  const confirmed = cases.filter((c) => inside(c.confirmed_at, r))
  const waits = confirmed.map((c) => (new Date(c.confirmed_at!).getTime() - new Date(c.created_at).getTime()) / 3.6e6).filter((h) => h >= 0)
  const scores = created.map((c) => c.ai_confidence?.score).filter((s): s is number => s != null)
  return {
    created: created.length,
    confirmed: confirmed.length,
    fhir: confirmed.filter((c) => caseStatus(c) === 'fhir').length,
    exported: Object.values(exports).filter((e) => inside(e.at, r)).length,
    hours: waits.length ? waits.reduce((a, b) => a + b, 0) / waits.length : null,
    score: scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null,
  }
}

const duration = (h: number) => (h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${h.toFixed(h < 10 ? 1 : 0).replace('.', ',')} h` : `${Math.round(h / 24)} dní`)

export default function TimeStats({ cases }: { cases: Case[] }) {
  const [period, setPeriod] = useState<Period>('month')
  const [exports, setExports] = useState<Record<string, ExportInfo>>({})
  useEffect(() => { api.exportStatus().then(setExports).catch(() => {}) }, [])

  const [now] = useState(() => new Date()) // fixed for the page visit; periods are months, not seconds
  const current = range(period, now)
  const cur = compute(cases, exports, current)
  const prev = compute(cases, exports, range(period, now, 1))

  const tiles: { label: string; value: string; delta: number | null; hint: string; better?: 'up' | 'down' }[] = [
    { label: 'Nová hlášení', value: String(cur.created), delta: cur.created - prev.created, hint: 'Případy založené nahráním zpráv nebo ze zpráv z NIS.', better: 'up' },
    { label: 'Potvrzeno lékařem', value: String(cur.confirmed), delta: cur.confirmed - prev.confirmed, hint: 'Hlášení, která lékař v tomto období potvrdil.', better: 'up' },
    { label: 'Konečná v IRIS FHIR', value: String(cur.fhir), delta: cur.fhir - prev.fhir, hint: 'Potvrzená hlášení zapsaná v IRIS FHIR jako konečná (final).', better: 'up' },
    { label: 'Exportováno', value: String(cur.exported), delta: cur.exported - prev.exported, hint: 'Hlášení, jejichž poslední export (CSV / JSON) proběhl v tomto období.', better: 'up' },
    {
      label: 'Průměrně do potvrzení', value: cur.hours == null ? '–' : duration(cur.hours),
      delta: cur.hours != null && prev.hours != null ? cur.hours - prev.hours : null,
      hint: 'Průměrná doba od nahrání zpráv po potvrzení hlášení lékařem.', better: 'down',
    },
    { label: 'Průměrná jistota AI', value: cur.score == null ? '–' : `${cur.score}`, delta: cur.score != null && prev.score != null ? cur.score - prev.score : null, hint: 'Průměrná celková jistota AI u hlášení založených v tomto období (0–100).', better: 'up' },
  ]

  return (
    <section className="mb-6" aria-labelledby="stats-title" data-tour="stats">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="stats-title" className="text-base font-semibold text-fno-950">
          Statistika <span className="font-normal text-slate-600">· {title(period, current)}</span>
        </h2>
        <div role="group" aria-label="Období" className="inline-flex rounded-md border border-slate-300 bg-white p-0.5">
          {PERIODS.map(([p, label]) => (
            <button key={p} onClick={() => setPeriod(p)} aria-pressed={period === p}
              className={`rounded px-3 py-1 text-sm font-medium transition-colors duration-150 ${period === p ? 'bg-fno-800 text-white' : 'text-slate-700 hover:bg-fno-50'}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <dl className={`${panel} grid grid-cols-2 divide-slate-200 overflow-hidden sm:grid-cols-3 lg:grid-cols-6 lg:divide-x`}>
        {tiles.map((t, i) => (
          <div key={t.label} title={t.hint} className={`px-4 py-3 ${i % 2 ? 'border-l border-slate-200 sm:border-l-0' : ''} ${i >= 2 ? 'border-t border-slate-200 sm:border-t-0' : ''} ${i >= 3 ? 'sm:border-t lg:border-t-0' : ''} ${i % 3 ? 'sm:border-l lg:border-l-0' : ''}`}>
            <dt className="text-xs font-medium text-slate-600">{t.label}</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-fno-950">{t.value}</dd>
            <dd className="mt-0.5 text-xs text-slate-500"><Delta value={t.delta} better={t.better} format={i === 4 ? duration : undefined} />{` vs. ${PREVIOUS[period]}`}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Delta({ value, better, format }: { value: number | null; better?: 'up' | 'down'; format?: (n: number) => string }) {
  if (value == null) return <span>–</span>
  if (Math.abs(value) < 1e-9) return <span>beze změny</span>
  const good = better === 'down' ? value < 0 : value > 0
  const text = format ? format(Math.abs(value)) : String(Math.abs(Math.round(value)))
  return <span className={good ? 'font-medium text-emerald-700' : 'font-medium text-amber-700'}>{value > 0 ? '+' : '−'}{text}</span>
}
