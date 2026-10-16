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

export interface Extracted<T = unknown> {
  value: T | null
  coding: { system: string; code: string; display?: string | null } | null
  status: FieldStatus
  confidence: number | null // 0-100
  confidence_reasons: string[]
  needs_review: boolean // conflict or confidence below threshold
  evidence: Evidence[]
  alternatives: T[]
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
}

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
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
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
    return fetch(`/api/cases${q}`, { method: 'POST', body: form }).then(json<Case>)
  },
  extract: (id: string) => post(`/api/cases/${id}/extract`).then(json<Case>),
  saveReport: (id: string, report: NorReport) =>
    fetch(`/api/cases/${id}/report`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
    }).then(json<Case>),
  updatePatient: (id: string, patientRef: string | null) =>
    fetch(`/api/cases/${id}/patient`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_ref: patientRef }),
    }).then(json<Case>),
  codelists: () => fetch('/api/codelists').then(json<Codelists>),
  uzisPreview: (id: string) => fetch(`/api/cases/${id}/uzis-preview`).then(json<Record<string, unknown>>),
  confirm: (id: string, by: string) => post(`/api/cases/${id}/confirm`, { by }).then(json<Case>),
  uzisExportUrl: (id: string) => `/api/cases/${id}/uzis-export`,
  submit: (id: string) => post(`/api/cases/${id}/submit`).then(json<{ entry?: unknown[] }>),
}
