// Tab "Nový pacient": upload the patient's reports, optionally run the AI extraction, then open the case for review.
import { useRef, useState, type DragEvent } from 'react'
import { api } from '../api'
import { go } from '../router'
import { Icon } from '../icons'
import { Notice, PageHeader } from '../ui'
import { btn, input, panel } from '../lib'

const ACCEPT = ['.pdf', '.txt', '.md', '.xlsx']

// same rules as backend ingest.guess_kind (only a hint for the user, the backend decides)
const KINDS: [RegExp, string][] = [
  [/histolog/, 'Histologie'],
  [/^pz|propoust/, 'Propouštěcí zpráva'],
  [/^az|ambulant/, 'Ambulantní zpráva'],
  [/^kz|mdt/, 'MDT'],
  [/operac/, 'Operační protokol'],
]
const guessKind = (name: string) => {
  const n = name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  return n.endsWith('.xlsx') ? 'Export z NIS (více zpráv)' : KINDS.find(([re]) => re.test(n))?.[1] ?? 'Jiná zpráva'
}
const size = (b: number) => (b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} kB` : `${(b / 1024 / 1024).toFixed(1)} MB`)

type Step = 'idle' | 'upload' | 'extract'

export default function NewPatient({ onCreated }: { onCreated: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [ref, setRef] = useState('')
  const [extract, setExtract] = useState(true)
  const [step, setStep] = useState<Step>('idle')
  const [error, setError] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const picker = useRef<HTMLInputElement>(null)

  function add(list: FileList | null) {
    if (!list) return
    const ok = [...list].filter((f) => ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext)))
    const skipped = list.length - ok.length
    setError(skipped ? `${skipped} ${skipped === 1 ? 'soubor nemá' : 'soubory nemají'} podporovaný formát (PDF, TXT, XLSX), vynechávám.` : null)
    setFiles((prev) => [...prev, ...ok.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size))])
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDrag(false)
    add(e.dataTransfer.files)
  }

  async function submit() {
    setError(null)
    try {
      setStep('upload')
      const created = await api.createCase(files, ref.trim() || undefined)
      onCreated()
      if (extract) {
        setStep('extract')
        await api.extract(created.id)
        onCreated()
      }
      go('vytezovani', created.id)
    } catch (e) {
      setError(String(e instanceof Error ? e.message.replace(/^\d+: /, '') : e))
      setStep('idle')
    }
  }

  const busy = step !== 'idle'

  return (
    <>
      <PageHeader title="Nový pacient">
        Nahrajte všechny zprávy jednoho pacienta najednou: ambulantní a propouštěcí zprávy, histologie, zápisy z MDT, operační protokoly.
        AI z nich připraví hlášení incidence a u každého údaje uvede, odkud ho vzala.
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
            className={`flex flex-col items-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors duration-150 ${drag ? 'border-fno-sky bg-fno-sky-soft' : 'border-slate-300 bg-white'}`}>
            <Icon.upload width={28} height={28} className="text-fno-700" />
            <p className="mt-3 text-sm font-medium text-slate-900">Přetáhněte zprávy sem</p>
            <p className="mt-1 text-xs text-slate-600">PDF, TXT nebo XLSX export z NIS (jeden řádek = jedna zpráva)</p>
            <button type="button" className={`${btn.secondary} mt-4`} onClick={() => picker.current?.click()} disabled={busy}>Vybrat soubory</button>
            <input ref={picker} type="file" multiple accept={ACCEPT.join(',')} className="hidden"
              onChange={(e) => { add(e.target.files); e.target.value = '' }} />
          </div>

          {files.length > 0 && (
            <ul className={`${panel} divide-y divide-slate-100`} aria-label="Vybrané soubory">
              {files.map((f, i) => (
                <li key={`${f.name}-${f.size}`} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <Icon.file width={18} height={18} className="shrink-0 text-fno-700" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-slate-900">{f.name}</span>
                    <span className="text-xs text-slate-600">{guessKind(f.name)} · {size(f.size)}</span>
                  </span>
                  <button className="rounded p-1 text-slate-500 transition-colors duration-150 hover:bg-red-50 hover:text-red-700" disabled={busy}
                    onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Odebrat ${f.name}`}>
                    <Icon.x width={16} height={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error && <Notice tone="error">{error}</Notice>}
        </div>

        <aside className={`${panel} h-fit space-y-4 p-4`}>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-900">Rodné číslo nebo ID pacienta</span>
            <input className={input} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="nepovinné, např. 855201/1234" disabled={busy} />
            <span className="mt-1 block text-xs text-slate-600">Když ho nevyplníte, AI ho vezme ze zpráv. Nesoulad mezi zprávami aplikace ohlásí.</span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 size-4" checked={extract} onChange={(e) => setExtract(e.target.checked)} disabled={busy} />
            <span>
              <span className="font-medium text-slate-900">Hned spustit vytěžování AI</span>
              <span className="block text-xs text-slate-600">Obvykle trvá 20–40 sekund.</span>
            </span>
          </label>
          <button className={`${btn.primary} w-full`} disabled={!files.length || busy} onClick={submit}>
            {step === 'upload' ? 'Nahrávám zprávy…' : step === 'extract' ? 'AI vytěžuje hlášení…' : extract ? 'Nahrát a vytěžit' : 'Nahrát zprávy'}
          </button>
          {busy && (
            <ol className="space-y-1 text-xs text-slate-700" aria-live="polite">
              <Progress done={step === 'extract'} active={step === 'upload'}>Nahrání a převod zpráv na text</Progress>
              {extract && <Progress done={false} active={step === 'extract'}>Vytěžení polí hlášení s citacemi</Progress>}
            </ol>
          )}
          {!files.length && <p className="text-xs text-slate-600">Nejdřív vyberte alespoň jednu zprávu.</p>}
        </aside>
      </div>
    </>
  )
}

function Progress({ done, active, children }: { done: boolean; active: boolean; children: string }) {
  return (
    <li className="flex items-center gap-2">
      {done ? <Icon.check width={14} height={14} className="text-emerald-700" />
        : <span className={`size-3.5 rounded-full border-2 ${active ? 'animate-spin border-fno-200 border-t-fno-800' : 'border-slate-300'}`} />}
      <span className={active ? 'font-medium text-fno-900' : ''}>{children}</span>
    </li>
  )
}
