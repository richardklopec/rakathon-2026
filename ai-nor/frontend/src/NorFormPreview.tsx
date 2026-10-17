// Preview that mirrors the ÚZIS NOR form "Incidence zhoubného novotvaru" (screenshots from FNO, contracts/nor_form.md).
// Display values come from GET /api/cases/{id}/uzis-preview; the editable controls read and write the NorReport itself
// (select options from GET /api/codelists), so an edit here is the same as a clinician's edit in the review queue.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { getField, type Codelists, type NorReport, type Option, type PartialDate, type TNM, type FormFields } from './api'

type Rec = Record<string, unknown>

const txt = (v: unknown) => (v == null || v === '' ? '' : String(v))
const hasBit = (sum: unknown, bit: number) => typeof sum === 'number' && (bit === 0 ? false : (sum & bit) === bit)

const BOX = 'h-8 rounded-md border bg-white text-[14px] shadow-[1px_2px_3px_rgba(0,0,0,0.25)] disabled:bg-slate-50 disabled:text-slate-700'
const border = (error?: string | null) => (error ? 'border-red-500 ring-1 ring-red-400' : 'border-slate-300')

// TNM values as written in the form, without prefixes (contracts/nor_form.md)
const TNM_PATTERN: Record<string, RegExp> = {
  t: /^(X|0|is|[1-4][a-d]?(\(m\))?)$/i,
  n: /^(X|[0-3][a-d]?(mi)?(\(sn\)|\(i[+-]\))?)$/i,
  m: /^(X|0|1[a-d]?)$/i,
}

function parseDate(s: string, today = new Date()): PartialDate | null | 'invalid' {
  const t = s.trim()
  if (!t) return null
  let y: number, m: number | null = null, d: number | null = null
  let x: RegExpMatchArray | null
  if ((x = t.match(/^(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})$/))) [d, m, y] = [Number(x[1]), Number(x[2]), Number(x[3])]
  else if ((x = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/))) [y, m, d] = [Number(x[1]), Number(x[2]), Number(x[3])]
  else if ((x = t.match(/^(\d{1,2})\.\s?(\d{4})$/))) [m, y] = [Number(x[1]), Number(x[2])]
  else if ((x = t.match(/^(\d{4})$/))) y = Number(x[1])
  else return 'invalid'
  if (y < 1900) return 'invalid'
  if (m != null && (m < 1 || m > 12)) return 'invalid'
  const probe = new Date(y, (m ?? 1) - 1, d ?? 1)
  if (d != null && probe.getDate() !== d) return 'invalid' // 31. 2. etc.
  if (probe > today) return 'invalid'
  return { year: y, month: m, day: d }
}

function Label({ children }: { children: ReactNode }) {
  return <div className="mb-1 text-[13px] italic text-slate-700 underline decoration-slate-400 underline-offset-2">{children}</div>
}

function Box({ value, className = '' }: { value: unknown; className?: string }) {
  return (
    <div className={`flex items-center px-2 ${BOX} ${border()} ${className}`}>
      <span className="flex-1 truncate">{txt(value)}</span>
    </div>
  )
}

function FieldError({ msg }: { msg?: string | null }) {
  return msg ? <div className="mt-0.5 text-[12px] text-red-700">{msg}</div> : null
}

