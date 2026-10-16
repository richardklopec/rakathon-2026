// Preview that mirrors the ÚZIS NOR form "Incidence zhoubného novotvaru" (screenshots from FNO, contracts/nor_form.md).
// Read-only: values come from GET /api/cases/{id}/uzis-preview.
import type { ReactNode } from 'react'

type Rec = Record<string, unknown>

const BASIS: [number, string][] = [[0, '00 klinicky jasné'], [1, '01 klinické vyšetření'], [2, '02 laborator vyš. markery'], [4, '04 cytologie'], [8, '08 histologie metastázy'], [16, '16 histologie prim nádoru']]
const METASTASES: [number, string][] = [[0, '0 neznámo'], [1, '1 plíce'], [2, '2 kostní dřeň'], [4, '4 kost'], [8, '8 pleura'], [16, '16 játra'], [32, '32 peritoneum'], [64, '64 mozek'], [128, '128 nadledvinkové'], [256, '256 uzliny'], [512, '512 kůže'], [1024, '1024 jiný orgán']]

const txt = (v: unknown) => (v == null || v === '' ? '' : String(v))
const hasBit = (sum: unknown, bit: number) => typeof sum === 'number' && (bit === 0 ? false : (sum & bit) === bit)

function Label({ children }: { children: ReactNode }) {
  return <div className="mb-1 text-[13px] italic text-slate-700 underline decoration-slate-400 underline-offset-2">{children}</div>
}

function Box({ value, select, className = '' }: { value: unknown; select?: boolean; className?: string }) {
  return (
    <div className={`flex h-8 items-center rounded-md border border-slate-300 bg-white shadow-[1px_2px_3px_rgba(0,0,0,0.25)] ${className}`}>
      <span className="flex-1 truncate px-2 text-[14px]">{txt(value)}</span>
      {select && <span className="h-full w-6 border-l border-slate-300" />}
    </div>
  )
}

