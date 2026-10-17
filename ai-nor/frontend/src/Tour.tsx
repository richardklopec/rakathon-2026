// Product tour "Prezentace" (button with the Play icon in the header): 10 steps across the tabs, each highlights one part of the
// screen with a short text and a "Další" button. The visitor fills in or uploads nothing; it can be replayed any time.
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import type { Case } from './api'
import { Icon } from './icons'
import { caseStatus } from './lib'
import { href, type TabId } from './router'

interface Step {
  tab: TabId
  targets: string[] // data-tour anchors, first one found wins; none found = card in the middle
  title: string
  text: string
  withCase?: boolean // open a case in Vytěžování
}

const STEPS: Step[] = [
  {
    tab: 'domu', targets: [], title: 'Vítejte v AI NOR',
    text: 'AI NOR připraví hlášení incidence zhoubného novotvaru do Národního onkologického registru ze zpráv, které už máte v nemocničním systému. Projdeme spolu celou aplikaci, nic nevyplňujete, stačí klikat na Další.',
  },
  {
    tab: 'domu', targets: ['nav'], title: 'Záložky aplikace',
    text: 'Šest záložek pokrývá celý postup: přehled, seznam hlášení, hlášení relapsu, nový pacient, číselníky a vytěžování. Číslo u Seznamu hlášení ukazuje, kolik hlášení čeká na kontrolu.',
  },
  {
    tab: 'domu', targets: ['pipeline', 'stats'], title: 'Aktuální stav a statistika',
    text: 'Nahoře je aktuální stav hlášení od Nevytěženo po Uloženo ve FHIR, kliknutím se otevře jejich seznam. Pod ním statistika za měsíc, kvartál nebo rok: nová a potvrzená hlášení, hlášení v IRIS FHIR, exporty, průměrná doba do potvrzení a jistota AI, vždy ve srovnání s minulým obdobím.',
  },
  {
    tab: 'novy', targets: ['dropzone'], title: 'Nový pacient',
    text: 'Sem se přetáhnou zprávy jednoho pacienta: PDF i naskenované (přečte je OCR), fotografie, Word nebo e-mail s přílohami. Zprávy z nemocničního systému chodí přes InterSystems IRIS samy a načtou se jedním kliknutím. AI z nich vytěží pole hlášení a u každého uvede doslovnou citaci.',
  },
  {
    tab: 'vytezovani', withCase: true, targets: ['evidence'], title: 'Citace a jistota AI',
    text: 'Vlevo je zpráva, vpravo pole formuláře NOR. Číslo u pole je jistota AI 0–100 a odkaz Zdroj zvýrazní přesné místo ve zprávě. Pole s jistotou 80 a víc bez rozporu jsou předvyplněná.',
  },
  {
    tab: 'vytezovani', withCase: true, targets: ['queue', 'evidence'], title: 'Lékař řeší jen to podstatné',
    text: 'Do bloku Ke kontrole jdou jen rozpory mezi zprávami, nejistá pole a chybějící povinné údaje. Lékař hodnotu potvrdí, opraví nebo zamítne, pak otevře náhled ve tvaru formuláře ÚZIS a hlášení potvrdí.',
  },
  {
    tab: 'vytezovani', withCase: true, targets: ['audit'], title: 'Historie změn v InterSystems IRIS',
    text: 'Každá změna se zapíše: kdo, kdy, které pole, původní a nová hodnota. Záznamy se ukládají do databáze InterSystems IRIS (tabulka Nor.Audit), vedle hlášení samotných a jejich záznamu ve FHIR serveru.',
  },
  {
    tab: 'hlaseni', targets: ['cases'], title: 'Seznam hlášení',
    text: 'Všechna hlášení v jedné tabulce s hledáním, filtrem podle stavu a řazením. Potvrzená hlášení zaškrtnete a hromadně exportujete do CSV nebo JSON, nebo odešlete do IRIS FHIR. Ikonka ve sloupci Export ukazuje, co už odešlo.',
  },
  {
    tab: 'relaps', targets: ['relapse'], title: 'Hlášení relapsu',
    text: 'K potvrzenému hlášení zapíše lékař recidivu nebo progresi s datem a lokalizacemi metastáz. Kód pro NOR se spočítá sám a hlášení se znovu potvrdí.',
  },
  {
    tab: 'ciselniky', targets: ['codelists'], title: 'Číselníky a nápověda',
    text: 'Číselníky MKN-10, topografie a morfologie od ÚZIS: AI smí vybrat jen kód, který v nich je. Návod pro obsluhu najdete pod tlačítkem Dokumentace a tuto prezentaci spustíte znovu tlačítkem Prezentace.',
  },
]

type Rect = { top: number; left: number; width: number; height: number }
const PAD = 8

/** The case shown in steps 5-7: one waiting for review, else any extracted one, else the first. */
function demoCase(cases: Case[]): string | null {
  return (cases.find((c) => caseStatus(c) === 'kontrola') ?? cases.find((c) => caseStatus(c) !== 'nevytezeno') ?? cases[0])?.id ?? null
}