/** Small fixed code lists (lateralita, grading, …): a native select like in the NOR application. */
function Select({ value, options, onChange, disabled, className = '' }: {
  value: unknown; options: Option[]; onChange: (v: string | null) => void; disabled?: boolean; className?: string
}) {
  const current = value == null ? '' : String(value)
  const known = options.some((o) => String(o.value) === current)
  return (
    <select className={`w-full px-1 ${BOX} ${border()} ${className}`} value={current} disabled={disabled}
      onChange={(e) => onChange(e.target.value || null)}>
      <option value="">—</option>
      {!known && current && <option value={current}>{current} (mimo číselník)</option>}
      {options.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
    </select>
  )
}

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
// crude Czech stemming for search: 'jícen' must find 'jícnu', 'plíce' 'plic'; codes (with digits) stay exact
const stem = (w: string) => (/\d/.test(w) || w.length <= 4 ? w : w.slice(0, Math.max(3, w.length - 2)))
const SHOWN = 1000 // rows rendered at once (the code lists have ~700), so the current value is in view when opened

/** Long code lists (MKN-10, topografie, morfologie): a select with a search box, like the NOR application.
 *  Opens the whole list on click; typing filters by code, name and site words (diacritics ignored). Only codes
 *  from the list can be chosen. */
function CodeSelect({ value, options, onChange, disabled, className = '' }: {
  value: unknown; options: Option[]; onChange: (v: string | null) => void; disabled?: boolean; className?: string
}) {
  const listId = useId()
  const root = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const current = options.find((o) => o.value === value)
  const outside = value != null && !current // value from extraction that is not in the code list

  const hits = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean).map(stem)
    if (!words.length) return options
    const matches = options.filter((o) => {
      const hay = fold(`${o.label} ${o.search ?? ''}`)
      return words.every((w) => hay.includes(w))
    })
    // options whose own label matches come before those found only through the site words
    const inLabel = (o: Option) => words.every((w) => fold(o.label).includes(w))
    return [...matches.filter(inLabel), ...matches.filter((o) => !inLabel(o))]
  }, [options, query])

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active, open])

  function show() {
    if (disabled) return
    setQuery('')
    setActive(Math.max(0, options.findIndex((o) => o.value === value)))
    setOpen(true)
  }
  function pick(o: Option | null) {
    setOpen(false)
    const v = o ? String(o.value) : null
    if (v !== (value == null ? null : String(value))) onChange(v)
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, Math.min(hits.length, SHOWN) - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (hits[active]) pick(hits[active]) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div ref={root} className={`relative ${className}`}>
      <button type="button" disabled={disabled} onClick={() => (open ? setOpen(false) : show())}
        aria-haspopup="listbox" aria-expanded={open} aria-controls={listId}
        title={current?.label ?? (outside ? `${String(value)} není v číselníku` : undefined)}
        className={`flex w-full items-center text-left ${BOX} ${border(outside ? 'mimo číselník' : null)}`}>
        <span className={`flex-1 truncate px-2 ${current || outside ? '' : 'text-slate-400'}`}>
          {current?.label ?? (outside ? `${String(value)} (mimo číselník)` : '—')}
        </span>
        <span className="flex h-full w-6 items-center justify-center border-l border-slate-300 text-[10px] text-slate-500">▼</span>
      </button>
      {outside && <FieldError msg="Kód není v číselníku, vyberte ze seznamu" />}

      {open && (
        <div className="absolute left-0 z-20 mt-1 w-full min-w-[26rem] rounded-md border border-slate-300 bg-white shadow-lg">
          <input autoFocus className="w-full border-b border-slate-200 px-2 py-1.5 text-[14px] outline-none"
            placeholder={`Hledat kód, název nebo orgán (${options.length} položek)…`} value={query}
            role="combobox" aria-controls={listId} aria-expanded
            onChange={(e) => { setQuery(e.target.value); setActive(0) }} onKeyDown={onKey} />
          <ul ref={list} id={listId} role="listbox" className="max-h-72 overflow-auto py-1 text-[13px]">
            {!query && value != null && (
              <li role="option" aria-selected={false} className="cursor-pointer px-2 py-1 text-slate-500 hover:bg-slate-100" onMouseDown={() => pick(null)}>
                — vymazat
              </li>
            )}
            {hits.slice(0, SHOWN).map((o, i) => (
              <li key={String(o.value)} data-i={i} role="option" aria-selected={o.value === value}
                className={`cursor-pointer px-2 py-1 ${i === active ? 'bg-blue-600 text-white' : o.value === value ? 'bg-blue-50' : 'hover:bg-slate-100'}`}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(o) }}>
                <div className="truncate">{o.label}</div>
                {query && o.search && !fold(o.label).includes(stem(fold(query).split(/\s+/)[0])) && (
                  <div className={`truncate text-[11px] ${i === active ? 'text-blue-100' : 'text-slate-500'}`}>{o.search}</div>
                )}
              </li>
            ))}
            {hits.length === 0 && <li className="px-2 py-1 text-slate-500">Nic nenalezeno, kód musí být z číselníku.</li>}
            {hits.length > SHOWN && <li className="px-2 py-1 text-[12px] text-slate-500">… a dalších {hits.length - SHOWN}, upřesněte hledání</li>}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Free text / number box that saves on blur or Enter; `validate` returns an error message or null. */
function TextInput({ value, onCommit, validate, disabled, className = '', type = 'text', placeholder }: {
  value: unknown; onCommit: (v: string) => void; validate?: (v: string) => string | null
  disabled?: boolean; className?: string; type?: 'text' | 'number'; placeholder?: string
}) {
  const [text, setText] = useState(txt(value))
  const [error, setError] = useState<string | null>(null)
  function commit() {
    if (text.trim() === txt(value)) { setError(null); return }
    const err = validate?.(text.trim()) ?? null
    setError(err)
    if (!err) onCommit(text.trim())
  }
  return (
    <div className={className}>
      <input className={`w-full px-2 ${BOX} ${border(error)}`} type={type} min={type === 'number' ? 0 : undefined} value={text}
        disabled={disabled} placeholder={placeholder} title={error ?? undefined}
        onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && commit()} />
      <FieldError msg={error} />
    </div>
  )
}

