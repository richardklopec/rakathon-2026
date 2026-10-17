// "Zprávy z NIS": reports the hospital information system stored in IRIS FHIR for AI NOR (GET /api/nis/inbox).
// One click imports a patient's reports as a case and (optionally) runs the extraction, like an upload.
import { useCallback, useEffect, useState } from 'react'
import { api, type NisPatient } from '../api'
import { Icon } from '../icons'
import { btn, formatDate, panel } from '../lib'
import { go } from '../router'
import { Notice } from '../ui'

export default function NisInbox({ extract, onCreated, disabled }: { extract: boolean; onCreated: () => void; disabled: boolean }) {
  const [inbox, setInbox] = useState<{ iris: boolean; patients: NisPatient[] } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.nisInbox().then(setInbox).catch((e) => setError(String(e instanceof Error ? e.message : e)))
  }, [])
  useEffect(() => { load() }, [load])

  async function take(p: NisPatient) {
    setError(null)
    try {
      setBusy(`${p.patient}: načítám zprávy z NIS…`)
      const created = await api.nisImport(p.patient, p.documents.map((d) => d.id))
      onCreated()
      if (extract) {
        setBusy(`${p.patient}: AI vytěžuje hlášení…`)
        await api.extract(created.id)
        onCreated()
      }
      go('vytezovani', created.id)
    } catch (e) {
      setError(String(e instanceof Error ? e.message.replace(/^\d+: /, '') : e))
      setBusy(null)
      load()
    }
  }

  return (
    <section className={`${panel} p-4`} aria-labelledby="nis-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="nis-title" className="flex items-center gap-2 text-sm font-semibold text-fno-950">
          <Icon.database width={16} height={16} className="text-fno-700" />
          Zprávy z NIS přes InterSystems IRIS
        </h2>
        {inbox?.iris && <button className={btn.ghost} onClick={load} disabled={!!busy}>Obnovit</button>}
      </div>

      {!inbox && !error && <p className="mt-2 text-sm text-slate-600">Zjišťuji, co poslal NIS…</p>}
      {inbox && !inbox.iris && (
        <p className="mt-2 text-sm text-slate-600">
          IRIS FHIR teď neběží. Jakmile poběží, objeví se tu nové zprávy, které nemocniční systém poslal pro AI NOR, a načtete je jedním kliknutím, bez nahrávání souborů.
        </p>
      )}
      {inbox?.iris && inbox.patients.length === 0 && (
        <p className="mt-2 text-sm text-slate-600">Z NIS nečekají žádné nové zprávy.</p>
      )}

      {inbox?.iris && inbox.patients.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 rounded-md border border-slate-200">
          {inbox.patients.map((p) => (
            <li key={p.patient} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-slate-900">{p.patient}</span>
                <span className="block truncate text-xs text-slate-600" title={p.documents.map((d) => d.title).join(', ')}>
                  {p.documents.length} {p.documents.length === 1 ? 'zpráva' : p.documents.length < 5 ? 'zprávy' : 'zpráv'}:{' '}
                  {p.documents.map((d) => d.kind ?? d.title).join(', ')}
                  {p.documents[0]?.date && <> · {formatDate(p.documents[p.documents.length - 1].date)}</>}
                </span>
              </span>
              <button className={btn.secondary} disabled={!!busy || disabled} onClick={() => take(p)}>
                <Icon.download width={16} height={16} />{extract ? 'Načíst a vytěžit' : 'Načíst'}
              </button>
            </li>
          ))}
        </ul>
      )}
      {busy && <p className="mt-2 text-sm text-fno-900" aria-live="polite">{busy}</p>}
      {error && <div className="mt-2"><Notice tone="error">{error}</Notice></div>}
    </section>
  )
}
