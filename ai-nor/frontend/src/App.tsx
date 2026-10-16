// Simple working UI (PLAN.md §6): upload -> AI extraction -> review queue -> preview -> confirm -> ÚZIS / FHIR.
// The polished UI comes later; keep this one boring and correct.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, getField, type AiConfidence, type Case, type Codelists, type Evidence, type Extracted, type NorReport } from './api'
import NorFormPreview from './NorFormPreview'

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
  if (f.status === 'missing') return 'bg-red-100 text-red-800'
  if (f.status === 'conflict') return 'bg-purple-100 text-purple-800'
  const c = f.confidence ?? 0
  return c >= 85 ? 'bg-green-100 text-green-800' : c >= 60 ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
}

const needsHuman = (f: Extracted) => f.needs_review && f.review.state === 'pending'

/** Overall AI confidence of the report (backend confidence.overall), with the breakdown in the tooltip. */
function AiScore({ c }: { c: AiConfidence | undefined }) {
  if (!c || c.score == null) return <span className="text-slate-400">Jistota AI: —</span>
  const color = c.score >= 85 ? 'bg-green-100 text-green-800 border-green-300'
    : c.score >= 60 ? 'bg-amber-100 text-amber-800 border-amber-300' : 'bg-red-100 text-red-800 border-red-300'
  const detail = [
    `Vážený průměr jistoty ${c.fields_ai} polí vyplněných AI (povinná pole NOR se počítají dvakrát).`,
    `Předvyplněno automaticky: ${c.auto_accepted} · ke kontrole: ${c.to_review} · rozpory: ${c.conflicts}`,
    `Opraveno lékařem (nepočítá se): ${c.edited_by_human} · chybí povinných polí: ${c.missing_required}`,
  ].join('\n')
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm ${color}`} title={detail}>
      Jistota AI <b className="tabular-nums">{c.score}</b><span className="text-xs opacity-75">/100 · {c.level}</span>
    </span>
  )
}

export default function App() {
  const [health, setHealth] = useState<{ llm_mode: string; fhir: boolean } | null>(null)
  const [cases, setCases] = useState<Case[]>([])
  const [kase, setCase] = useState<Case | null>(null)
  const [active, setActive] = useState<Evidence | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null)
  const [doctor, setDoctor] = useState('')
  const [fhirResult, setFhirResult] = useState<string | null>(null)
  const [lists, setLists] = useState<Codelists | null>(null)
  const previewRef = useRef<HTMLElement>(null)
  const previewOpen = preview != null
  const latest = useRef<Case | null>(null)
  const saving = useRef<Promise<unknown>>(Promise.resolve())
  useEffect(() => { latest.current = kase }, [kase])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api.cases().then(setCases).catch(() => {})
    api.codelists().then(setLists).catch(() => setLists(null))
  }, [])

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

  async function onUpload(files: FileList | null) {
    if (!files?.length) return
    const created = await run('Nahrávám dokumenty…', () => api.createCase([...files]))
    if (!created) return
    open(created)
    const extracted = await run('AI vytěžuje hlášení… (obvykle 20–40 s)', () => api.extract(created.id))
    if (extracted) open(extracted)
    api.cases().then(setCases)
  }

  async function update(path: string, change: (f: Extracted) => void) {
    if (!kase) return
    const report = structuredClone(kase.report)
    change(getField(report, path))
    const saved = await run('Ukládám…', () => api.saveReport(kase.id, report))
    if (saved) {
      setCase(saved)
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
      api.cases().then(setCases)
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
          <div key={i} title={r.source}>
            📖 MKN-10 {r.code}{r.page ? `, str. ${r.page}` : ''}: „{r.quote}“{' '}
            {r.verified ? <span className="text-green-700">✓ citace v pravidlech</span> : <span className="text-amber-700">citace neověřena</span>}
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
        <span className="whitespace-nowrap">
          <button className="mr-1 rounded bg-amber-600 px-2 text-xs text-white" onClick={openPreview}>✎ Doplnit v náhledu</button>
          <button className="rounded border border-slate-300 px-2 text-xs hover:bg-slate-100"
            onClick={() => update(path, (x) => { x.review.state = 'confirmed' })}>Potvrdit: v dokumentaci není</button>
        </span>
      )
    }
    return (
      <span className="whitespace-nowrap">
        {f.status !== 'conflict' && f.alternatives.length > 0 && <span className="mr-1 text-xs text-slate-500">návrh:</span>}
        {f.status !== 'conflict' &&
          f.alternatives.slice(0, 3).map((alt, i) => (
            <button key={`a${i}`} className="mr-1 rounded border border-blue-300 px-1.5 text-xs text-blue-800 hover:bg-blue-50"
              onClick={() => update(path, (x) => { x.value = alt; x.review.state = 'edited' })}>
              {show(path, alt)}
            </button>
          ))}
        {f.status === 'conflict' &&
          [f.value, ...f.alternatives].map((alt, i) => (
            <button key={i} className="mr-1 rounded border px-1.5 text-xs hover:bg-slate-100"
              onClick={() => update(path, (x) => { x.value = alt; x.status = 'found'; x.review.state = 'edited' })}>
              {show(path, alt)}
            </button>
          ))}
        {f.status !== 'conflict' && (
          <button className="mr-1 rounded bg-green-600 px-2 text-xs text-white" onClick={() => update(path, (x) => { x.review.state = 'confirmed' })}>✓ Potvrdit</button>
        )}
        <button className="mr-1 rounded bg-slate-100 px-2 text-xs"
          onClick={() => {
            const v = window.prompt('Nová hodnota', typeof f.value === 'string' || typeof f.value === 'number' ? String(f.value) : '')
            if (v != null) update(path, (x) => { x.value = typeof f.value === 'number' ? Number(v) : v; x.status = 'found'; x.review.state = 'edited' })
          }}>✎</button>
        <button className="rounded bg-slate-100 px-2 text-xs" onClick={() => update(path, (x) => { x.review.state = 'rejected' })}>✗</button>
      </span>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between border-b bg-white px-6 py-3">
        <h1 className="text-lg font-semibold">AI NOR · hlášení novotvaru</h1>
        <div className="text-sm text-slate-500">LLM: {health?.llm_mode ?? '?'} · IRIS FHIR: {health?.fhir ? 'online' : 'offline'}</div>
      </header>

      <div className="grid grid-cols-[220px_1fr] gap-4 p-4">
        <aside className="space-y-3">
          <label className="block rounded-lg border bg-white p-3 text-sm font-medium">
            Nahrát dokumenty pacienta (PDF, TXT, XLSX)
            <input type="file" multiple accept=".pdf,.txt,.md,.xlsx" className="mt-2 block w-full text-xs"
              onChange={(e) => { onUpload(e.target.files); e.target.value = '' }} disabled={!!busy} />
          </label>
          <div className="rounded-lg border bg-white p-2 text-sm">
            <div className="mb-1 px-1 text-xs font-medium text-slate-500">Případy</div>
            {cases.map((c) => (
              <button key={c.id} onClick={() => api.getCase(c.id).then(open)}
                className={`block w-full truncate rounded px-2 py-1 text-left ${c.id === kase?.id ? 'bg-slate-800 text-white' : 'hover:bg-slate-100'}`}>
                {c.patient_ref ?? c.documents[0]?.filename ?? c.id.slice(0, 8)} {c.confirmed_at ? '✓' : ''}
              </button>
            ))}
          </div>
        </aside>

        <main className="space-y-4">
          {busy && <div className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">{busy}</div>}
          {error && <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
          {!kase && <p className="text-sm text-slate-500">Nahrajte dokumenty pacienta nebo vyberte případ.</p>}

          {kase && (
            <>
              <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-white px-4 py-2 text-sm">
                <b>{kase.patient_ref ?? 'Pacient'}</b>
                <span>{kase.documents.length} dokumenty</span>
                <span>ke kontrole: <b>{queue.length}</b></span>
                <AiScore c={kase.ai_confidence} />
                {kase.confirmed_at && <span className="text-green-700">✓ potvrdil {kase.confirmed_by}</span>}
                <span className="flex-1" />
                <button className="rounded border px-3 py-1" onClick={() => run('AI vytěžuje hlášení…', () => api.extract(kase.id)).then((c) => c && open(c))} disabled={!!busy}>Vytěžit znovu</button>
                <button className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-40" disabled={!!busy} onClick={openPreview}>
                  Náhled a potvrzení →
                </button>
              </div>

              {kase.warnings.length > 0 && (
                <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  {kase.warnings.map((w) => <div key={w}>⚠ {w}</div>)}
                </div>
              )}

              {queue.length > 0 && (
                <section className="rounded-lg border-2 border-amber-300 bg-white p-3">
                  <h2 className="mb-2 text-sm font-semibold">Ke kontrole ({queue.length}): rozpory, nejistá a chybějící povinná pole</h2>
                  {queue.map(({ path, label, f }) => (
                    <div key={path} className="flex flex-wrap items-center gap-2 border-t py-1.5 text-sm first:border-0">
                      <span className={`rounded px-1.5 text-xs font-semibold ${badge(f)}`} title={f.confidence_reasons.join('\n')}>
                        {f.status === 'missing' ? 'chybí' : `${f.status === 'conflict' ? '⚠ ' : ''}${f.confidence}`}
                      </span>
                      <span className="w-48 text-slate-500">{label}</span>
                      {f.status === 'missing'
                        ? <span className="w-48 text-red-700">nenalezeno v dokumentaci</span>
                        : <b className="w-48">{show(path, f.value)}</b>}
                      {f.evidence.map((e, i) => (
                        <button key={i} className="text-xs text-blue-700 underline" onClick={() => setActive(e)}>citace {i + 1}</button>
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

              <div className="grid gap-4 lg:grid-cols-2">
                <section className="rounded-lg border bg-white p-3">
                  <div className="mb-2 flex flex-wrap gap-1">
                    {kase.documents.map((d) => (
                      <button key={d.id} onClick={() => setActive({ doc_id: d.id, quote: '', start: 0, end: 0, verified: false })}
                        className={`rounded px-2 py-0.5 text-xs ${d.id === doc?.id ? 'bg-slate-800 text-white' : 'bg-slate-100'}`}>
                        {d.kind} · {d.filename.replace(/^Rakathon_2026_/, '')}
                      </button>
                    ))}
                  </div>
                  {doc && (
                    <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap text-xs leading-relaxed">
                      {active && active.doc_id === doc.id && active.end > active.start ? (
                        <>
                          {doc.text.slice(0, active.start)}
                          <mark className="bg-amber-200" ref={(el) => el?.scrollIntoView({ block: 'center' })}>{doc.text.slice(active.start, active.end)}</mark>
                          {doc.text.slice(active.end)}
                        </>
                      ) : doc.text}
                    </pre>
                  )}
                </section>

                <section className="rounded-lg border bg-white p-3 text-sm">
                  {SECTIONS.map(([title, fields]) => (
                    <div key={title} className="mb-3">
                      <h3 className="mb-1 text-xs font-semibold uppercase text-slate-500">{title}</h3>
                      {fields.map(([path, label]) => {
                        const f = getField(kase.report, path)
                        const missing = f.status === 'missing'
                        const todo = missing && needsHuman(f) // mandatory and not resolved yet: must not look finished
                        return (
                          <div key={path} className={`flex flex-wrap items-center gap-2 border-b py-1 last:border-0 ${todo ? 'bg-amber-50' : ''}`}>
                            <span className="w-48 text-slate-500">{label}</span>
                            <span className={`flex-1 ${todo ? 'font-medium text-amber-800' : missing || f.review.state === 'rejected' ? 'text-slate-400' : 'font-medium'}`}>
                              {todo ? 'chybí – doplňte, nebo potvrďte, že není'
                                : missing && f.review.state === 'confirmed' ? 'v dokumentaci není (potvrzeno lékařem)'
                                : missing ? 'chybí v dokumentaci' : f.review.state === 'rejected' ? 'zamítnuto' : show(path, f.value)}
                            </span>
                            {todo && <span className={`rounded px-1.5 text-xs font-semibold ${badge(f)}`} title={f.confidence_reasons.join('\n')}>chybí</span>}
                            {!missing && (
                              <span className={`rounded px-1.5 text-xs font-semibold ${badge(f)}`} title={f.confidence_reasons.join('\n')}>{f.confidence}</span>
                            )}
                            <span className="w-16 text-xs text-slate-500">
                              {f.review.state === 'auto_accepted' ? '✓ AI' : f.review.state === 'confirmed' ? '✓ lékař' : f.review.state === 'edited' ? '✎ lékař' : needsHuman(f) ? 'ke kontrole' : ''}
                            </span>
                            {f.evidence[0] && <button className="text-xs text-blue-700 underline" onClick={() => setActive(f.evidence[0])}>zdroj</button>}
                            <RuleCite f={f} />
                          </div>
                        )
                      })}
                    </div>
                  ))}
                </section>
              </div>

              {preview && (
                <section ref={previewRef} className="scroll-mt-4 rounded-lg border-2 border-slate-900 bg-white p-4 text-sm">
                  <div className="mb-2 flex flex-wrap items-center gap-3">
                    <h2 className="font-semibold">Náhled hlášení · {String(preview.formular)} · stav: {String(preview.stav)}</h2>
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
                        <input className="rounded border px-2 py-1" placeholder="Jméno lékaře" value={doctor} onChange={(e) => setDoctor(e.target.value)} />
                        <button className="rounded bg-green-700 px-4 py-1.5 text-white disabled:opacity-40" disabled={!doctor || queue.length > 0 || !!busy}
                          onClick={() => run('Potvrzuji…', () => api.confirm(kase.id, doctor)).then(async (c) => {
                            if (c) { open(c); setPreview(await api.uzisPreview(c.id)) }
                          })}>
                          Potvrdit hlášení
                        </button>
                        {queue.length > 0 ? (
                          <span className="text-xs text-amber-800">Před potvrzením vyřešte {queue.length} polí ke kontrole (nahoře).</span>
                        ) : (
                          <span className="text-xs text-slate-500">Bez potvrzení se nic neexportuje do ÚZIS ani nezapíše do FHIR.</span>
                        )}
                      </>
                    ) : (
                      <>
                        <a className="rounded border px-3 py-1.5" href={api.uzisExportUrl(kase.id)} target="_blank" rel="noreferrer">Export pro ÚZIS (JSON)</a>
                        <button className="rounded bg-slate-900 px-3 py-1.5 text-white disabled:opacity-40" disabled={!health?.fhir || !!busy}
                          onClick={() => run('Zapisuji do IRIS FHIR…', () => api.submit(kase.id)).then((r) => r && setFhirResult(`Zapsáno do FHIR: ${r.entry?.length ?? 0} zdrojů`))}>
                          Uložit do IRIS FHIR
                        </button>
                        {fhirResult && <span className="text-green-700">{fhirResult}</span>}
                      </>
                    )}
                  </div>
                </section>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
