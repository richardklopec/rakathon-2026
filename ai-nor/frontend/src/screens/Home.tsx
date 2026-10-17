// Tab "Domů": where the reports are in the workflow and what is waiting for the clinician.
import type { Case, Codelists } from '../api'
import { href } from '../router'
import { Icon } from '../icons'
import { PageHeader, ScoreBadge, StatusBadge } from '../ui'
import { STATUS, STATUS_ORDER, btn, caseStatus, pendingCount, diagnosis, formatDate, panel, patientName } from '../lib'

export default function Home({ cases, lists, health }: {
  cases: Case[]
  lists: Codelists | null
  health: { llm_mode: string; fhir: boolean } | null | undefined // undefined = still asking
}) {
  const counts = Object.fromEntries(STATUS_ORDER.map((s) => [s, cases.filter((c) => caseStatus(c) === s).length]))
  const waiting = cases.filter((c) => caseStatus(c) === 'kontrola').sort((a, b) => pendingCount(b) - pendingCount(a))
  const ready = cases.filter((c) => caseStatus(c) === 'potvrzeni')
  const recent = [...cases].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 6)

  return (
    <>
      <PageHeader title="Přehled hlášení"
        actions={<a href={href('novy')} className={btn.primary}><Icon.userPlus width={16} height={16} />Nový pacient</a>}>
        Hlášení incidence zhoubného novotvaru do NOR. AI připraví hlášení ze zpráv pacienta, vy řešíte jen rozpory a nejistá pole.
      </PageHeader>

      <nav aria-label="Stav hlášení" className={`${panel} mb-6 grid grid-cols-2 overflow-hidden sm:grid-cols-5`}>
        {STATUS_ORDER.map((s, i) => (
          <a key={s} href={href('hlaseni', null, { stav: s })} title={STATUS[s].hint}
            className={`group relative flex flex-col gap-1 border-slate-200 px-4 py-3 transition-colors duration-150 hover:bg-fno-50 ${i > 0 ? 'sm:border-l' : ''} ${i % 2 ? 'border-l' : ''} ${i > 1 ? 'border-t sm:border-t-0' : ''}`}>
            <span className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
              <span className={`size-2 rounded-full ${s === 'fhir' ? 'bg-fno-800' : STATUS[s].dot}`} />
              {STATUS[s].label}
            </span>
            <span className="text-2xl font-semibold tabular-nums text-fno-950">{counts[s]}</span>
            {i < STATUS_ORDER.length - 1 && (
              <Icon.chevron width={14} height={14} className="absolute right-1 top-1/2 hidden -translate-y-1/2 text-slate-300 sm:block" />
            )}
          </a>
        ))}
      </nav>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <section>
            <h2 className="mb-2 text-base font-semibold text-fno-950">Čeká na vaši kontrolu</h2>
            {waiting.length + ready.length === 0 ? (
              <p className={`${panel} px-4 py-5 text-sm text-slate-600`}>
                Nic nečeká. Až nahrajete zprávy nového pacienta, AI hlášení vytěží a pole, o kterých si není jistá, se objeví tady.
              </p>
            ) : (
              <ul className={`${panel} divide-y divide-slate-100`}>
                {[...waiting, ...ready].map((c) => <CaseRow key={c.id} c={c} lists={lists} />)}
              </ul>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="text-base font-semibold text-fno-950">Naposledy upravené</h2>
              {cases.length > 0 && <a href={href('hlaseni')} className={btn.ghost}>Všechna hlášení<Icon.chevron width={14} height={14} /></a>}
            </div>
            {recent.length === 0 ? (
              <p className={`${panel} px-4 py-5 text-sm text-slate-600`}>Zatím tu nejsou žádná hlášení.</p>
            ) : (
              <ul className={`${panel} divide-y divide-slate-100`}>
                {recent.map((c) => <CaseRow key={c.id} c={c} lists={lists} showDate />)}
              </ul>
            )}
          </section>
        </div>

        <aside className="space-y-6">
          <section>
            <h2 className="mb-2 text-base font-semibold text-fno-950">Stav systému</h2>
            <dl className={`${panel} divide-y divide-slate-100 text-sm`}>
              <SystemRow ok={health === undefined ? undefined : health?.llm_mode === 'live'} label="Jazykový model"
                value={health === undefined ? 'zjišťuji…' : health ? (health.llm_mode === 'live' ? 'ostrý provoz (EU)' : 'zkušební režim bez AI') : 'backend nedostupný'} />
              <SystemRow ok={health === undefined ? undefined : !!health?.fhir} label="IRIS FHIR" value={health === undefined ? 'zjišťuji…' : health?.fhir ? 'připojeno' : 'nepřipojeno'} />
              <SystemRow ok={!!lists?.icd10?.length} label="Číselník MKN-10" value={lists ? `${lists.icd10?.length ?? 0} kódů novotvarů` : 'nenačteno'} />
              <SystemRow ok={!!lists?.morphology_code?.length} label="Morfologie MKN-O-3" value={lists ? `${lists.morphology_code?.length ?? 0} kódů` : 'nenačteno'} />
            </dl>
          </section>
          <section className="rounded-lg border border-fno-200 bg-fno-50 p-4 text-sm text-fno-950">
            <h2 className="font-semibold">Jak to funguje</h2>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-fno-900">
              <li>Nahrajte zprávy pacienta v záložce Nový pacient.</li>
              <li>AI vytěží pole hlášení a u každého uvede citaci a jistotu.</li>
              <li>Ve Vytěžování vyřešte rozpory a nejistá pole.</li>
              <li>Zkontrolujte náhled formuláře a hlášení potvrďte.</li>
            </ol>
            <a href={href('dokumentace')} className="mt-3 inline-flex items-center gap-1 font-medium text-fno-800 underline underline-offset-2 hover:text-fno-950">Návod pro obsluhu</a>
          </section>
        </aside>
      </div>
    </>
  )
}

function CaseRow({ c, lists, showDate }: { c: Case; lists: Codelists | null; showDate?: boolean }) {
  const dg = diagnosis(c, lists)
  return (
    <li>
      <a href={href('vytezovani', c.id)} className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors duration-150 hover:bg-fno-50">
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium text-slate-900">{patientName(c)}</span>
          <span className="block truncate text-xs text-slate-600">
            {dg.code ? <><b className="font-semibold text-slate-700">{dg.code}</b> {dg.name}</> : 'diagnóza zatím neurčena'}
          </span>
        </span>
        {showDate ? <span className="hidden text-xs text-slate-500 sm:block">{formatDate(c.updated_at)}</span>
          : caseStatus(c) === 'kontrola' && <span className="hidden text-xs text-amber-800 sm:block">{pendingCount(c)} ke kontrole</span>}
        <span className="hidden sm:block"><ScoreBadge score={c.ai_confidence?.score} /></span>
        <StatusBadge c={c} />
        <Icon.chevron width={16} height={16} className="hidden shrink-0 text-slate-400 sm:block" />
      </a>
    </li>
  )
}

function SystemRow({ ok, label, value }: { ok: boolean | undefined; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5">
      <dt className="text-slate-600">{label}</dt>
      <dd className="flex items-center gap-1.5 text-right font-medium text-slate-900">
        <span className={`size-2 rounded-full ${ok === undefined ? 'bg-slate-300' : ok ? 'bg-emerald-500' : 'bg-amber-500'}`} />
        {value}
      </dd>
    </div>
  )
}