function Check({ checked, label, onToggle, disabled }: { checked: boolean; label: string; onToggle?: () => void; disabled?: boolean }) {
  return (
    <label className="flex items-center gap-1.5 text-[13px] text-slate-800">
      <input type="checkbox" className="h-3.5 w-3.5 accent-blue-600" checked={checked} disabled={disabled || !onToggle}
        onChange={() => onToggle?.()} />
      {label}
    </label>
  )
}

// code list behind each field (GET /api/codelists), as the form uses them
const FIELD_LIST: Record<string, string> = {
  laterality: 'laterality', icd10: 'icd10', topography: 'topography', morphology_type: 'morphology_type',
  morphology_code: 'morphology_code', grade: 'grade', sentinel_node: 'sentinel_node', clinical_stage: 'clinical_stage',
  disease_extent: 'disease_extent', diagnosis_basis: 'diagnosis_basis', metastasis_sites: 'metastasis_sites',
}
const BIT_FIELDS = new Set(['diagnosis_basis', 'metastasis_sites'])
const LONG_LISTS = new Set(['icd10', 'topography', 'morphology_code'])
const showDate = (v: unknown) => {
  const d = v as PartialDate | null
  return d?.year ? [d.day, d.month, d.year].filter(Boolean).join('.') : ''
}

/** One field edited outside the form (review queue "Upravit"): the same controls and checks as in the form.
 *  onSave gets the value the report stores (code from the list, PartialDate, number, list of bits) or null. */
