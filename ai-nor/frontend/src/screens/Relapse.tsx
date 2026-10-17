// Tab "Hlášení relapsu": record a recurrence / progression for a patient whose incidence report is confirmed.
// Stored in NorReport.progression (contract: backend/app/models.py ProgressionEvent), entered by the clinician.
// Saving the report resets the confirmation (backend PUT /report), so the clinician confirms it again in the same step.
import { useMemo, useState } from 'react'
import { api, type Case, type Codelists, type Extracted, type PartialDate } from '../api'
import { href } from '../router'
import { getUser } from '../user'
import { Icon } from '../icons'
import { Notice, PageHeader } from '../ui'
import { btn, diagnosis, formatDate, input, optionName, panel, patientName } from '../lib'

interface ProgressionEvent {
  status: Extracted<string>
  date: Extracted<PartialDate>
  sites: Extracted<number[]>
}

const KIND: Record<string, string> = { recurrence: 'Recidiva (relaps)', progression: 'Progrese', remission: 'Remise', stable: 'Stabilní onemocnění' }

const human = <T,>(value: T, by: string, status: Extracted['status'] = 'found'): Extracted<T> => ({
  value, coding: null, status, confidence: null, confidence_reasons: [], needs_review: false, evidence: [], alternatives: [], rules: [],
  review: { state: status === 'missing' ? 'pending' : 'edited', by, at: new Date().toISOString(), note: 'zadáno v záložce Hlášení relapsu' },
})

const showDate = (d: PartialDate | null | undefined) => (d ? [d.day, d.month, d.year].filter(Boolean).join('. ') : '—')
const toIso = (d: PartialDate | null | undefined) =>
  d?.day && d.month ? `${d.year}-${String(d.month).padStart(2, '0')}-${String(d.day).padStart(2, '0')}` : null
const todayIso = () => new Date().toISOString().slice(0, 10)