export default function Tour({ cases, onClose }: { cases: Case[]; onClose: () => void }) {
  const [i, setI] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const [readyStep, setReadyStep] = useState(-1) // step whose target is looked up and measured (the card waits for it)
  const startHash = useRef(location.hash)
  const caseId = useRef(demoCase(cases))
  const target = useRef<Element | null>(null)
  const next = useRef<HTMLButtonElement>(null)
  const step = STEPS[i]
  const last = i === STEPS.length - 1
  const ready = readyStep === i

  const close = useCallback(() => {
    location.hash = startHash.current || href('domu')
    onClose()
  }, [onClose])

  const measure = useCallback(() => {
    const el = target.current
    if (!el) return setRect(null)
    const r = el.getBoundingClientRect()
    setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD })
  }, [])

  // go to the step's tab, wait for its anchor (screens load data first), scroll it into view
  useEffect(() => {
    const want = href(step.tab, step.withCase ? caseId.current : null)
    if (location.hash !== want) location.hash = want
    let alive = true
    let tries = 0
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const look = () => {
      if (!alive) return
      const el = step.targets.map((t) => document.querySelector(`[data-tour="${t}"]`)).find((e) => e && e.getBoundingClientRect().height > 0)
      if (el || tries++ > 25 || !step.targets.length) {
        target.current = el ?? null
        if (el) {
          const r = el.getBoundingClientRect()
          // tall areas: show their top part; small ones: center them
          el.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? 'start' : 'center', behavior: reduce ? 'auto' : 'smooth' })
        }
        setTimeout(() => { if (alive) { measure(); setReadyStep(i) } }, el && !reduce ? 350 : 0)
        return
      }
      setTimeout(look, 100)
    }
    look()
    return () => { alive = false }
  }, [i, step, measure])

  useEffect(() => {
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => { window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true) }
  }, [measure])

  useEffect(() => {
    if (ready) next.current?.focus({ preventScroll: true })
  }, [ready])

  const advance = useCallback(() => (last ? close() : setI((n) => n + 1)), [last, close])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowRight') advance()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, advance])

  // card under the highlighted area when there is room, otherwise above it; centred without a target; docked on phones
  const vw = window.innerWidth
  const vh = window.innerHeight
  const cardW = Math.min(380, vw - 32)
  const phone = vw < 640
  let cardStyle: CSSProperties
  if (phone) cardStyle = { left: 16, right: 16, bottom: 16 }
  else if (!rect) cardStyle = { left: (vw - cardW) / 2, top: vh / 2 - 110, width: cardW }
  else {
    const left = Math.min(Math.max(16, rect.left), vw - cardW - 16)
    const below = rect.top + rect.height + 12
    cardStyle = below + 230 < vh
      ? { left, top: below, width: cardW }
      : rect.top - 12 > 230
        ? { left, bottom: vh - rect.top + 12, width: cardW }
        : { left: vw - cardW - 24, bottom: 24, width: cardW } // huge target: corner
  }

  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* covers the page so it can't be changed during the tour */}
      <div className="absolute inset-0" />
      <div
        className={`pointer-events-none fixed rounded-lg transition-all duration-300 ease-out motion-reduce:transition-none ${rect ? 'outline-2 outline-fno-sky' : ''}`}
        style={{
          ...(rect ? { top: rect.top, left: rect.left, width: rect.width, height: rect.height } : { top: vh / 2, left: vw / 2, width: 0, height: 0 }),
          boxShadow: '0 0 0 9999px rgba(1, 28, 62, 0.55)', // dims everything but the highlighted area
        }}
      />
      <div
        className={`fixed rounded-xl border border-fno-200 bg-white p-5 shadow-[0_12px_32px_rgba(1,28,62,0.28)] transition-opacity duration-200 ${ready ? 'opacity-100' : 'opacity-0'}`}
        style={cardStyle}
      >
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-semibold tabular-nums text-fno-700" aria-label={`Krok ${i + 1} z ${STEPS.length}`}>{i + 1}/{STEPS.length}</span>
          <button onClick={close} className="-mr-1 rounded p-1 text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-800" aria-label="Ukončit prezentaci">
            <Icon.x width={16} height={16} />
          </button>
        </div>
        <div className="mt-1.5 flex gap-1" aria-hidden="true">
          {STEPS.map((_, n) => (
            <span key={n} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${n <= i ? 'bg-fno-800' : 'bg-fno-100'}`} />
          ))}
        </div>
        <h2 id="tour-title" className="mt-4 text-base font-semibold text-fno-950">{step.title}</h2>
        <p className="mt-1.5 text-sm leading-relaxed text-slate-700" aria-live="polite">{step.text}</p>
        <div className="mt-5 flex items-center justify-between gap-3">
          <button onClick={close} className="text-sm text-slate-600 underline-offset-2 hover:text-slate-900 hover:underline">Ukončit</button>
          <button ref={next} onClick={advance}
            className="inline-flex items-center gap-1.5 rounded-md bg-fno-800 px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-fno-700 active:bg-fno-900">
            {last ? 'Dokončit' : 'Další'}
            {!last && <Icon.chevron width={16} height={16} />}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
