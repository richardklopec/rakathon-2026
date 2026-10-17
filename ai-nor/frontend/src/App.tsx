// App shell: header with the NOR logo, tab navigation and the shared data (cases, code lists, system status).
// Screens live in src/screens; routing is the URL hash (src/router.ts).
import { useCallback, useEffect, useState, type ReactElement, type SVGProps } from 'react'
import { api, type Case, type Codelists } from './api'
import logo from './assets/logo-nor.png'
import Docs from './Docs'
import { href, useRoute, type TabId } from './router'
import CaseList from './screens/CaseList'
import CodeLists from './screens/CodeLists'
import Extraction from './screens/Extraction'
import Home from './screens/Home'
import NewPatient from './screens/NewPatient'
import Relapse from './screens/Relapse'
import { Icon } from './icons'
import { caseStatus } from './lib'

const TABS: { id: TabId; label: string; icon: (p: SVGProps<SVGSVGElement>) => ReactElement }[] = [
  { id: 'domu', label: 'Domů', icon: Icon.home },
  { id: 'hlaseni', label: 'Seznam hlášení', icon: Icon.list },
  { id: 'relaps', label: 'Hlášení relapsu', icon: Icon.relapse },
  { id: 'novy', label: 'Nový pacient', icon: Icon.userPlus },
  { id: 'ciselniky', label: 'Číselníky', icon: Icon.book },
  { id: 'vytezovani', label: 'Vytěžování', icon: Icon.extract },
]

export default function App() {
  const route = useRoute()
  // undefined = still asking (the FHIR probe can take a few seconds), null = backend not reachable
  const [health, setHealth] = useState<{ llm_mode: string; fhir: boolean } | null | undefined>(undefined)
  const [cases, setCases] = useState<Case[]>([])
  const [lists, setLists] = useState<Codelists | null>(null)

  const refresh = useCallback(() => { api.cases().then(setCases).catch(() => {}) }, [])
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api.codelists().then(setLists).catch(() => setLists(null))
    refresh()
  }, [refresh])

  const toReview = cases.filter((c) => caseStatus(c) === 'kontrola').length

  return (
    <div className="min-h-screen bg-canvas text-slate-900">
      <header className="bg-white">
        <div className="mx-auto flex max-w-[1440px] items-center gap-4 px-4 py-2.5 sm:px-6">
          <a href={href('domu')} className="flex shrink-0 items-center gap-4" aria-label="AI NOR, domů">
            <img src={logo} alt="NOR" className="h-10 w-auto sm:h-11" />
            <span className="hidden border-l border-slate-200 pl-4 sm:block">
              <span className="block text-sm font-semibold leading-tight text-fno-900">Hlášení novotvarů do NOR</span>
              <span className="block text-xs leading-tight text-slate-600">Fakultní nemocnice Ostrava · AI asistent</span>
            </span>
          </a>
          <span className="flex-1" />
          <div className="hidden items-center gap-3 text-xs text-slate-600 md:flex" aria-label="Stav systému">
            <Status ok={health === undefined ? undefined : health?.llm_mode === 'live'}
              label={`AI: ${health === undefined ? 'zjišťuji…' : health ? (health.llm_mode === 'live' ? 'ostrý provoz' : 'zkušební režim') : 'backend nedostupný'}`} />
            <Status ok={health === undefined ? undefined : !!health?.fhir} label={`IRIS FHIR: ${health === undefined ? 'zjišťuji…' : health?.fhir ? 'připojeno' : 'offline'}`} />
          </div>
          <a href={href('dokumentace')} aria-current={route.tab === 'dokumentace' ? 'page' : undefined}
            className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors duration-150 ${route.tab === 'dokumentace' ? 'border-fno-800 bg-fno-800 text-white' : 'border-slate-300 text-fno-900 hover:border-fno-600 hover:bg-fno-50'}`}>
            <Icon.docs width={16} height={16} />Dokumentace
          </a>
        </div>
        <nav aria-label="Hlavní navigace" className="bg-fno-800">
          <ul className="mx-auto flex max-w-[1440px] overflow-x-auto px-2 sm:px-4">
            {TABS.map(({ id, label, icon: I }) => {
              const on = route.tab === id
              return (
                <li key={id} className="shrink-0">
                  <a href={href(id)} aria-current={on ? 'page' : undefined}
                    className={`relative flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors duration-150 ${on ? 'bg-fno-900 text-white' : 'text-fno-100 hover:bg-fno-700 hover:text-white'}`}>
                    <I width={17} height={17} />
                    {label}
                    {id === 'hlaseni' && toReview > 0 && (
                      <span className="rounded-full bg-amber-400 px-1.5 text-[11px] font-semibold tabular-nums text-amber-950" title="Hlášení ke kontrole">{toReview}</span>
                    )}
                    <span className={`absolute inset-x-0 bottom-0 h-[3px] transition-colors duration-150 ${on ? 'bg-fno-sky' : 'bg-transparent'}`} />
                  </a>
                </li>
              )
            })}
          </ul>
        </nav>
      </header>

      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
        {route.tab === 'domu' && <Home cases={cases} lists={lists} health={health} />}
        {route.tab === 'hlaseni' && <CaseList cases={cases} lists={lists} status={route.query.get('stav')} />}
        {route.tab === 'relaps' && <Relapse key={route.id ?? ''} caseId={route.id} cases={cases} lists={lists} onChanged={refresh} />}
        {route.tab === 'novy' && <NewPatient onCreated={refresh} />}
        {route.tab === 'ciselniky' && <CodeLists lists={lists} active={route.id} />}
        {route.tab === 'vytezovani' && <Extraction caseId={route.id} cases={cases} lists={lists} fhirUp={!!health?.fhir} onChanged={refresh} />}
        {route.tab === 'dokumentace' && <Docs />}
      </main>
    </div>
  )
}

function Status({ ok, label }: { ok: boolean | undefined; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className={`size-2 rounded-full ${ok === undefined ? 'bg-slate-300' : ok ? 'bg-emerald-500' : 'bg-amber-500'}`} />
      {label}
    </span>
  )
}
