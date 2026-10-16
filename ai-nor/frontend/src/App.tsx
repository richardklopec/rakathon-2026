import { useEffect, useMemo, useState } from 'react'
import { api, type Case, type Evidence, type Extracted, type NorReport } from './api'

// Fields shown in the review panel, in NOR form order. Path = key in NorReport (dot for TNM parts).
const FIELDS: [string, string][] = [
  ['diagnosis_date', 'Datum stanovení dg.'],
  ['icd10', 'Dg. MKN-10'],
  ['topography', 'Topografie'],
  ['laterality', 'Lateralita'],
  ['morphology_code', 'Kód morfologie'],
  ['morphology_name', 'Název morfologie'],
  ['grade', 'Grading'],
  ['tnm_clinical.t', 'cT'],
  ['tnm_clinical.n', 'cN'],
  ['tnm_clinical.m', 'cM'],
  ['tnm_pathological.t', 'pT'],
  ['tnm_pathological.n', 'pN'],
  ['tnm_pathological.m', 'pM'],
  ['clinical_stage', 'Klinické stádium'],
  ['disease_extent', 'Onemocnění'],
]

function getField(report: NorReport, path: string): Extracted {
  const [a, b] = path.split('.')
  const top = report[a as keyof NorReport] as unknown as Record<string, Extracted>
  return (b ? top[b] : top) as Extracted
}

function show(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object' && 'year' in (v as object)) {
    const d = v as { year: number; month?: number; day?: number }
    return [d.day, d.month, d.year].filter(Boolean).join('. ')
  }
  return Array.isArray(v) ? v.join(', ') : String(v)
}

export default function App() {
  const [health, setHealth] = useState<{ llm_mode: string; fhir: boolean } | null>(null)
  const [kase, setCase] = useState<Case | null>(null)
  const [active, setActive] = useState<Evidence | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  async function run<T>(fn: () => Promise<T>) {
    setBusy(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(files: FileList | null) {
    if (!files?.length) return
    const created = await run(() => api.createCase([...files]))
    if (created) setCase((await run(() => api.extract(created.id))) ?? created)
  }

  async function setReview(path: string, state: 'confirmed' | 'rejected') {
    if (!kase) return
    const report = structuredClone(kase.report)
    getField(report, path).review.state = state
    const saved = await run(() => api.saveReport(kase.id, report))
    if (saved) setCase(saved)
  }

  const doc = useMemo(
    () => kase?.documents.find((d) => d.id === active?.doc_id) ?? kase?.documents[0],
    [kase, active],
  )

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between border-b bg-white px-6 py-3">
        <h1 className="text-lg font-semibold">AI NOR · hlášení novotvaru</h1>
        <div className="text-sm text-slate-500">
          LLM: {health?.llm_mode ?? '?'} · IRIS FHIR: {health?.fhir ? 'online' : 'offline'}
        </div>
      </header>

      <main className="grid gap-4 p-6 lg:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <label className="mb-3 block text-sm font-medium">
            Zdravotnická dokumentace (PDF, TXT, XLSX)
            <input
              type="file"
              multiple
              accept=".pdf,.txt,.md,.xlsx"
              className="mt-1 block w-full text-sm"
              onChange={(e) => onUpload(e.target.files)}
              disabled={busy}
            />
          </label>
          {kase && (
            <>
              <div className="mb-2 flex flex-wrap gap-2">
                {kase.documents.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setActive({ doc_id: d.id, quote: '', start: 0, end: 0 })}
                    className={`rounded px-2 py-1 text-xs ${d.id === doc?.id ? 'bg-slate-800 text-white' : 'bg-slate-100'}`}
                  >
                    {d.kind} · {d.filename}
                  </button>
                ))}
              </div>
              {doc && (
                <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap text-sm leading-relaxed">
                  {active && active.doc_id === doc.id && active.end > active.start ? (
                    <>
                      {doc.text.slice(0, active.start)}
                      <mark className="bg-amber-200">{doc.text.slice(active.start, active.end)}</mark>
                      {doc.text.slice(active.end)}
                    </>
                  ) : (
                    doc.text
                  )}
                </pre>
              )}
            </>
          )}
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-medium">Pole hlášení NOR</h2>
          {!kase && <p className="text-sm text-slate-500">Nahrajte dokumenty pacienta.</p>}
          {kase && (
            <table className="w-full text-sm">
              <tbody>
                {FIELDS.map(([path, label]) => {
                  const f = getField(kase.report, path)
                  return (
                    <tr key={path} className="border-b last:border-0">
                      <td className="py-2 pr-2 text-slate-500">{label}</td>
                      <td className="py-2 pr-2 font-medium">
                        {f.status === 'missing' ? <span className="text-slate-400">chybí</span> : show(f.value)}
                      </td>
                      <td className="py-2 pr-2">
                        {f.evidence[0] && (
                          <button className="text-xs text-blue-700 underline" onClick={() => setActive(f.evidence[0])}>
                            zdroj
                          </button>
                        )}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        {f.status !== 'missing' && (
                          <>
                            <button
                              className={`mr-1 rounded px-2 text-xs ${f.review.state === 'confirmed' ? 'bg-green-600 text-white' : 'bg-slate-100'}`}
                              onClick={() => setReview(path, 'confirmed')}
                            >
                              ✓
                            </button>
                            <button
                              className={`rounded px-2 text-xs ${f.review.state === 'rejected' ? 'bg-red-600 text-white' : 'bg-slate-100'}`}
                              onClick={() => setReview(path, 'rejected')}
                            >
                              ✗
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
          {kase && (
            <button
              className="mt-4 rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
              disabled={busy || !health?.fhir}
              onClick={() => run(() => api.submit(kase.id))}
            >
              Odeslat potvrzené do IRIS FHIR
            </button>
          )}
          {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
        </section>
      </main>
    </div>
  )
}
