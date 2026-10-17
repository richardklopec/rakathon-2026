// "Historie změn" of one case: who changed which field, when, old -> new (GET /api/cases/{id}/audit, IRIS Nor.Audit).
import { useEffect, useState } from 'react'
import { api, type AuditEntry } from '../api'
import { Icon } from '../icons'
import { panel } from '../lib'

const KIND: Record<string, [string, string]> = {
  filled: ['Doplnění', 'bg-emerald-500'],
  changed: ['Přepsání', 'bg-fno-sky'],
  resolved: ['Vyřešení rozporu', 'bg-violet-500'],
  confirmed: ['Potvrzení hodnoty', 'bg-emerald-500'],
  confirmed_missing: ['Potvrzeno: v dokumentaci není', 'bg-slate-400'],
  rejected: ['Zamítnutí', 'bg-red-500'],
  removed: ['Odebrání', 'bg-red-500'],
  case_created: ['Založení případu', 'bg-fno-800'],
  extracted: ['Vytěžení AI', 'bg-fno-800'],
  patient_changed: ['Změna pacienta', 'bg-fno-sky'],
  report_confirmed: ['Potvrzení hlášení', 'bg-emerald-600'],
  fhir_submitted: ['Zápis do IRIS FHIR', 'bg-fno-800'],
  fhir_failed: ['Zápis do IRIS FHIR se nepovedl', 'bg-amber-500'],
}
const SHOWN = 8

const records = (n: number) => `${n} ${n === 1 ? 'záznam' : n < 5 ? 'záznamy' : 'záznamů'}`
const time = (iso: string) => new Date(iso).toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })

/** `stamp` changes whenever the case was saved, so the log reloads after every change. */
export default function AuditLog({ caseId, stamp }: { caseId: string; stamp: string }) {
  const [log, setLog] = useState<{ iris: boolean; entries: AuditEntry[] } | null>(null)
  const [failed, setFailed] = useState(false)
  const [all, setAll] = useState(false)

  useEffect(() => {
    let alive = true
    api.audit(caseId)
      .then((l) => { if (alive) { setLog(l); setFailed(false) } })
      .catch(() => { if (alive) setFailed(true) })
    return () => { alive = false }
  }, [caseId, stamp])

  const entries = [...(log?.entries ?? [])].reverse() // newest first
  const shown = all ? entries : entries.slice(0, SHOWN)
  const waiting = entries.filter((e) => e.storage === 'local').length

  return (
    <section className={`${panel} p-4`} data-tour="audit">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fno-950">
          <Icon.history width={16} height={16} className="text-fno-700" />
          Historie změn {log && <span className="font-normal tabular-nums text-slate-500">({entries.length})</span>}
        </h2>
        {log && (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-600" title="Tabulka Nor.Audit v namespace FHIRSERVER">
            <Icon.database width={14} height={14} className={log.iris ? 'text-emerald-700' : 'text-amber-600'} />
            {log.iris
              ? 'Ukládá se do InterSystems IRIS (Nor.Audit)'
              : `IRIS nedostupný: ${waiting ? `${records(waiting)} ${waiting === 1 ? 'čeká' : 'čekají'} v lokální záloze` : 'záznamy se ukládají do lokální zálohy'} a přesunou se do IRIS`}
          </span>
        )}
      </div>

      {failed && <p className="text-sm text-red-700">Historii se nepodařilo načíst.</p>}
      {log && entries.length === 0 && (
        <p className="text-sm text-slate-600">Zatím žádné změny. Každé doplnění, přepsání, potvrzení nebo zamítnutí pole se tu zapíše i se jménem uživatele.</p>
      )}

      {shown.length > 0 && (
        <ol className="space-y-0">
          {shown.map((e) => {
            const [kind, dot] = KIND[e.kind] ?? [e.kind, 'bg-slate-400']
            return (
              <li key={e.id} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 border-t border-slate-100 py-2 text-sm first:border-0 sm:grid-cols-[150px_minmax(0,1fr)_auto]">
                <span className="text-xs tabular-nums text-slate-500 sm:pt-0.5">{time(e.at)}</span>
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-x-2">
                    <span className={`size-2 shrink-0 rounded-full ${dot}`} />
                    <b className="font-medium text-slate-900">{kind}</b>
                    {e.label && <span className="text-slate-700">· {e.label}</span>}
                  </span>
                  {(e.old != null || e.new != null) && (
                    <span className="mt-0.5 block break-words pl-4 text-xs text-slate-600">
                      {e.old != null && <span className="text-slate-500 line-through decoration-slate-400">{e.old}</span>}
                      {e.old != null && e.new != null && <span aria-hidden="true"> → </span>}
                      {e.new != null && <span className="font-medium text-slate-800">{e.new}</span>}
                    </span>
                  )}
                </span>
                <span className="col-start-2 pl-4 text-xs text-slate-600 sm:col-start-3 sm:pl-0 sm:text-right">
                  {e.actor}
                  {e.storage === 'local' && <span className="ml-1 text-amber-700" title="Uloženo v lokální záloze, do IRIS se přesune po připojení">· čeká na IRIS</span>}
                </span>
              </li>
            )
          })}
        </ol>
      )}

      {entries.length > SHOWN && (
        <button className="mt-2 text-sm font-medium text-fno-800 underline underline-offset-2 hover:text-fno-950" onClick={() => setAll(!all)}>
          {all ? 'Zobrazit jen posledních' : `Zobrazit všech ${records(entries.length)}`}
        </button>
      )}
    </section>
  )
}
