// Mirrors contracts/nor_record.schema.json (backend/app/models.py). Keep in sync.

export type FieldStatus = 'found' | 'missing' | 'conflict' | 'not_applicable'
export type ReviewState = 'pending' | 'confirmed' | 'edited' | 'rejected' | 'auto_accepted'

export interface Evidence {
  doc_id: string
  quote: string
  start: number
  end: number
  verified: boolean
}

export interface RuleRef {
  source: string // MKN-10, Tabelární část (ÚZIS, 2014)
  code: string // category or note range, e.g. C50 or C00–D48
  page: number | null // printed page in the PDF
  quote: string
  verified: boolean // quote found in the rule texts
}

export interface Extracted<T = unknown> {
  value: T | null
  coding: { system: string; code: string; display?: string | null } | null
  status: FieldStatus
  confidence: number | null // 0-100
  confidence_reasons: string[]
  needs_review: boolean // conflict or confidence below threshold
  evidence: Evidence[]
  alternatives: T[]
  rules?: RuleRef[] // coding rules behind the value (MKN-10 Tabelární část)
  review: { state: ReviewState; by?: string | null; at?: string | null; note?: string | null }
}

export interface TNM {
  y_prefix: boolean
  t: Extracted<string>
  n: Extracted<string>
  m: Extracted<string>
}

export type NorReport = Record<string, Extracted | TNM | unknown[]>

export interface PartialDate {
  year: number
  month?: number | null
  day?: number | null
}

// select options of the NOR form (GET /api/codelists): value = what NorReport stores, label = what the form shows
export interface Option<V = string | number> {
  value: V
  label: string
  search?: string // extra words to find the option by (e.g. organ names from the MKN-10 neoplasm index)
}

// overall AI confidence of the report (backend app/confidence.py: overall)
export interface AiConfidence {
  score: number | null
  level: string | null
  fields_ai: number
  auto_accepted: number
  to_review: number
  conflicts: number
  edited_by_human: number
  missing_required: number
}
export type Codelists = Record<string, Option[]>

export function getField(report: NorReport, path: string): Extracted {
  const [a, b] = path.split('.')
  const top = report[a] as unknown as Record<string, unknown>
  return (b ? top[b] : top) as Extracted
}

export interface DocumentT {
  id: string
  filename: string
  kind: string | null
  text: string
}

export interface Case {
  id: string
  patient_ref: string | null
  documents: DocumentT[]
  report: NorReport
  warnings: string[]
  confirmed_by: string | null
  confirmed_at: string | null
  fhir_bundle_id: string | null
  updated_at: string
  ai_confidence: AiConfidence
}

// one entry of the change log (backend app/audit.py, IRIS table Nor.Audit)
export interface AuditEntry {
  id: string
  case_id: string
  at: string // ISO 8601 UTC
  actor: string
  kind: string // filled | changed | resolved | confirmed | confirmed_missing | rejected | removed | case_created | extracted | patient_changed | report_confirmed | fhir_submitted
  path: string | null
  label: string | null
  old: string | null
  new: string | null
  storage: 'iris' | 'local'
}

// reports waiting in IRIS FHIR from the hospital system (GET /api/nis/inbox)
export interface NisPatient {
  patient: string
  documents: { id: string; title: string; kind: string | null; date: string | null }[]
}

// last bulk export of a report (GET /api/exports, from the audit log)
export interface ExportInfo {
  at: string
  actor: string
  detail: string | null // e.g. "CSV, 3 hlášení v dávce"
}

// who is working: sent with every change as X-Actor (URL-encoded, HTTP headers can't carry diacritics) for the change log
let actor = ''
export const setActor = (name: string) => { actor = name.trim() }
const actorHeader = (): Record<string, string> => (actor ? { 'X-Actor': encodeURIComponent(actor) } : {})

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text()
    let msg = body
    try {
      msg = JSON.parse(body).detail ?? body
    } catch {
      /* plain text */
    }
    throw new Error(`${res.status}: ${msg}`)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body?: unknown) =>
  fetch(url, {
    method: 'POST',
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...actorHeader() },
    body: body ? JSON.stringify(body) : undefined,
  })

export const api = {
  health: () => fetch('/api/health').then(json<{ ok: boolean; llm_mode: string; fhir: boolean }>),
  cases: () => fetch('/api/cases').then(json<Case[]>),
  getCase: (id: string) => fetch(`/api/cases/${id}`).then(json<Case>),
  createCase: (files: File[], patientRef?: string) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    const q = patientRef ? `?patient_ref=${encodeURIComponent(patientRef)}` : ''
    return fetch(`/api/cases${q}`, { method: 'POST', body: form, headers: actorHeader() }).then(json<Case>)
  },
  extract: (id: string) => post(`/api/cases/${id}/extract`).then(json<Case>),
  saveReport: (id: string, report: NorReport) =>
    fetch(`/api/cases/${id}/report`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...actorHeader() },
      body: JSON.stringify(report),
    }).then(json<Case>),
  updatePatient: (id: string, patientRef: string | null) =>
    fetch(`/api/cases/${id}/patient`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...actorHeader() },
      body: JSON.stringify({ patient_ref: patientRef }),
    }).then(json<Case>),
  codelists: () => fetch('/api/codelists').then(json<Codelists>),
  uzisPreview: (id: string) => fetch(`/api/cases/${id}/uzis-preview`).then(json<Record<string, unknown>>),
  confirm: (id: string, by: string) => post(`/api/cases/${id}/confirm`, { by }).then(json<Case>),
  uzisExportUrl: (id: string) => `/api/cases/${id}/uzis-export`,
  submit: (id: string) => post(`/api/cases/${id}/submit`).then(json<{ entry?: unknown[] }>),
  nisInbox: () => fetch('/api/nis/inbox').then(json<{ iris: boolean; patients: NisPatient[] }>),
  nisImport: (patient: string, ids: string[]) => post('/api/nis/import', { patient, ids }).then(json<Case>),
  exportStatus: () => fetch('/api/exports').then(json<Record<string, ExportInfo>>),
  /** Bulk export of confirmed reports; downloads the file and returns its name. */
  exportReports: async (caseIds: string[], format: 'csv' | 'json') => {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...actorHeader() },
      body: JSON.stringify({ case_ids: caseIds, format }),
    })
    if (!res.ok) await json(res) // throws with the backend's message
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? `nor-hlaseni.${format}`
    const url = URL.createObjectURL(await res.blob())
    const a = Object.assign(document.createElement('a'), { href: url, download: name })
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    return name
  },
  audit: (id: string) => fetch(`/api/cases/${id}/audit`).then(json<{ iris: boolean; entries: AuditEntry[] }>),
}