export function FieldEditor({ path, value, lists, onSave, onCancel }: {
  path: string; value: unknown; lists: Codelists | null; onSave: (v: unknown) => void; onCancel: () => void
}) {
  const [bits, setBits] = useState<number[]>(Array.isArray(value) ? (value as number[]) : [])
  const options = lists?.[FIELD_LIST[path]] ?? []
  const part = path.startsWith('tnm_') ? path.slice(-1) : null
  let control: ReactNode
  if (BIT_FIELDS.has(path)) {
    control = (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {options.filter((o) => Number(o.value) !== 0).map((o) => {
          const bit = Number(o.value)
          return <Check key={bit} label={o.label} checked={bits.includes(bit)}
            onToggle={() => setBits(bits.includes(bit) ? bits.filter((b) => b !== bit) : [...bits, bit].sort((a, b) => a - b))} />
        })}
        <button type="button" className="rounded bg-fno-800 px-2 py-0.5 text-xs font-medium text-white hover:bg-fno-700" onClick={() => onSave(bits)}>Uložit</button>
      </div>
    )
  } else if (options.length) {
    control = LONG_LISTS.has(path)
      ? <CodeSelect value={value} options={options} onChange={onSave} className="w-80" />
      : <Select value={value} options={options} onChange={onSave} className="w-56" />
  } else if (part) {
    control = <TextInput value={value} className="w-24" placeholder={part.toUpperCase()}
      validate={(v) => (v && !TNM_PATTERN[part].test(v) ? `neplatná hodnota ${part.toUpperCase()}` : null)}
      onCommit={(v) => onSave(v ? v.replace(/^x$/i, 'X') : null)} />
  } else if (path === 'diagnosis_date') {
    control = <TextInput value={showDate(value)} className="w-36" placeholder="d.m.rrrr"
      validate={(v) => (parseDate(v) === 'invalid' ? 'datum d.m.rrrr, m.rrrr nebo rrrr, ne v budoucnosti' : null)}
      onCommit={(v) => onSave(parseDate(v))} />
  } else if (path === 'pn_examined' || path === 'pn_positive') {
    control = <TextInput type="number" value={value} className="w-20"
      validate={(v) => (v && !/^\d{1,3}$/.test(v) ? 'celé číslo ≥ 0' : null)} onCommit={(v) => onSave(v === '' ? null : Number(v))} />
  } else {
    control = <TextInput value={value} className="w-72" onCommit={(v) => onSave(v || null)} />
  }
  return (
    <span className="flex flex-wrap items-start gap-2 font-[Arial,Helvetica,sans-serif]">
      {control}
      <button type="button" className="h-8 rounded px-2 text-xs text-slate-600 hover:bg-slate-100"
        onMouseDown={(e) => e.preventDefault()} onClick={onCancel}>Zrušit</button>
    </span>
  )
}

function Fieldset({ legend, children }: { legend: ReactNode; children: ReactNode }) {
  return (
    <div className="relative mt-5 rounded-md border border-slate-300 px-3 pb-4 pt-6">
      <div className="absolute -top-3 left-2 flex items-center gap-1 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[13px] text-slate-800">{legend}</div>
      {children}
    </div>
  )
}

