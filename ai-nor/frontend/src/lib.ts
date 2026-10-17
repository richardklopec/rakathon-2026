// Helpers shared by the tabs: case status, formatters, class names.
import type { Case, Codelists, Extracted, Option } from './api'

/** Fields at or above this AI confidence without a conflict are prefilled (backend AUTO_ACCEPT_THRESHOLD, keep equal). */
export const AUTO_ACCEPT = 80

// ---------- case status (derived from the case, the backend has no status field) ----------

export type CaseStatus = 'nevytezeno' | 'kontrola' | 'potvrzeni' | 'potvrzeno' | 'fhir'

export const STATUS: Record<CaseStatus, { label: string; hint: string; cls: string; dot: string }> = {
  nevytezeno: { label: 'Nevytěženo', hint: 'Dokumenty jsou nahrané, AI je ještě nezpracovala.', cls: 'bg-slate-100 text-slate-700', dot: 'bg-slate-400' },
  kontrola: { label: 'Ke kontrole', hint: 'Rozpory nebo nejistá pole čekají na lékaře. V IRIS FHIR je hlášení zatím jako rozpracované.', cls: 'bg-amber-50 text-amber-800', dot: 'bg-amber-500' },
  potvrzeni: { label: 'K potvrzení', hint: 'Kontrola hotová, chybí potvrzení celého hlášení.', cls: 'bg-fno-sky-soft text-fno-800', dot: 'bg-fno-sky' },
  potvrzeno: { label: 'Potvrzeno', hint: 'Lékař hlášení potvrdil, ale do IRIS FHIR se ho zatím nepodařilo zapsat.', cls: 'bg-emerald-50 text-emerald-800', dot: 'bg-emerald-500' },
  fhir: { label: 'Uloženo ve FHIR', hint: 'Potvrzené hlášení je v IRIS FHIR jako konečné (final).', cls: 'bg-fno-800 text-white', dot: 'bg-white' },
}
export const STATUS_ORDER: CaseStatus[] = ['nevytezeno', 'kontrola', 'potvrzeni', 'potvrzeno', 'fhir']

/** Fields waiting for the clinician: needs_review and still pending (same rule as backend confidence.review_queue).
 * Counted from the report because ai_confidence.to_review leaves out missing mandatory fields. */
export function pendingCount(c: Case): number {
  let n = 0
  for (const v of Object.values(c.report)) {
    if (v == null || typeof v !== 'object' || Array.isArray(v)) continue // lists (treatments, progression) are never reviewed
    const fields = ('y_prefix' in v ? [v.t, v.n, v.m] : [v]) as Extracted[]
    for (const f of fields) if (f?.needs_review && f.review?.state === 'pending') n++
  }
  return n
}

export function caseStatus(c: Case): CaseStatus {
  if (c.confirmed_at) return c.fhir?.status === 'final' && !c.fhir.error ? 'fhir' : 'potvrzeno'
  const a = c.ai_confidence
  if (!a || (a.fields_ai === 0 && a.edited_by_human === 0)) return 'nevytezeno'
  return pendingCount(c) > 0 ? 'kontrola' : 'potvrzeni'
}

/** Where the case stands in IRIS FHIR, in words: one record per case, a draft until the clinician confirms it. */
export function fhirState(c: Case): { tone: 'none' | 'draft' | 'final' | 'error'; text: string } {
  const f = c.fhir
  if (f?.error) return { tone: 'error', text: f.status ? 'Poslední změna se do IRIS FHIR nezapsala' : 'Do IRIS FHIR se hlášení nezapsalo' }
  if (f?.status === 'final') return { tone: 'final', text: `V IRIS FHIR jako konečné hlášení, verze ${f.version ?? '?'}` }
  if (f?.status === 'preliminary') return { tone: 'draft', text: `V IRIS FHIR jako rozpracované hlášení, verze ${f.version ?? '?'}` }
  return { tone: 'none', text: 'V IRIS FHIR zatím není (zapíše se po vytěžení)' }
}

// ---------- formatters ----------

/** The patient by birth number: the one the clinician confirmed in the preview, else the one in the documents. */
export const patientName = (c: Case) =>
  (c.patient_ref && /^[\d\s/]+$/.test(c.patient_ref) ? c.patient_ref : null)
  ?? c.document_rc ?? c.patient_ref ?? c.documents[0]?.filename ?? `Případ ${c.id.slice(0, 8)}`

export function diagnosis(c: Case, lists: Codelists | null): { code: string | null; name: string | null } {
  const code = (c.report.icd10 as { value?: string | null } | undefined)?.value ?? null
  if (!code) return { code: null, name: null }
  return { code, name: optionName(lists?.icd10, code) }
}

/** "C50.4 - ZN prsu" -> "ZN prsu" (labels in /api/codelists are "code - name"). */
export function optionName(options: Option[] | undefined, value: string | number): string | null {
  const o = options?.find((x) => x.value === value)
  if (!o) return null
  const i = o.label.indexOf(' - ')
  return i >= 0 ? o.label.slice(i + 3) : o.label
}

export const formatDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

/** Lower case without diacritics, for search. */
export const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

// ---------- class names ----------

export const btn = {
  primary: 'inline-flex items-center justify-center gap-2 rounded-md bg-fno-800 px-3.5 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-fno-700 active:bg-fno-900 disabled:bg-slate-300 disabled:text-slate-500',
  secondary: 'inline-flex items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-800 transition-colors duration-150 hover:border-fno-600 hover:text-fno-800 active:bg-fno-50 disabled:opacity-50',
  ghost: 'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-fno-700 transition-colors duration-150 hover:bg-fno-50 hover:text-fno-900',
}

export const panel = 'rounded-lg border border-slate-200 bg-white'
export const input = 'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-500 transition-colors duration-150 hover:border-slate-400 focus:border-fno-sky focus:outline-none focus:ring-2 focus:ring-fno-sky/25'

