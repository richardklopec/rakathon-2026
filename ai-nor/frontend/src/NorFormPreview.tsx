// Preview that mirrors the ÚZIS NOR form "Incidence zhoubného novotvaru" (screenshots from FNO, contracts/nor_form.md).
// Display values come from GET /api/cases/{id}/uzis-preview; the editable controls read and write the NorReport itself
// (select options from GET /api/codelists), so an edit here is the same as a clinician's edit in the review queue.
import { useId, useState, type ReactNode } from 'react'
import { getField, type Codelists, type NorReport, type Option, type PartialDate, type TNM } from './api'

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

/** Long code lists (MKN-10, topografie, morfologie): type to filter, only a code from the list is accepted. */
function CodeSelect({ value, options, onChange, disabled, className = '' }: {
  value: unknown; options: Option[]; onChange: (v: string | null) => void; disabled?: boolean; className?: string
}) {
  const id = useId()
  const label = (v: unknown) => (v == null ? '' : options.find((o) => o.value === v)?.label ?? String(v))
  const [text, setText] = useState(label(value))
  const [error, setError] = useState<string | null>(null)

  function commit(t: string) {
    const s = t.trim()
    if (!s) { setError(null); if (value != null) onChange(null); return }
    const code = s.split(' - ')[0].trim().toUpperCase()
    const hit = options.find((o) => o.label === s) ?? options.find((o) => String(o.value).toUpperCase() === code)
    if (!hit) { setError('Kód není v číselníku'); return }
    setError(null)
    setText(hit.label)
    if (hit.value !== value) onChange(String(hit.value))
  }

  return (
    <div className={className}>
      <div className="relative">
        <input className={`w-full pl-2 pr-7 ${BOX} ${border(error)}`} list={id} value={text} disabled={disabled}
          placeholder="hledat kód nebo název…"
          onChange={(e) => {
            setText(e.target.value)
            // picking from the list fills the whole label: save immediately
            if (options.some((o) => o.label === e.target.value)) commit(e.target.value)
          }}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && commit(e.currentTarget.value)} />
        <span className="pointer-events-none absolute right-0 top-0 flex h-8 w-6 items-center justify-center border-l border-slate-300 text-[10px] text-slate-500">▼</span>
      </div>
      <datalist id={id}>{options.map((o) => <option key={String(o.value)} value={o.label} />)}</datalist>
      <FieldError msg={error} />
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

function Fieldset({ legend, children }: { legend: ReactNode; children: ReactNode }) {
  return (
    <div className="relative mt-5 rounded-md border border-slate-300 px-3 pb-4 pt-6">
      <div className="absolute -top-3 left-2 flex items-center gap-1 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[13px] text-slate-800">{legend}</div>
      {children}
    </div>
  )
}

export default function NorFormPreview({ data, report, lists, editable, onEdit, onPatient }: {
  data: Rec
  report: NorReport
  lists: Codelists | null
  editable: boolean
  onEdit: (change: (r: NorReport) => void) => void
  onPatient: (ref: string | null) => Promise<string | null> // error message or null
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
          <div><Label>Zařízení (pracoviště):</Label><Box value={dc.zarizeni} /></div>
          <div><Label>Oddělení:</Label><Box value={dc.oddeleni} /></div>
        </div>

        <Fieldset legend="Diagnóza">
          <div className="grid grid-cols-[1fr_1fr] gap-4">
            <div className="space-y-2">
              <div className="flex gap-4"><Check checked={false} label="Neznámo (bezdomovec, neudaný pobyt)" /><Check checked={false} label="Cizinec" /></div>
              <Label>Datum stanovení diagnózy (není-li známo, uvést datum vyšetření nebo zahájení léčby):</Label>
              <TextInput key={txt(dg.datum_stanoveni_diagnozy)} value={dg.datum_stanoveni_diagnozy} disabled={off} className="w-44"
                placeholder="d.m.rrrr" validate={(v) => (parseDate(v) === 'invalid' ? 'datum d.m.rrrr, m.rrrr nebo rrrr, ne v budoucnosti' : null)}
                onCommit={(v) => set('diagnosis_date', parseDate(v))} />
            </div>
            <div><Label>Země původu:</Label><Box value={dc.zeme_puvodu} className="w-56" /></div>
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
            <div><Label>Identifikace specifických diagnóz:</Label><Box value="" /></div>
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
          <div className="flex items-center gap-2"><span className="text-[13px] italic">Skupina:</span><Box value="" className="w-56" /></div>
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

          <div className="mt-4 grid grid-cols-3 gap-3 opacity-60">
            <div><Label>Riziková kategorie:</Label><Box value="" /></div>
            <div><Label>Sérové nádorové markery:</Label><Box value="" /></div>
            <div><Label>p16 pozitivní</Label><Box value="" /></div>
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
            <Check checked={(reporting & 1) === 1} label="stanovilo diagnózu novotvaru" />
            <Check checked={(reporting & 2) === 2} label="léčí pacienta s novotvarem" />
          </div>
        </div>
      </div>
    </div>
  )
}