export default function NorFormPreview({ data, report, lists, editable, onEdit, onPatient, onForm }: {
  data: Rec
  report: NorReport
  lists: Codelists | null
  editable: boolean
  onEdit: (change: (r: NorReport) => void) => void
  onPatient: (ref: string | null) => Promise<string | null> // error message or null
  onForm: (patch: Partial<FormFields>) => void // fields not in the documents (Case.form)
}) {
  const dc = (data.diagnosticka_cast ?? {}) as Rec
  const dg = (data.diagnoza ?? {}) as Rec
  const t = (data.tnm ?? {}) as Rec
  const h = (data.hlaseni ?? {}) as Rec
  const rcCheck = (data.pacient_rc ?? {}) as { je_rc?: boolean; platne?: boolean | null; chyby?: string[]; datum_narozeni?: string | null; pohlavi?: string | null }
  const complete = data.stav === 'Úplné'
  const reporting = typeof h.pracoviste_hlasici_novotvar === 'number' ? h.pracoviste_hlasici_novotvar : 0
  const [patientError, setPatientError] = useState<string | null>(null)
  const off = !editable

  // value the report currently holds (missing or rejected fields count as empty, like in the export)
  const val = (path: string): unknown => {
    const f = getField(report, path)
    return f.status === 'missing' || f.review.state === 'rejected' ? null : f.value
  }
  const set = (path: string, value: unknown) =>
    onEdit((r) => {
      const f = getField(r, path)
      const empty = value == null || value === '' || (Array.isArray(value) && value.length === 0)
      f.value = empty ? null : value
      f.status = empty ? 'missing' : 'found'
      f.alternatives = []
      f.review = { ...f.review, state: 'edited' }
    })
  const opts = (name: string) => lists?.[name] ?? []
  // free text the documents do not give (facility, country, TNM group...): shown from the preview data, saved in Case.form
  const free = (key: keyof FormFields, shown: unknown, className = '') => (
    <TextInput key={txt(shown)} value={shown} disabled={off} className={className} onCommit={(v) => onForm({ [key]: v.trim() || null })} />
  )

  // fixed list -> native select; long list -> searchable code select; no code lists loaded -> free text
  const sel = (path: string, list: string, className = '') =>
    lists ? <Select value={val(path)} options={opts(list)} disabled={off} className={className} onChange={(v) => set(path, v)} />
      : <TextInput value={val(path)} disabled={off} className={className} onCommit={(v) => set(path, v || null)} />
  const code = (path: string, list: string, className = '') =>
    opts(list).length ? <CodeSelect key={String(val(path))} value={val(path)} options={opts(list)} disabled={off} className={className} onChange={(v) => set(path, v)} />
      : <TextInput key={String(val(path))} value={val(path)} disabled={off} className={className} onCommit={(v) => set(path, v || null)} />
  const tnm = (path: string, part: 't' | 'n' | 'm', className = 'w-16') => (
    <TextInput key={String(val(path))} value={val(path)} disabled={off} className={className}
      validate={(v) => (v && !TNM_PATTERN[part].test(v) ? `neplatná hodnota ${part.toUpperCase()}` : null)}
      onCommit={(v) => set(path, v ? v.replace(/^x$/i, 'X') : null)} />
  )
  const bits = (path: string, list: string, sum: unknown) => {
    const current = (val(path) as number[] | null) ?? []
    const toggle = (bit: number) => set(path, (current.includes(bit) ? current.filter((b) => b !== bit) : [...current, bit]).sort((a, b) => a - b))
    return opts(list).map((o) => {
      const bit = Number(o.value)
      return <Check key={bit} label={o.label} disabled={off} checked={editable ? current.includes(bit) : hasBit(sum, bit)} onToggle={() => toggle(bit)} />
    })
  }
  const yPrefix = (report.tnm_pathological as TNM).y_prefix
  const nodes = (v: string, other: unknown, examined: boolean) => {
    if (!v) return null
    if (!/^\d{1,3}$/.test(v)) return 'celé číslo ≥ 0'
    if (other == null) return null
    return (examined ? Number(v) < Number(other) : Number(v) > Number(other)) ? 'pozitivních uzlin nemůže být víc než vyšetřených' : null
  }

  return (
    <div className="mx-auto max-w-[780px] rounded border border-slate-300 bg-white p-5 font-[Arial,Helvetica,sans-serif] text-slate-900">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-[20px] text-[#3c4a6e]">Incidence zhoubného novotvaru</h2>
        <span className="text-[12px] text-slate-600">{editable ? 'Pole lze upravit, změny se ukládají hned' : 'Potvrzeno, jen pro čtení'}</span>
      </div>

      <div className="rounded-md border border-slate-300 p-4">
        <div className="flex flex-wrap items-start gap-2 text-[15px] font-semibold">
          <span className="pt-1">Pacient RČ:</span>
          <div className="w-52 font-normal">
            <TextInput key={txt(data.pacient)} value={data.pacient} disabled={off} placeholder="RRMMDD/XXXX"
              onCommit={async (v) => setPatientError(await onPatient(v || null))} />
            <FieldError msg={patientError} />
          </div>
          {rcCheck.je_rc && (
            <span className={`pt-1.5 text-[12px] font-normal ${rcCheck.platne ? 'text-green-700' : 'text-red-700'}`}>
              {rcCheck.platne
                ? `✓ platné RČ · ${rcCheck.pohlavi === 'F' ? 'žena' : 'muž'}, nar. ${rcCheck.datum_narozeni?.split('-').reverse().map(Number).join('. ')}`
                : `✗ ${rcCheck.chyby?.join('; ')}`}
            </span>
          )}
        </div>
        <div className="mt-4 flex items-end justify-between">
          <div className="text-[13px]">Evid.č.ZN: <span className="text-[19px] font-bold text-slate-500">přidělí ÚZIS</span></div>
          <div className={`flex items-center gap-1 text-[14px] font-semibold ${complete ? 'text-green-700' : 'text-amber-700'}`}>
            <span className={`inline-block h-5 w-5 rounded ${complete ? 'bg-green-600' : 'bg-amber-500'}`} />
            {txt(data.stav)}
          </div>
        </div>

        <h3 className="mt-6 text-[18px] text-[#3c4a6e]">Diagnostická část</h3>
        <div className="mt-2 grid grid-cols-[2fr_1fr] gap-4 rounded-md border border-slate-300 p-3">
          <div><Label>Zařízení (pracoviště):</Label>{free('zarizeni', dc.zarizeni)}</div>
          <div><Label>Oddělení:</Label>{free('oddeleni', dc.oddeleni)}</div>
        </div>

        <Fieldset legend="Diagnóza">
          <div className="grid grid-cols-[1fr_1fr] gap-4">
            <div className="space-y-2">
              <div className="flex gap-4">
                <Check checked={dg.neznamo === true} label="Neznámo (bezdomovec, neudaný pobyt)" disabled={off} onToggle={() => onForm({ neznamo: dg.neznamo !== true })} />
                <Check checked={dg.cizinec === true} label="Cizinec" disabled={off} onToggle={() => onForm({ cizinec: dg.cizinec !== true })} />
              </div>
              <Label>Datum stanovení diagnózy (není-li známo, uvést datum vyšetření nebo zahájení léčby):</Label>
              <TextInput key={txt(dg.datum_stanoveni_diagnozy)} value={dg.datum_stanoveni_diagnozy} disabled={off} className="w-44"
                placeholder="d.m.rrrr" validate={(v) => (parseDate(v) === 'invalid' ? 'datum d.m.rrrr, m.rrrr nebo rrrr, ne v budoucnosti' : null)}
                onCommit={(v) => set('diagnosis_date', parseDate(v))} />
            </div>
            <div><Label>Země původu:</Label>{free('zeme_puvodu', dc.zeme_puvodu, 'w-56')}</div>
          </div>

          <div className="mt-4 grid grid-cols-[1fr_2fr] gap-4">
            <div className="pt-8"><Label>Lateralita:</Label>{sel('laterality', 'laterality')}</div>
            <div>
              <div className="mb-2 flex items-center gap-2"><Label>K dg. vedla tato vyšetření:</Label><Box value={dg.k_dg_vedla_vysetreni} className="w-12" /></div>
              <div className="grid grid-flow-col grid-rows-3 gap-y-2">{bits('diagnosis_basis', 'diagnosis_basis', dg.k_dg_vedla_vysetreni)}</div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-[1.3fr_1fr_1fr] gap-3">
            <div><Label>Dg. MKN:</Label>{code('icd10', 'icd10')}</div>
            <div><Label>Dg. slovně:</Label><Box value={dg.dg_slovne} /></div>
            <div><Label>Identifikace specifických diagnóz:</Label>{free('identifikace_specifickych_dg', dg.identifikace_specifickych_dg)}</div>
          </div>
          <div className="mt-3 grid grid-cols-[2fr_1fr] items-end gap-3">
            <div><Label>Topografie:</Label>{code('topography', 'topography')}</div>
            <div className="rounded-md border border-slate-300 px-2 py-1 text-center text-[13px] text-slate-700 shadow-[1px_2px_3px_rgba(0,0,0,0.2)]">Vztah Diagnóza / Topografie / Morfologie</div>
          </div>

          <div className="mt-4 text-[13px] font-bold">Morfologie</div>
          <div className="mt-1 grid grid-cols-[1fr_1.6fr_1.2fr] gap-3">
            <div><Label>Typ morfologie:</Label>{sel('morphology_type', 'morphology_type')}</div>
            <div><Label>Kód morfologie:</Label>{code('morphology_code', 'morphology_code')}</div>
            <div><Label>Grading:</Label>{sel('grade', 'grade')}</div>
          </div>
          <div className="mt-2"><Label>Název morfologie:</Label>
            <TextInput key={txt(val('morphology_name'))} value={val('morphology_name')} disabled={off} onCommit={(v) => set('morphology_name', v || null)} />
          </div>
        </Fieldset>

        <Fieldset legend={<>TNM <span className="inline-block h-3.5 w-3.5 rounded-full bg-blue-600" /></>}>
          <div className="flex items-center gap-2"><span className="text-[13px] italic">Skupina:</span>{free('skupina', t.skupina, 'w-56')}</div>
          <div className="mt-2 flex items-start gap-3 pl-8 text-[13px] italic">
            <span className="pt-1.5 underline">T</span>{tnm('tnm_clinical.t', 't')}
            <span className="pt-1.5 underline">N</span>{tnm('tnm_clinical.n', 'n')}
            <span className="pt-1.5 underline">M</span>{tnm('tnm_clinical.m', 'm', 'w-20')}
          </div>
          <div className="mt-3 flex flex-wrap items-start gap-1.5 text-[13px] italic">
            <span className="pt-1.5 underline">y</span>
            <span className="pt-2"><Check checked={yPrefix} label="" disabled={off}
              onToggle={() => onEdit((r) => { (r.tnm_pathological as TNM).y_prefix = !yPrefix })} /></span>
            <span className="pt-1.5 underline">pT</span>{tnm('tnm_pathological.t', 't')}
            <span className="pt-1.5 underline">pN</span>{tnm('tnm_pathological.n', 'n')}
            <span className="text-center leading-3 underline">pN<br />vyš.</span>
            <TextInput key={`v${txt(val('pn_examined'))}`} type="number" value={val('pn_examined')} disabled={off} className="w-16"
              validate={(v) => nodes(v, val('pn_positive'), true)} onCommit={(v) => set('pn_examined', v === '' ? null : Number(v))} />
            <span className="text-center leading-3 underline">pN<br />poz.</span>
            <TextInput key={`p${txt(val('pn_positive'))}`} type="number" value={val('pn_positive')} disabled={off} className="w-16"
              validate={(v) => nodes(v, val('pn_examined'), false)} onCommit={(v) => set('pn_positive', v === '' ? null : Number(v))} />
            <span className="pt-1.5 underline">sn</span>{sel('sentinel_node', 'sentinel_node', 'w-36')}
            <span className="pt-1.5 underline">pM</span>{tnm('tnm_pathological.m', 'm', 'w-14')}
          </div>

          <div className="mt-4 flex items-center gap-2"><span className="text-[13px]">Lokalizace vzdálených metastáz:</span><Box value={t.lokalizace_vzdalenych_metastaz} className="w-14" /></div>
          <div className="mt-2 grid grid-flow-col grid-rows-3 gap-y-2">{bits('metastasis_sites', 'metastasis_sites', t.lokalizace_vzdalenych_metastaz)}</div>

          <div className="mt-4 grid grid-cols-3 gap-3">
            <div><Label>Riziková kategorie:</Label>{free('rizikova_kategorie', t.rizikova_kategorie)}</div>
            <div><Label>Sérové nádorové markery:</Label>{free('serove_markery', t.serove_markery)}</div>
            <div><Label>p16 pozitivní</Label>{free('p16', t.p16)}</div>
          </div>
          <div className="mt-2 flex items-end gap-3">
            <div className="w-56"><Label>Klinické stádium:</Label>{sel('clinical_stage', 'clinical_stage')}</div>
          </div>
        </Fieldset>

        <Fieldset legend="Ostatní">
          <Label>Onemocnění:</Label>
          {sel('disease_extent', 'disease_extent', 'max-w-xs')}
        </Fieldset>

        <div className="mt-4 rounded-md border border-slate-300 p-3">
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Datum hlášení:</Label><Box value={h.datum_hlaseni} className="w-44" /></div>
            <div><Label>Jméno hlásícího lékaře:</Label><Box value={h.jmeno_hlasiciho_lekare} /></div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-[13px]">Pracoviště hlásící novotvar: <Box value={String(reporting).padStart(2, '0')} className="w-12" /></div>
          <div className="mt-2 flex gap-4">
            <Check checked={(reporting & 1) === 1} label="stanovilo diagnózu novotvaru" disabled={off} onToggle={() => onForm({ pracoviste_hlasici_novotvar: reporting ^ 1 })} />
            <Check checked={(reporting & 2) === 2} label="léčí pacienta s novotvarem" disabled={off} onToggle={() => onForm({ pracoviste_hlasici_novotvar: reporting ^ 2 })} />
          </div>
        </div>
      </div>
    </div>
  )
}
