// Tab "Seznam hlášení": all cases with their status, searchable and filterable; a row opens the case in Vytěžování.
// The cases come from IRIS (Nor.CaseRecord); each one is also kept in IRIS FHIR (draft, then final), shown by an icon.
// Confirmed reports can be selected for a bulk export (CSV / JSON).
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type Case, type Codelists, type ExportInfo } from '../api'
import { go, href } from '../router'
import { Icon } from '../icons'
import { Notice, PageHeader, ScoreBadge, StatusBadge } from '../ui'
import { STATUS, STATUS_ORDER, btn, caseStatus, fhirState, pendingCount, diagnosis, fold, formatDate, input, panel, patientName, type CaseStatus } from '../lib'

type SortKey = 'updated' | 'patient' | 'score' | 'review'

const errorText = (e: unknown) => String(e instanceof Error ? e.message.replace(/^\d+: /, '') : e)

/** 'stale' when the report changed after the export (a change drops the confirmation; a new one is later than the export). */
function exportState(c: Case, info: ExportInfo | undefined): 'none' | 'ok' | 'stale' {
  if (!info) return 'none'
  return c.confirmed_at && new Date(info.at) >= new Date(c.confirmed_at) ? 'ok' : 'stale'
}

export default function CaseList({ cases, lists, status }: {
  cases: Case[]
  lists: Codelists | null
  status: string | null
}) {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortKey>('updated')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [exports, setExports] = useState<Record<string, ExportInfo>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [result, setResult] = useState<{ tone: 'ok' | 'warn' | 'error'; text: string } | null>(null)
  const filter = STATUS_ORDER.includes(status as CaseStatus) ? (status as CaseStatus) : null

  const loadExports = useCallback(() => { api.exportStatus().then(setExports).catch(() => {}) }, [])
  useEffect(() => { loadExports() }, [loadExports])

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

  // only confirmed reports can be exported; one un-confirmed meanwhile drops out of the selection
  const chosen = cases.filter((c) => selected.has(c.id) && c.confirmed_at)
  const confirmed = cases.filter((c) => c.confirmed_at)
  const selectable = rows.filter((r) => r.c.confirmed_at).map((r) => r.c.id)
  const allOn = selectable.length > 0 && selectable.every((id) => selected.has(id))
  const toggle = (id: string) => setSelected((s) => {
    const n = new Set(s)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })

  async function exportAs(format: 'csv' | 'json', which: Case[] = chosen) {
    setBusy('Exportuji…')
    setResult(null)
    try {
      const name = await api.exportReports(which.map((c) => c.id), format)
      setResult({ tone: 'ok', text: `Exportováno ${which.length} hlášení do souboru ${name}.` })
      setSelected(new Set())
      loadExports()
    } catch (e) {
      setResult({ tone: 'error', text: errorText(e) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <PageHeader title="Seznam hlášení"
        actions={<>
          <button className={btn.secondary} disabled={!confirmed.length || !!busy} onClick={() => exportAs('json', confirmed)}
            title={confirmed.length ? `Stáhne všech ${confirmed.length} potvrzených hlášení ve struktuře formuláře ÚZIS (JSON)` : 'Zatím žádné potvrzené hlášení'}>
            <Icon.download width={16} height={16} />Export pro ÚZIS ({confirmed.length})
          </button>
          <a href={href('novy')} className={btn.primary}><Icon.userPlus width={16} height={16} />Nový pacient</a>
        </>}>
        Všechna hlášení incidence uložená v IRIS. Klikněte na řádek a otevře se kontrola hlášení. Potvrzená hlášení zaškrtněte pro export.
        Do IRIS FHIR se každé hlášení zapisuje samo: po vytěžení jako rozpracované, po potvrzení jako konečné.
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

      {chosen.length > 0 && (
        <div role="toolbar" aria-label="Akce s vybranými hlášeními"
          className="sticky top-2 z-10 mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-fno-200 bg-fno-50 px-3 py-2 shadow-[0_4px_12px_rgba(1,28,62,0.08)]">
          <span className="mr-1 text-sm font-medium text-fno-950">Vybráno {chosen.length}</span>
          <button className={btn.primary} disabled={!!busy} onClick={() => exportAs('csv')}><Icon.download width={16} height={16} />Export CSV</button>
          <button className={btn.secondary} disabled={!!busy} onClick={() => exportAs('json')}><Icon.download width={16} height={16} />Export JSON</button>
          <span className="flex-1" />
          {busy && <span className="text-sm text-fno-900" aria-live="polite">{busy}</span>}
          <button className={btn.ghost} onClick={() => setSelected(new Set())}>Zrušit výběr</button>
        </div>
      )}
      {result && <div className="mb-3"><Notice tone={result.tone}>{result.text}</Notice></div>}

      <div className={`${panel} overflow-x-auto`} data-tour="cases">
        <table className="w-full min-w-[800px] text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-600">
            <tr>
              <th className="w-10 py-2.5 pl-4 pr-0">
                <input type="checkbox" className="size-4 align-middle" checked={allOn} disabled={!selectable.length}
                  onChange={() => setSelected(allOn ? new Set() : new Set(selectable))}
                  aria-label="Vybrat všechna potvrzená hlášení" title={selectable.length ? 'Vybrat všechna potvrzená hlášení' : 'Žádné potvrzené hlášení k exportu'} />
              </th>
              <Th sortKey="patient" sort={sort} setSort={setSort}>Pacient</Th>
              <th className="px-4 py-2.5 font-medium">Diagnóza</th>
              <th className="px-4 py-2.5 text-right font-medium">Zprávy</th>
              <Th sortKey="score" sort={sort} setSort={setSort} right>Jistota AI</Th>
              <Th sortKey="review" sort={sort} setSort={setSort} right>Ke kontrole</Th>
              <th className="px-4 py-2.5 font-medium">Stav</th>
              <Th sortKey="updated" sort={sort} setSort={setSort}>Upraveno</Th>
              <th className="w-20 px-2 py-2.5 text-center font-medium">Export · FHIR</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(({ c, dg }) => (
              <tr key={c.id} onClick={() => go('vytezovani', c.id)}
                className={`cursor-pointer transition-colors duration-150 hover:bg-fno-50 ${selected.has(c.id) ? 'bg-fno-50' : ''}`}>
                <td className="py-2.5 pl-4 pr-0" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" className="size-4 align-middle" checked={selected.has(c.id)} disabled={!c.confirmed_at} onChange={() => toggle(c.id)}
                    aria-label={`Vybrat ${patientName(c)}`} title={c.confirmed_at ? 'Vybrat k exportu' : 'Exportovat lze jen potvrzené hlášení'} />
                </td>
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
                <td className="px-2 py-2.5"><ExportIcons c={c} info={exports[c.id]} /></td>
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

const FHIR_ICON = { draft: 'text-fno-sky', final: 'text-fno-800', error: 'text-amber-600' }

/** Only icons, to keep the list narrow: exported (green; amber when the report changed since) and the IRIS FHIR record
 * (light blue = draft, navy = final, amber = the last write failed). */
function ExportIcons({ c, info }: { c: Case; info: ExportInfo | undefined }) {
  const state = exportState(c, info)
  const fhir = fhirState(c)
  return (
    <span className="flex items-center justify-center gap-1.5">
      {info && state !== 'none' && (
        <span role="img" className={state === 'ok' ? 'text-emerald-700' : 'text-amber-600'}
          aria-label={state === 'ok' ? 'Exportováno' : 'Změněno po exportu'}
          title={`${state === 'ok' ? 'Exportováno' : 'Změněno po exportu, exportujte znovu'}: ${formatDate(info.at)}, ${info.detail ?? ''}, ${info.actor}`}>
          <Icon.download width={17} height={17} />
        </span>
      )}
      {fhir.tone !== 'none' && (
        <span role="img" className={FHIR_ICON[fhir.tone]} aria-label={fhir.text} title={c.fhir.error ?? fhir.text}>
          <Icon.database width={17} height={17} />
        </span>
      )}
      {state === 'none' && fhir.tone === 'none' && <span className="text-slate-300" aria-label="Neexportováno" title="Neexportováno">–</span>}
    </span>
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
