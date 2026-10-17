// Tab "Seznam hlášení": all cases with their status, searchable and filterable; a row opens the case in Vytěžování.
import { useMemo, useState, type ReactNode } from 'react'
import type { Case, Codelists } from '../api'
import { go, href } from '../router'
import { Icon } from '../icons'
import { PageHeader, ScoreBadge, StatusBadge } from '../ui'
import { STATUS, STATUS_ORDER, btn, caseStatus, pendingCount, diagnosis, fold, formatDate, input, panel, patientName, type CaseStatus } from '../lib'

type SortKey = 'updated' | 'patient' | 'score' | 'review'

export default function CaseList({ cases, lists, status }: { cases: Case[]; lists: Codelists | null; status: string | null }) {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortKey>('updated')
  const filter = STATUS_ORDER.includes(status as CaseStatus) ? (status as CaseStatus) : null

  const rows = useMemo(() => {
    const needle = fold(q.trim())
    const out = cases
      .map((c) => ({ c, s: caseStatus(c), dg: diagnosis(c, lists) }))
      .filter((r) => !filter || r.s === filter)
      .filter((r) => !needle || fold(`${patientName(r.c)} ${r.dg.code ?? ''} ${r.dg.name ?? ''} ${r.c.documents.map((d) => d.filename).join(' ')}`).includes(needle))
    const by: Record<SortKey, (a: (typeof out)[number], b: (typeof out)[number]) => number> = {
      updated: (a, b) => b.c.updated_at.localeCompare(a.c.updated_at),
      patient: (a, b) => patientName(a.c).localeCompare(patientName(b.c), 'cs'),
      score: (a, b) => (a.c.ai_confidence.score ?? 101) - (b.c.ai_confidence.score ?? 101),
      review: (a, b) => pendingCount(b.c) - pendingCount(a.c),
    }
    return out.sort(by[sort])
  }, [cases, lists, q, filter, sort])

  const count = (s: CaseStatus) => cases.filter((c) => caseStatus(c) === s).length
  const setFilter = (s: CaseStatus | null) => go('hlaseni', null, s ? { stav: s } : undefined)

  return (
    <>
      <PageHeader title="Seznam hlášení"
        actions={<a href={href('novy')} className={btn.primary}><Icon.userPlus width={16} height={16} />Nový pacient</a>}>
        Všechna hlášení incidence. Klikněte na řádek a otevře se kontrola hlášení.
      </PageHeader>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative min-w-60 flex-1 sm:max-w-sm">
          <span className="sr-only">Hledat</span>
          <Icon.search width={16} height={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input className={`${input} pl-9`} placeholder="Pacient, diagnóza nebo název zprávy" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filtr podle stavu">
          <Chip active={!filter} onClick={() => setFilter(null)}>Vše <span className="tabular-nums opacity-75">{cases.length}</span></Chip>
          {STATUS_ORDER.map((s) => (
            <Chip key={s} active={filter === s} onClick={() => setFilter(s)}>
              {STATUS[s].label} <span className="tabular-nums opacity-75">{count(s)}</span>
            </Chip>
          ))}
        </div>
      </div>

      <div className={`${panel} overflow-x-auto`}>
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-600">
            <tr>
              <Th sortKey="patient" sort={sort} setSort={setSort}>Pacient</Th>
              <th className="px-4 py-2.5 font-medium">Diagnóza</th>
              <th className="px-4 py-2.5 text-right font-medium">Zprávy</th>
              <Th sortKey="score" sort={sort} setSort={setSort} right>Jistota AI</Th>
              <Th sortKey="review" sort={sort} setSort={setSort} right>Ke kontrole</Th>
              <th className="px-4 py-2.5 font-medium">Stav</th>
              <Th sortKey="updated" sort={sort} setSort={setSort}>Upraveno</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(({ c, dg }) => (
              <tr key={c.id} onClick={() => go('vytezovani', c.id)} className="cursor-pointer transition-colors duration-150 hover:bg-fno-50">
                <td className="px-4 py-2.5">
                  <a href={href('vytezovani', c.id)} className="whitespace-nowrap font-medium text-slate-900 hover:text-fno-800" onClick={(e) => e.stopPropagation()}>{patientName(c)}</a>
                </td>
                <td className="max-w-80 px-4 py-2.5">
                  {dg.code ? <span className="block truncate" title={dg.name ?? ''}><b className="font-semibold">{dg.code}</b> <span className="text-slate-600">{dg.name}</span></span>
                    : <span className="text-slate-500">neurčena</span>}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">{c.documents.length}</td>
                <td className="px-4 py-2.5 text-right"><ScoreBadge score={c.ai_confidence?.score} /></td>
                <td className="px-4 py-2.5 text-right tabular-nums">{c.confirmed_at ? '—' : pendingCount(c)}</td>
                <td className="px-4 py-2.5"><StatusBadge c={c} /></td>
                <td className="whitespace-nowrap px-4 py-2.5 text-slate-600">{formatDate(c.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-slate-600">
            {cases.length === 0
              ? <>Zatím žádná hlášení. Začněte nahráním zpráv v záložce <a href={href('novy')} className="font-medium text-fno-800 underline underline-offset-2">Nový pacient</a>.</>
              : 'Žádné hlášení neodpovídá hledání nebo filtru.'}
          </div>
        )}
      </div>
    </>
  )
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150 ${active ? 'border-fno-800 bg-fno-800 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-fno-600 hover:text-fno-800'}`}>
      {children}
    </button>
  )
}

function Th({ sortKey, sort, setSort, right, children }: {
  sortKey: SortKey; sort: SortKey; setSort: (k: SortKey) => void; right?: boolean; children: ReactNode
}) {
  const on = sort === sortKey
  return (
    <th className={`px-4 py-2.5 font-medium ${right ? 'text-right' : ''}`}>
      <button onClick={() => setSort(sortKey)} className={`inline-flex items-center gap-1 hover:text-fno-800 ${on ? 'text-fno-800' : ''}`}>
        {children}
        <span aria-hidden="true" className={on ? 'opacity-100' : 'opacity-0'}>↓</span>
      </button>
    </th>
  )
}
