// Tab "Vytěžování": review of one case (PLAN.md §6): AI extraction -> review queue -> preview -> confirm -> ÚZIS / FHIR.
// Moved here from App.tsx when the app got tabs; the review logic is unchanged.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, getField, type AiConfidence, type Case, type Codelists, type Evidence, type Extracted, type NorReport } from '../api'
import NorFormPreview from '../NorFormPreview'
import { href } from '../router'
import { Icon } from '../icons'
import { Notice, PageHeader, StatusBadge } from '../ui'
import { btn, panel, patientName, pendingCount } from '../lib'

const SECTIONS: [string, [string, string][]][] = [
  ['Diagnóza', [
    ['diagnosis_date', 'Datum stanovení diagnózy'],
    ['diagnosis_basis', 'K dg. vedla vyšetření'],
    ['laterality', 'Lateralita'],
    ['icd10', 'Dg. MKN'],
    ['topography', 'Topografie'],
  ]],
  ['Morfologie', [
    ['morphology_type', 'Typ morfologie'],
    ['morphology_code', 'Kód morfologie'],
    ['grade', 'Grading'],
    ['morphology_name', 'Název morfologie'],
  ]],
  ['TNM', [
    ['tnm_clinical.t', 'T'], ['tnm_clinical.n', 'N'], ['tnm_clinical.m', 'M'],
    ['tnm_pathological.t', 'pT'], ['tnm_pathological.n', 'pN'], ['tnm_pathological.m', 'pM'],
    ['pn_examined', 'pN vyš.'], ['pn_positive', 'pN poz.'], ['sentinel_node', 'sn'],
    ['metastasis_sites', 'Lokalizace vzdálených metastáz'], ['clinical_stage', 'Klinické stádium'],
  ]],
  ['Ostatní', [['disease_extent', 'Onemocnění']]],
]
const ALL_FIELDS = SECTIONS.flatMap(([, f]) => f)
const LATERALITY: Record<string, string> = {
  right: '1 - vpravo', left: '2 - vlevo', bilateral: '3 - oboustranně', not_applicable: '4 - odpadá', midline: '4 - odpadá', unknown: '9 - neznámo',
}

function show(path: string, v: unknown): string {
  if (v == null) return '—'
  if (path === 'laterality') return LATERALITY[String(v)] ?? String(v)
  if (typeof v === 'object' && !Array.isArray(v) && 'year' in (v as object)) {
    const d = v as { year: number; month?: number; day?: number }
    return [d.day, d.month, d.year].filter(Boolean).join('. ')
  }
  if (Array.isArray(v)) return v.length ? `${v.reduce((s: number, x) => s + Number(x), 0)} (${v.join(' + ')})` : 'žádné'
  return String(v)
}

function badge(f: Extracted): string {
  if (f.status === 'missing') return 'bg-red-50 text-red-800'
  if (f.status === 'conflict') return 'bg-violet-100 text-violet-800'
  const c = f.confidence ?? 0
  return c >= 85 ? 'bg-emerald-50 text-emerald-800' : c >= 60 ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-800'
}

const needsHuman = (f: Extracted) => f.needs_review && f.review.state === 'pending'

