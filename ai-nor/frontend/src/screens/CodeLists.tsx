// Tab "Číselníky": browse the code lists the NOR form uses (GET /api/codelists), search ignores diacritics.
import { useDeferredValue, useMemo, useState } from 'react'
import type { Codelists, Option } from '../api'
import { go } from '../router'
import { Icon } from '../icons'
import { PageHeader } from '../ui'
import { fold, input, panel } from '../lib'

const LISTS: { id: string; name: string; source: string }[] = [
  { id: 'icd10', name: 'Dg. MKN-10', source: 'MKN-10-CZ 2026 (ÚZIS), kapitola novotvarů C00–D48' },
  { id: 'topography', name: 'Topografie', source: 'MKN-O-3 topografie, názvy z MKN-10-CZ 2026 (ÚZIS)' },
  { id: 'morphology_code', name: 'Morfologie', source: 'MKN-O-3 morfologie z rejstříku MKN-10 a tabelární části (ÚZIS)' },
  { id: 'grade', name: 'Grading', source: 'Formulář NOR „Incidence zhoubného novotvaru“' },
  { id: 'laterality', name: 'Lateralita', source: 'Formulář NOR' },
  { id: 'morphology_type', name: 'Typ morfologie', source: 'Formulář NOR' },
  { id: 'diagnosis_basis', name: 'K dg. vedla vyšetření', source: 'Formulář NOR (bitový součet)' },
  { id: 'metastasis_sites', name: 'Lokalizace metastáz', source: 'Formulář NOR (bitový součet)' },
  { id: 'clinical_stage', name: 'Klinické stádium', source: 'Formulář NOR (ukázkové hodnoty)' },
  { id: 'sentinel_node', name: 'Sentinelová uzlina', source: 'Formulář NOR' },
  { id: 'disease_extent', name: 'Onemocnění', source: 'Formulář NOR' },
]
const LIMIT = 300

/** "C50.4 - ZN prsu" -> ["C50.4", "ZN prsu"]; "01 klinické vyšetření" -> ["01", "klinické vyšetření"]. */
function split(o: Option): [string, string] {
  const dash = o.label.indexOf(' - ')
  if (dash >= 0) return [o.label.slice(0, dash), o.label.slice(dash + 3)]
  const m = /^(\S+)\s+(.*)$/.exec(o.label)
  return m && /\d/.test(m[1]) ? [m[1], m[2]] : [String(o.value), o.label]
}

export default function CodeLists({ lists, active }: { lists: Codelists | null; active: string | null }) {
  const [q, setQ] = useState('')
  const query = useDeferredValue(q)
  const current = LISTS.find((l) => l.id === active) ?? LISTS[0]
  const options = useMemo(() => lists?.[current.id] ?? [], [lists, current.id])

  const hits = useMemo(() => {
    const words = fold(query.trim()).split(/\s+/).filter(Boolean)
    if (!words.length) return options
    return options.filter((o) => {
      const hay = fold(`${o.label} ${o.search ?? ''}`)
      return words.every((w) => hay.includes(w))
    })
  }, [options, query])

  return (
    <>
      <PageHeader title="Číselníky">
        Kódy, ze kterých se vyplňuje hlášení NOR. AI smí vybrat jen kód, který tu je. Hledat můžete podle kódu, názvu i orgánu (např. „prs“, „C50“, „adenokarcinom“).
      </PageHeader>

      <div className="grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
        <label className="lg:hidden">
          <span className="mb-1 block text-sm font-medium text-slate-900">Číselník</span>
          <select className={input} value={current.id} onChange={(e) => go('ciselniky', e.target.value)}>
            {LISTS.map((l) => <option key={l.id} value={l.id}>{l.name} ({lists ? (lists[l.id]?.length ?? 0) : '…'})</option>)}
          </select>
        </label>
        <nav aria-label="Číselníky" className={`${panel} hidden h-fit p-2 lg:block`}>
          {LISTS.map((l) => {
            const on = l.id === current.id
            return (
              <button key={l.id} onClick={() => go('ciselniky', l.id)} aria-current={on ? 'page' : undefined}
                className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-1.5 text-left text-sm transition-colors duration-150 ${on ? 'bg-fno-800 text-white' : 'text-slate-800 hover:bg-fno-50'}`}>
                <span className="truncate">{l.name}</span>
                <span className={`text-xs tabular-nums ${on ? 'text-fno-100' : 'text-slate-500'}`}>{lists ? (lists[l.id]?.length ?? 0) : '…'}</span>
              </button>
            )
          })}
        </nav>

        <section className="min-w-0">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3" data-tour="codelists">
            <div>
              <h2 className="text-base font-semibold text-fno-950">{current.name}</h2>
              <p className="text-xs text-slate-600">Zdroj: {current.source}</p>
            </div>
            <label className="relative w-full sm:w-80">
              <span className="sr-only">Hledat v číselníku</span>
              <Icon.search width={16} height={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input className={`${input} pl-9`} placeholder={`Hledat v číselníku ${current.name}`} value={q} onChange={(e) => setQ(e.target.value)} />
            </label>
          </div>

          <div className={`${panel} overflow-hidden`}>
            {!lists ? (
              <p className="px-4 py-8 text-center text-sm text-slate-600">Číselníky se načítají, nebo backend neběží.</p>
            ) : hits.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-600">
                {options.length ? <>Nic neodpovídá „{query}“. Zkuste kód (C50), název nebo orgán.</> : 'Tento číselník se nepodařilo načíst ze souborů ÚZIS.'}
              </p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-600">
                  <tr>
                    <th className="w-28 px-4 py-2.5 font-medium">Kód</th>
                    <th className="px-4 py-2.5 font-medium">Název</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {hits.slice(0, LIMIT).map((o) => {
                    const [code, name] = split(o)
                    return (
                      <tr key={String(o.value)} className="align-top hover:bg-fno-50">
                        <td className="whitespace-nowrap px-4 py-2 font-semibold tabular-nums text-fno-900">{code}</td>
                        <td className="px-4 py-2 text-slate-800">
                          {name}
                          {o.search && query && <span className="mt-0.5 block truncate text-xs text-slate-500" title={o.search}>také: {o.search}</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
          {hits.length > LIMIT && (
            <p className="mt-2 text-xs text-slate-600">Zobrazeno prvních {LIMIT} z {hits.length} položek. Upřesněte hledání.</p>
          )}
          {hits.length > 0 && hits.length <= LIMIT && <p className="mt-2 text-xs text-slate-600">{hits.length} {hits.length === 1 ? 'položka' : hits.length < 5 ? 'položky' : 'položek'}</p>}
        </section>
      </div>
    </>
  )
}