function Check({ checked, label }: { checked: boolean; label: string }) {
  return (
    <label className="flex items-center gap-1.5 text-[13px] text-slate-800">
      <span className={`inline-flex h-3.5 w-3.5 items-center justify-center rounded-sm border ${checked ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-500 bg-white'}`}>
        {checked && <svg viewBox="0 0 12 12" className="h-2.5 w-2.5"><path d="M2 6.5l2.5 2.5L10 3.5" fill="none" stroke="currentColor" strokeWidth="2" /></svg>}
      </span>
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

export default function NorFormPreview({ data }: { data: Rec }) {
  const dc = (data.diagnosticka_cast ?? {}) as Rec
  const dg = (data.diagnoza ?? {}) as Rec
  const mo = (data.morfologie ?? {}) as Rec
  const t = (data.tnm ?? {}) as Rec
  const os = (data.ostatni ?? {}) as Rec
  const h = (data.hlaseni ?? {}) as Rec
  const complete = data.stav === 'Úplné'
  const reporting = typeof h.pracoviste_hlasici_novotvar === 'number' ? h.pracoviste_hlasici_novotvar : 0

  return (
    <div className="mx-auto max-w-[780px] rounded border border-slate-300 bg-white p-5 font-[Arial,Helvetica,sans-serif] text-slate-900">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-[20px] text-[#3c4a6e]">Incidence zhoubného novotvaru</h2>
        <span className="text-[12px] text-slate-600">Nápověda</span>
      </div>

      <div className="rounded-md border border-slate-300 p-4">
        <div className="text-[15px] font-semibold">Pacient RČ: <span className="font-normal">{txt(data.pacient)}</span></div>
        <div className="mt-4 flex items-end justify-between">
          <div className="text-[13px]">Evid.č.ZN: <span className="text-[19px] font-bold text-slate-500">přidělí ÚZIS</span></div>
          <div className={`flex items-center gap-1 text-[14px] font-semibold ${complete ? 'text-green-700' : 'text-amber-700'}`}>
            <span className={`inline-block h-5 w-5 rounded ${complete ? 'bg-green-600' : 'bg-amber-500'}`} />
            {txt(data.stav)}
          </div>
        </div>

        <h3 className="mt-6 text-[18px] text-[#3c4a6e]">Diagnostická část</h3>
        <div className="mt-2 grid grid-cols-[2fr_1fr] gap-4 rounded-md border border-slate-300 p-3">
          <div><Label>Zařízení (pracoviště):</Label><Box value={dc.zarizeni} select /></div>
          <div><Label>Oddělení:</Label><Box value={dc.oddeleni} select /></div>
        </div>

        <Fieldset legend="Diagnóza">
          <div className="grid grid-cols-[1fr_1fr] gap-4">
            <div className="space-y-2">
              <div className="flex gap-4"><Check checked={false} label="Neznámo (bezdomovec, neudaný pobyt)" /><Check checked={false} label="Cizinec" /></div>
              <Label>Datum stanovení diagnózy (není-li známo, uvést datum vyšetření nebo zahájení léčby):</Label>
              <Box value={dg.datum_stanoveni_diagnozy} className="w-44" />
            </div>
            <div><Label>Země původu:</Label><Box value={dc.zeme_puvodu} select className="w-56" /></div>
          </div>

          <div className="mt-4 grid grid-cols-[1fr_2fr] gap-4">
            <div className="pt-8"><Label>Lateralita:</Label><Box value={dg.lateralita} select /></div>
            <div>
              <div className="mb-2 flex items-center gap-2"><Label>K dg. vedla tato vyšetření:</Label><Box value={dg.k_dg_vedla_vysetreni} className="w-12" /></div>
              <div className="grid grid-flow-col grid-rows-3 gap-y-2">
                {BASIS.map(([bit, label]) => <Check key={bit} checked={hasBit(dg.k_dg_vedla_vysetreni, bit)} label={label} />)}
              </div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-[1fr_1fr_1.3fr] gap-3">
            <div><Label>Dg. MKN:</Label><Box value={dg.dg_mkn} select /></div>
            <div><Label>Dg. slovně:</Label><Box value={dg.dg_slovne} /></div>
            <div><Label>Identifikace specifických diagnóz:</Label><Box value="" select className="w-44" /></div>
          </div>
          <div className="mt-3 grid grid-cols-[2fr_1fr] items-end gap-3">
            <div><Label>Topografie:</Label><Box value={dg.topografie} select /></div>
            <div className="rounded-md border border-slate-300 px-2 py-1 text-center text-[13px] text-slate-700 shadow-[1px_2px_3px_rgba(0,0,0,0.2)]">Vztah Diagnóza / Topografie / Morfologie</div>
          </div>

          <div className="mt-4 text-[13px] font-bold">Morfologie</div>
          <div className="mt-1 grid grid-cols-3 gap-3">
            <div><Label>Typ morfologie:</Label><Box value={mo.typ_morfologie} select /></div>
            <div><Label>Kód morfologie:</Label><Box value={mo.kod_morfologie} select /></div>
            <div><Label>Grading:</Label><Box value={mo.grading} select /></div>
          </div>
          <div className="mt-2"><Label>Název morfologie:</Label><Box value={mo.nazev_morfologie} /></div>
        </Fieldset>

        <Fieldset legend={<>TNM <span className="inline-block h-3.5 w-3.5 rounded-full bg-blue-600" /></>}>
          <div className="flex items-center gap-2"><span className="text-[13px] italic">Skupina:</span><Box value="" select className="w-56" /></div>
          <div className="mt-2 flex items-center gap-3 pl-8 text-[13px] italic">
            <span className="underline">T</span><Box value={t.T} className="w-14" />
            <span className="underline">N</span><Box value={t.N} className="w-14" />
            <span className="underline">M</span><Box value={t.M} className="w-20" />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[13px] italic">
            <span className="underline">y</span><Check checked={t.y === true} label="" />
            <span className="underline">pT</span><Box value={t.pT} className="w-14" />
            <span className="underline">pN</span><Box value={t.pN} className="w-14" />
            <span className="text-center leading-3 underline">pN<br />vyš.</span><Box value={t.pN_vys} className="w-12" />
            <span className="text-center leading-3 underline">pN<br />poz.</span><Box value={t.pN_poz} className="w-12" />
            <span className="underline">sn</span><Box value={t.sn} select className="w-32" />
            <span className="underline">pM</span><Box value={t.pM} className="w-12" />
          </div>

          <div className="mt-4 flex items-center gap-2"><span className="text-[13px]">Lokalizace vzdálených metastáz:</span><Box value={t.lokalizace_vzdalenych_metastaz} className="w-12" /></div>
          <div className="mt-2 grid grid-flow-col grid-rows-3 gap-y-2">
            {METASTASES.map(([bit, label]) => <Check key={bit} checked={hasBit(t.lokalizace_vzdalenych_metastaz, bit)} label={label} />)}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3 opacity-60">
            <div><Label>Riziková kategorie:</Label><Box value="" select /></div>
            <div><Label>Sérové nádorové markery:</Label><Box value="" select /></div>
            <div><Label>p16 pozitivní</Label><Box value="" select /></div>
          </div>
          <div className="mt-2 flex items-end gap-3">
            <div className="w-56"><Label>Klinické stádium:</Label><Box value={t.klinicke_stadium} select /></div>
            <div className="mb-0.5 rounded-md border border-slate-300 px-3 py-1 text-[13px] shadow-[1px_2px_3px_rgba(0,0,0,0.2)]">Vyplnit stádium</div>
          </div>
        </Fieldset>

        <Fieldset legend="Ostatní">
          <Label>Onemocnění:</Label>
          <Box value={os.onemocneni} select />
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
