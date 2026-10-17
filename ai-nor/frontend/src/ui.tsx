// Shared UI components for all tabs.
import type { ReactNode } from 'react'
import type { Case } from './api'
import { Icon } from './icons'
import { STATUS, caseStatus } from './lib'

export function StatusBadge({ c }: { c: Case }) {
  const s = STATUS[caseStatus(c)]
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${s.cls}`} title={s.hint}>
      <span className={`size-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-slate-400">—</span>
  const cls = score >= 85 ? 'bg-emerald-50 text-emerald-800' : score >= 60 ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-800'
  return <span className={`inline-block min-w-9 rounded px-1.5 py-0.5 text-center text-xs font-semibold tabular-nums ${cls}`}>{score}</span>
}

// ---------- building blocks ----------

export function PageHeader({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-fno-950">{title}</h1>
        {children && <p className="mt-1 max-w-3xl text-sm text-slate-600">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Notice({ tone, children }: { tone: 'info' | 'warn' | 'error' | 'ok'; children: ReactNode }) {
  const cls = {
    info: 'border-fno-200 bg-fno-50 text-fno-900',
    warn: 'border-amber-200 bg-amber-50 text-amber-900',
    error: 'border-red-200 bg-red-50 text-red-800',
    ok: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  }[tone]
  const I = tone === 'ok' ? Icon.check : tone === 'info' ? null : Icon.alert
  return (
    <div className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${cls}`} role={tone === 'error' ? 'alert' : undefined}>
      {I && <I className="mt-0.5 shrink-0" width={16} height={16} />}
      <div className="min-w-0">{children}</div>
    </div>
  )
}