export default function Relapse({ caseId, cases, lists, onChanged }: {
  caseId: string | null
  cases: Case[]
  lists: Codelists | null
  onChanged: () => void
}) {
  const kase = cases.find((c) => c.id === caseId) ?? null
  const confirmed = cases.filter((c) => c.confirmed_at)
  const others = cases.filter((c) => !c.confirmed_at)

  const [kind, setKind] = useState('recurrence')
  const [date, setDate] = useState('')
  const [sites, setSites] = useState<number[]>([])
  const [doctor, setDoctor] = useState(getUser() || kase?.confirmed_by || '') // App remounts this screen per patient (key)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const events = useMemo(() => ((kase?.report.progression ?? []) as ProgressionEvent[]), [kase])
  const dgDate = kase ? toIso((kase.report.diagnosis_date as Extracted<PartialDate>)?.value) : null
  const siteOptions = (lists?.metastasis_sites ?? []).filter((o) => o.value !== 0)
  const dateError = date && date > todayIso() ? 'Datum nemůže být v budoucnosti.'
    : date && dgDate && date < dgDate ? `Datum je před datem diagnózy (${showDate((kase!.report.diagnosis_date as Extracted<PartialDate>).value)}).` : null

  /** Save the report with the new list of events and confirm it again (PUT /report drops the previous confirmation). */
  async function save(next: ProgressionEvent[], message: string) {
    if (!kase) return
    setBusy(true); setError(null); setSaved(null)
    try {
      const report = structuredClone(kase.report)
      report.progression = next
      await api.saveReport(kase.id, report)
      await api.confirm(kase.id, doctor.trim())
      setSaved(message)
      setDate(''); setSites([])
      onChanged()
    } catch (e) {
      setError(`${String(e instanceof Error ? e.message.replace(/^\d+: /, '') : e)}. Hlášení otevřete ve Vytěžování a potvrďte ho znovu.`)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  function add() {
    const by = doctor.trim()
    const [y, m, d] = date.split('-').map(Number)
    const event: ProgressionEvent = {
      status: human(kind, by),
      date: human({ year: y, month: m, day: d }, by),
      sites: sites.length ? human([...sites].sort((a, b) => a - b), by) : human<number[]>([], by, 'missing'),
    }
    save([...events, event], `${KIND[kind]} ze dne ${d}. ${m}. ${y} je uložená a hlášení znovu potvrzené.`)
  }

  return (
    <>
      <PageHeader title="Hlášení relapsu">
        Recidiva nebo progrese u pacienta, jehož hlášení incidence je potvrzené. Údaje zadává lékař, uloží se k hlášení pacienta a hlášení se znovu potvrdí.
      </PageHeader>

      <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <nav aria-label="Pacienti" className={`${panel} h-fit p-2`} data-tour="relapse">
          <h2 className="px-2 pb-1 pt-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Potvrzená hlášení</h2>
          {confirmed.length === 0 && <p className="px-2 pb-2 text-sm text-slate-600">Žádné. Relaps lze zapsat až k potvrzenému hlášení incidence.</p>}
          {confirmed.map((c) => {
            const on = c.id === caseId
            const n = ((c.report.progression as unknown[] | undefined) ?? []).length
            return (
              <a key={c.id} href={href('relaps', c.id)} aria-current={on ? 'page' : undefined}
                className={`block rounded-md px-2 py-1.5 text-sm transition-colors duration-150 ${on ? 'bg-fno-800 text-white' : 'text-slate-800 hover:bg-fno-50'}`}>
                <span className="block truncate font-medium">{patientName(c)}</span>
                <span className={`text-xs ${on ? 'text-fno-100' : 'text-slate-500'}`}>
                  {diagnosis(c, lists).code ?? 'bez dg.'} · {n ? `${n} ${n === 1 ? 'událost' : n < 5 ? 'události' : 'událostí'}` : 'bez relapsu'}
                </span>
              </a>
            )
          })}
          {others.length > 0 && (
            <p className="mt-2 border-t border-slate-100 px-2 pt-2 text-xs text-slate-500">
              {others.length} {others.length === 1 ? 'hlášení čeká' : 'hlášení čekají'} na potvrzení ve <a href={href('vytezovani')} className="underline underline-offset-2 hover:text-fno-800">Vytěžování</a>.
            </p>
          )}
        </nav>

        <div className="min-w-0 space-y-5">
          {!kase ? (
            <div className={`${panel} px-6 py-10 text-center`}>
              <Icon.relapse width={32} height={32} className="mx-auto text-fno-600" />
              <h2 className="mt-3 text-lg font-semibold text-fno-950">Vyberte pacienta</h2>
              <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">Vlevo jsou pacienti s potvrzeným hlášením incidence. Relaps se zapíše k jejich hlášení.</p>
            </div>
          ) : !kase.confirmed_at ? (
            <Notice tone="warn">
              Hlášení incidence pacienta {patientName(kase)} ještě není potvrzené. <a className="font-medium underline underline-offset-2" href={href('vytezovani', kase.id)}>Dokončete kontrolu ve Vytěžování</a>.
            </Notice>
          ) : (
            <>
              <PrimaryTumour c={kase} lists={lists} />

              <section>
                <h2 className="mb-2 text-base font-semibold text-fno-950">Zapsané události</h2>
                {events.length === 0 ? (
                  <p className={`${panel} px-4 py-4 text-sm text-slate-600`}>U pacienta zatím není zapsaná recidiva ani progrese.</p>
                ) : (
                  <div className={`${panel} overflow-x-auto`}>
                    <table className="w-full min-w-[560px] text-left text-sm">
                      <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-600">
                        <tr><th className="px-4 py-2 font-medium">Datum</th><th className="px-4 py-2 font-medium">Událost</th><th className="px-4 py-2 font-medium">Lokalizace</th><th className="px-4 py-2 font-medium">Zapsal</th><th /></tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {events.map((e, i) => (
                          <tr key={i}>
                            <td className="whitespace-nowrap px-4 py-2 tabular-nums">{showDate(e.date.value)}</td>
                            <td className="px-4 py-2 font-medium">{KIND[e.status.value ?? ''] ?? e.status.value ?? '—'}</td>
                            <td className="px-4 py-2 text-slate-700">{e.sites.value?.length ? e.sites.value.map((s) => optionName(lists?.metastasis_sites, s) ?? s).join(', ') : 'neuvedeno'}</td>
                            <td className="px-4 py-2 text-slate-600">{e.status.review.by ?? '—'}</td>
                            <td className="px-2 py-1 text-right">
                              <button className="rounded p-1.5 text-slate-500 transition-colors duration-150 hover:bg-red-50 hover:text-red-700 disabled:opacity-40" disabled={busy || !doctor.trim()}
                                title={doctor.trim() ? 'Odebrat a znovu potvrdit hlášení' : 'Nejdřív vyplňte jméno lékaře'} aria-label="Odebrat událost"
                                onClick={() => { if (window.confirm('Odebrat tuto událost a znovu potvrdit hlášení?')) save(events.filter((_, j) => j !== i), 'Událost je odebraná a hlášení znovu potvrzené.') }}>
                                <Icon.trash width={16} height={16} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className={`${panel} p-5`}>
                <h2 className="text-base font-semibold text-fno-950">Nová událost</h2>
                <div className="mt-4 grid gap-5 md:grid-cols-2">
                  <fieldset>
                    <legend className="mb-1.5 text-sm font-medium text-slate-900">Typ události</legend>
                    <div className="flex flex-wrap gap-2">
                      {['recurrence', 'progression'].map((k) => (
                        <label key={k} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors duration-150 ${kind === k ? 'border-fno-800 bg-fno-50 text-fno-950' : 'border-slate-300 hover:border-fno-600'}`}>
                          <input type="radio" name="kind" value={k} checked={kind === k} onChange={() => setKind(k)} className="size-4" />
                          {KIND[k]}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <label className="block text-sm">
                    <span className="mb-1.5 block font-medium text-slate-900">Datum zjištění</span>
                    <input type="date" className={input} value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} aria-invalid={!!dateError} />
                    {dateError && <span className="mt-1 block text-xs text-red-700">{dateError}</span>}
                  </label>
                </div>

                <fieldset className="mt-5">
                  <legend className="mb-1.5 text-sm font-medium text-slate-900">Lokalizace vzdálených metastáz <span className="font-normal text-slate-600">(nepovinné, u lokální recidivy nechte prázdné)</span></legend>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3 lg:grid-cols-4">
                    {siteOptions.map((o) => {
                      const v = Number(o.value)
                      return (
                        <label key={v} className="flex items-center gap-2 text-sm text-slate-800">
                          <input type="checkbox" className="size-4" checked={sites.includes(v)}
                            onChange={(e) => setSites(e.target.checked ? [...sites, v] : sites.filter((s) => s !== v))} />
                          {optionName(lists?.metastasis_sites, v) ?? o.label}
                        </label>
                      )
                    })}
                  </div>
                  {sites.length > 0 && <p className="mt-1.5 text-xs text-slate-600">Kód pro NOR (součet): <b className="tabular-nums">{sites.reduce((a, b) => a + b, 0)}</b></p>}
                </fieldset>

                <div className="mt-5 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-4">
                  <label className="block text-sm">
                    <span className="mb-1.5 block font-medium text-slate-900">Jméno lékaře</span>
                    <input className={`${input} w-64`} value={doctor} onChange={(e) => setDoctor(e.target.value)} />
                  </label>
                  <button className={btn.primary} disabled={busy || !date || !!dateError || !doctor.trim()} onClick={add}>
                    <Icon.check width={16} height={16} />{busy ? 'Ukládám…' : 'Uložit a potvrdit'}
                  </button>
                  <span className="text-xs text-slate-600">Uložením lékař znovu potvrzuje celé hlášení pacienta.</span>
                </div>
              </section>

              {saved && <Notice tone="ok">{saved}</Notice>}
              {error && <Notice tone="error">{error}</Notice>}
              <Notice tone="info">
                Relaps se ukládá k hlášení pacienta. Do exportu pro ÚZIS a do FHIR se zatím nepropisuje (mapování na mCODE <i>cancer-disease-status</i> je v plánu).
              </Notice>
            </>
          )}
        </div>
      </div>
    </>
  )
}

function PrimaryTumour({ c, lists }: { c: Case; lists: Codelists | null }) {
  const dg = diagnosis(c, lists)
  const r = c.report as Record<string, Extracted>
  const morph = r.morphology_code?.value as string | undefined
  const items: [string, string][] = [
    ['Diagnóza', dg.code ? `${dg.code} ${dg.name ?? ''}` : '—'],
    ['Datum diagnózy', showDate(r.diagnosis_date?.value as PartialDate | undefined)],
    ['Morfologie', morph ? `${morph} ${optionName(lists?.morphology_code, morph) ?? ''}` : '—'],
    ['Klinické stádium', (r.clinical_stage?.value as string | undefined) ?? '—'],
  ]
  return (
    <section className={`${panel} p-5`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-fno-950">{patientName(c)}</h2>
        <a href={href('vytezovani', c.id)} className={btn.ghost}>Hlášení incidence<Icon.chevron width={14} height={14} /></a>
      </div>
      <dl className="mt-3 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        {items.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-slate-600">{k}</dt>
            <dd className="font-medium text-slate-900">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-slate-600">Potvrdil {c.confirmed_by} · {formatDate(c.confirmed_at)}</p>
    </section>
  )
}