/** Overall AI confidence of the report (backend confidence.overall), with the breakdown in the tooltip. */
function AiScore({ c }: { c: AiConfidence | undefined }) {
  if (!c || c.score == null) return <span className="text-slate-500">Jistota AI: —</span>
  const color = c.score >= 85 ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
    : c.score >= 60 ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-red-50 text-red-800 border-red-200'
  const detail = [
    `Vážený průměr jistoty ${c.fields_ai} polí vyplněných AI (povinná pole NOR se počítají dvakrát).`,
    `Předvyplněno automaticky: ${c.auto_accepted} · ke kontrole: ${c.to_review} · rozpory: ${c.conflicts}`,
    `Opraveno lékařem (nepočítá se): ${c.edited_by_human} · chybí povinných polí: ${c.missing_required}`,
  ].join('\n')
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm ${color}`} title={detail}>
      Jistota AI <b className="tabular-nums">{c.score}</b><span className="text-xs opacity-80">/100 · {c.level}</span>
    </span>
  )
}

const small = 'inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition-colors duration-150'

export default function Extraction({ caseId, cases, lists, fhirUp, onChanged }: {
  caseId: string | null
  cases: Case[]
  lists: Codelists | null
  fhirUp: boolean
  onChanged: () => void // case list in the shell is stale
}) {
  const [kase, setCase] = useState<Case | null>(null)
  const [active, setActive] = useState<Evidence | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null)
  const [doctor, setDoctor] = useState('')
  const [fhirResult, setFhirResult] = useState<string | null>(null)
  const previewRef = useRef<HTMLElement>(null)
  const previewOpen = preview != null
  const latest = useRef<Case | null>(null)
  const saving = useRef<Promise<unknown>>(Promise.resolve())
  useEffect(() => { latest.current = kase }, [kase])

  // the preview renders below the document, so bring it into view when it opens (not on every edit inside it)
  useEffect(() => {
    if (previewOpen) previewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [previewOpen])

  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(label)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setBusy(null)
    }
  }

  function open(c: Case) {
    setCase(c)
    setActive(null)
    setPreview(null)
    setFhirResult(null)
  }

  useEffect(() => {
    if (!caseId) return
    let alive = true
    api.getCase(caseId).then((c) => { if (alive) { setError(null); open(c) } }).catch((e) => alive && setError(String(e instanceof Error ? e.message : e)))
    return () => { alive = false }
  }, [caseId])

  async function update(path: string, change: (f: Extracted) => void) {
    if (!kase) return
    const report = structuredClone(kase.report)
    change(getField(report, path))
    const saved = await run('Ukládám…', () => api.saveReport(kase.id, report))
    if (saved) {
      setCase(saved)
      onChanged()
      if (preview) setPreview(await api.uzisPreview(saved.id))
    }
  }

  // edit made directly in the form preview: save the report and refresh the preview in place.
  // Edits are queued and each one starts from the last saved report, so quick successive edits don't overwrite each other.
  async function editInPreview(change: (r: NorReport) => void) {
    const job = saving.current.then(async () => {
      const c = latest.current
      if (!c) return
      const report = structuredClone(c.report)
      change(report)
      const saved = await run('Ukládám…', () => api.saveReport(c.id, report))
      if (saved) {
        latest.current = saved
        setCase(saved)
        onChanged()
        setPreview(await api.uzisPreview(saved.id))
      }
    })
    saving.current = job.catch(() => {})
    await job
  }

  async function savePatient(ref: string | null): Promise<string | null> {
    if (!kase) return null
    try {
      const saved = await api.updatePatient(kase.id, ref)
      setCase(saved)
      setPreview(await api.uzisPreview(saved.id))
      onChanged()
      return null
    } catch (e) {
      return String(e instanceof Error ? e.message.replace(/^\d+: /, '') : e)
    }
  }

  const queue = useMemo(() => {
    if (!kase) return []
    return ALL_FIELDS.map(([p, l]) => ({ path: p, label: l, f: getField(kase.report, p) }))
      .filter(({ f }) => needsHuman(f))
      .sort((a, b) => Number(b.f.status === 'conflict') - Number(a.f.status === 'conflict') || (a.f.confidence ?? 0) - (b.f.confidence ?? 0))
  }, [kase])

  const doc = useMemo(
    () => kase?.documents.find((d) => d.id === active?.doc_id) ?? kase?.documents[0],
    [kase, active],
  )

  function RuleCite({ f }: { f: Extracted }) {
    if (!f.rules?.length) return null
    return (
      <div className="w-full pl-2 text-xs text-slate-600">
        {f.rules.map((r, i) => (
          <div key={i} title={r.source} className="flex items-start gap-1">
            <Icon.book width={14} height={14} className="mt-px shrink-0 text-fno-700" />
            <span>
              MKN-10 {r.code}{r.page ? `, str. ${r.page}` : ''}: „{r.quote}“{' '}
              {r.verified ? <span className="text-emerald-700">citace v pravidlech ověřena</span> : <span className="text-amber-700">citace neověřena</span>}
            </span>
          </div>
        ))}
      </div>
    )
  }

  function openPreview() {
    if (kase) run('Připravuji náhled…', () => api.uzisPreview(kase.id)).then((p) => p && setPreview(p))
  }

  function FieldActions({ path, f }: { path: string; f: Extracted }) {
    if (f.status === 'missing') {
      // a missing mandatory field: fill it in (the form has the right controls) or confirm that it is not documented
      return (
        <span className="flex flex-wrap items-center gap-1">
          <button className={`${small} bg-amber-600 text-white hover:bg-amber-700`} onClick={openPreview}>Doplnit v náhledu</button>
          <button className={`${small} border border-slate-300 text-slate-800 hover:bg-slate-100`}
            onClick={() => update(path, (x) => { x.review.state = 'confirmed' })}>Potvrdit: v dokumentaci není</button>
        </span>
      )
    }
    return (
      <span className="flex flex-wrap items-center gap-1">
        {f.status !== 'conflict' && f.alternatives.length > 0 && <span className="text-xs text-slate-500">návrh:</span>}
        {f.status !== 'conflict' &&
          f.alternatives.slice(0, 3).map((alt, i) => (
            <button key={`a${i}`} className={`${small} border border-fno-200 text-fno-800 hover:bg-fno-50`}
              onClick={() => update(path, (x) => { x.value = alt; x.review.state = 'edited' })}>
              {show(path, alt)}
            </button>
          ))}
        {f.status === 'conflict' &&
          [f.value, ...f.alternatives].map((alt, i) => (
            <button key={i} className={`${small} border border-violet-300 text-violet-900 hover:bg-violet-50`}
              onClick={() => update(path, (x) => { x.value = alt; x.status = 'found'; x.review.state = 'edited' })}>
              {show(path, alt)}
            </button>
          ))}
        {f.status !== 'conflict' && (
          <button className={`${small} bg-emerald-700 text-white hover:bg-emerald-800`} onClick={() => update(path, (x) => { x.review.state = 'confirmed' })}>
            <Icon.check width={14} height={14} />Potvrdit
          </button>
        )}
        <button className={`${small} bg-slate-100 text-slate-800 hover:bg-slate-200`}
          onClick={() => {
            const v = window.prompt('Nová hodnota', typeof f.value === 'string' || typeof f.value === 'number' ? String(f.value) : '')
            if (v != null) update(path, (x) => { x.value = typeof f.value === 'number' ? Number(v) : v; x.status = 'found'; x.review.state = 'edited' })
          }}>Upravit</button>
        <button className={`${small} bg-slate-100 text-slate-800 hover:bg-slate-200`} onClick={() => update(path, (x) => { x.review.state = 'rejected' })}>Zamítnout</button>
      </span>
    )
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className={`${panel} h-fit p-2 lg:sticky lg:top-4`}>
        <div className="flex items-center justify-between px-2 pb-2 pt-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Případy</h2>
          <a href={href('novy')} className={btn.ghost}><Icon.plus width={14} height={14} />Nový</a>
        </div>
        {cases.length === 0 && <p className="px-2 pb-2 text-sm text-slate-500">Zatím žádné případy. Nahrajte zprávy v záložce Nový pacient.</p>}
        <nav className="max-h-[70vh] space-y-0.5 overflow-auto">
          {cases.map((c) => (
            <a key={c.id} href={href('vytezovani', c.id)} aria-current={c.id === caseId ? 'page' : undefined}
              className={`block rounded-md px-2 py-1.5 text-sm transition-colors duration-150 ${c.id === caseId ? 'bg-fno-800 text-white' : 'text-slate-800 hover:bg-fno-50'}`}>
              <span className="block truncate font-medium">{patientName(c)}</span>
              <span className={`text-xs ${c.id === caseId ? 'text-fno-100' : 'text-slate-500'}`}>{c.documents.length} dok. · {c.confirmed_at ? 'potvrzeno' : `ke kontrole ${pendingCount(c)}`}</span>
            </a>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 space-y-4">
        {busy && <Notice tone="info">{busy}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
        {!caseId && (
          <div className={`${panel} px-6 py-10 text-center`}>
            <Icon.extract width={32} height={32} className="mx-auto text-fno-600" />
            <h1 className="mt-3 text-lg font-semibold text-fno-950">Vyberte případ ke kontrole</h1>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
              Vlevo je seznam nahraných pacientů. Nového pacienta založíte nahráním jeho zpráv, AI z nich vytěží hlášení NOR.
            </p>
            <a href={href('novy')} className={`${btn.primary} mt-4`}><Icon.upload width={16} height={16} />Nahrát zprávy pacienta</a>
          </div>
        )}

        {kase && kase.id === caseId && ( // nothing while another case loads
          <>
            <PageHeader title={patientName(kase)}
              actions={<>
                <button className={btn.secondary} onClick={() => run('AI vytěžuje hlášení… (obvykle 20–40 s)', () => api.extract(kase.id)).then((c) => { if (c) { open(c); onChanged() } })} disabled={!!busy}>Vytěžit znovu</button>
                <button className={btn.primary} disabled={!!busy} onClick={openPreview}>
                  Náhled a potvrzení <Icon.chevron width={16} height={16} />
                </button>
              </>}>
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <StatusBadge c={kase} />
                <span>{kase.documents.length} {kase.documents.length === 1 ? 'dokument' : kase.documents.length < 5 ? 'dokumenty' : 'dokumentů'}</span>
                <span>ke kontrole: <b className="tabular-nums">{queue.length}</b></span>
                <AiScore c={kase.ai_confidence} />
                {kase.confirmed_at && <span className="text-emerald-800">potvrdil {kase.confirmed_by}</span>}
              </span>
            </PageHeader>

            {kase.warnings.length > 0 && (
              <Notice tone="warn">{kase.warnings.map((w) => <div key={w}>{w}</div>)}</Notice>
            )}

            {queue.length > 0 && (
              <section className="rounded-lg border border-amber-300 bg-white p-4 shadow-[0_1px_3px_rgba(146,64,14,0.08)]">
                <h2 className="mb-2 text-sm font-semibold text-amber-900">Ke kontrole ({queue.length}): rozpory, nejistá a chybějící povinná pole</h2>
                {queue.map(({ path, label, f }) => (
                  <div key={path} className="flex flex-wrap items-center gap-2 border-t border-slate-100 py-2 text-sm first:border-0">
                    <span className={`rounded px-1.5 text-xs font-semibold tabular-nums ${badge(f)}`} title={f.confidence_reasons.join('\n')}>
                      {f.status === 'missing' ? 'chybí' : `${f.status === 'conflict' ? 'rozpor · ' : ''}${f.confidence}`}
                    </span>
                    <span className="w-48 text-slate-600">{label}</span>
                    {f.status === 'missing'
                      ? <span className="w-48 text-red-700">nenalezeno v dokumentaci</span>
                      : <b className="w-48">{show(path, f.value)}</b>}
                    {f.evidence.map((e, i) => (
                      <button key={i} className="text-xs text-fno-700 underline underline-offset-2 hover:text-fno-900" onClick={() => setActive(e)}>citace {i + 1}</button>
                    ))}
                    <span className="flex-1" />
                    <FieldActions path={path} f={f} />
                    <RuleCite f={f} />
                    {f.confidence_reasons.filter((r) => r.startsWith('✗ nesoulad')).map((r) => (
                      <div key={r} className="w-full pl-10 text-xs text-red-700">{r}</div>
                    ))}
                  </div>
                ))}
              </section>
            )}

            <div className="grid gap-4 xl:grid-cols-2">
              <section className={`${panel} p-3`}>
                <div className="mb-2 flex flex-wrap gap-1">
                  {kase.documents.map((d) => (
                    <button key={d.id} onClick={() => setActive({ doc_id: d.id, quote: '', start: 0, end: 0, verified: false })}
                      className={`rounded px-2 py-0.5 text-xs transition-colors duration-150 ${d.id === doc?.id ? 'bg-fno-800 text-white' : 'bg-slate-100 text-slate-700 hover:bg-fno-50'}`}>
                      {d.kind} · {d.filename.replace(/^Rakathon_2026_/, '')}
                    </button>
                  ))}
                </div>
                {doc && (
                  <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-800">
                    {active && active.doc_id === doc.id && active.end > active.start ? (
                      <>
                        {doc.text.slice(0, active.start)}
                        <mark className="rounded-sm bg-amber-200 px-0.5" ref={(el) => el?.scrollIntoView({ block: 'center' })}>{doc.text.slice(active.start, active.end)}</mark>
                        {doc.text.slice(active.end)}
                      </>
                    ) : doc.text}
                  </pre>
                )}
              </section>

              <section className={`${panel} p-4 text-sm`}>
                {SECTIONS.map(([title, fields]) => (
                  <div key={title} className="mb-4 last:mb-0">
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-fno-700">{title}</h3>
                    {fields.map(([path, label]) => {
                      const f = getField(kase.report, path)
                      const missing = f.status === 'missing'
                      const todo = missing && needsHuman(f) // mandatory and not resolved yet: must not look finished
                      return (
                        <div key={path} className={`flex flex-wrap items-center gap-2 border-b border-slate-100 py-1.5 last:border-0 ${todo ? '-mx-2 rounded bg-amber-50 px-2' : ''}`}>
                          <span className="w-48 text-slate-600">{label}</span>
                          <span className={`flex-1 ${todo ? 'font-medium text-amber-800' : missing || f.review.state === 'rejected' ? 'text-slate-500' : 'font-medium'}`}>
                            {todo ? 'chybí – doplňte, nebo potvrďte, že není'
                              : missing && f.review.state === 'confirmed' ? 'v dokumentaci není (potvrzeno lékařem)'
                              : missing ? 'chybí v dokumentaci' : f.review.state === 'rejected' ? 'zamítnuto' : show(path, f.value)}
                          </span>
                          {todo && <span className={`rounded px-1.5 text-xs font-semibold ${badge(f)}`} title={f.confidence_reasons.join('\n')}>chybí</span>}
                          {!missing && (
                            <span className={`rounded px-1.5 text-xs font-semibold tabular-nums ${badge(f)}`} title={f.confidence_reasons.join('\n')}>{f.confidence}</span>
                          )}
                          <span className="w-20 text-xs text-slate-500">
                            {f.review.state === 'auto_accepted' ? 'předvyplněno' : f.review.state === 'confirmed' ? 'potvrzeno' : f.review.state === 'edited' ? 'opraveno' : needsHuman(f) ? 'ke kontrole' : ''}
                          </span>
                          {f.evidence[0] && <button className="text-xs text-fno-700 underline underline-offset-2 hover:text-fno-900" onClick={() => setActive(f.evidence[0])}>zdroj</button>}
                          <RuleCite f={f} />
                        </div>
                      )
                    })}
                  </div>
                ))}
              </section>
            </div>

            {preview && (
              <section ref={previewRef} className="scroll-mt-4 rounded-lg border-2 border-fno-800 bg-white p-4 text-sm">
                <div className="mb-2 flex flex-wrap items-center gap-3">
                  <h2 className="font-semibold text-fno-950">Náhled hlášení · {String(preview.formular)} · stav: {String(preview.stav)}</h2>
                  <AiScore c={kase.ai_confidence} />
                </div>
                {(preview.chybi_povinne as string[]).length > 0 && (
                  <p className="mb-2 text-amber-800">Chybí povinná pole: {(preview.chybi_povinne as string[]).join(', ')}</p>
                )}
                <NorFormPreview data={preview} report={kase.report} lists={lists} editable={!kase.confirmed_at}
                  onEdit={editInPreview} onPatient={savePatient} />
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {!kase.confirmed_at ? (
                    <>
                      <input className="w-56 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-fno-sky focus:outline-none focus:ring-2 focus:ring-fno-sky/25"
                        placeholder="Jméno lékaře" aria-label="Jméno lékaře" value={doctor} onChange={(e) => setDoctor(e.target.value)} />
                      <button className="inline-flex items-center gap-2 rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:bg-slate-300 disabled:text-slate-500"
                        disabled={!doctor || queue.length > 0 || !!busy}
                        onClick={() => run('Potvrzuji…', () => api.confirm(kase.id, doctor)).then(async (c) => {
                          if (c) { open(c); onChanged(); setPreview(await api.uzisPreview(c.id)) }
                        })}>
                        <Icon.check width={16} height={16} />Potvrdit hlášení
                      </button>
                      {queue.length > 0 ? (
                        <span className="text-xs text-amber-800">Před potvrzením vyřešte {queue.length} polí ke kontrole (nahoře).</span>
                      ) : (
                        <span className="text-xs text-slate-600">Bez potvrzení se nic neexportuje do ÚZIS ani nezapíše do FHIR.</span>
                      )}
                    </>
                  ) : (
                    <>
                      <a className={btn.secondary} href={api.uzisExportUrl(kase.id)} target="_blank" rel="noreferrer">Export pro ÚZIS (JSON)</a>
                      <button className={btn.primary} disabled={!fhirUp || !!busy}
                        onClick={() => run('Zapisuji do IRIS FHIR…', () => api.submit(kase.id)).then((r) => { if (r) { setFhirResult(`Zapsáno do FHIR: ${r.entry?.length ?? 0} zdrojů`); onChanged() } })}>
                        Uložit do IRIS FHIR
                      </button>
                      {fhirResult && <span className="text-emerald-800">{fhirResult}</span>}
                    </>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}
