// Mirrors contracts/nor_record.schema.json (backend/app/models.py). Keep in sync.

export type FieldStatus = 'found' | 'missing' | 'conflict' | 'not_applicable'
export type ReviewState = 'pending' | 'confirmed' | 'edited' | 'rejected'

export interface Evidence {
  doc_id: string
  quote: string
  start: number
  end: number
}

export interface Extracted<T = unknown> {
  value: T | null
  coding: { system: string; code: string; display?: string | null } | null
  status: FieldStatus
  confidence: number | null
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

export interface NorReport {
  diagnosis_date: Extracted<{ year: number; month?: number | null; day?: number | null }>
  icd10: Extracted<string>
  topography: Extracted<string>
  laterality: Extracted<string>
  diagnosis_basis: Extracted<number[]>
  morphology_code: Extracted<string>
  morphology_name: Extracted<string>
  grade: Extracted<string>
  tnm_clinical: TNM
  tnm_pathological: TNM
  sentinel_node: Extracted<string>
  clinical_stage: Extracted<string>
  metastasis_sites: Extracted<number[]>
  disease_extent: Extracted<string>
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
  fhir_bundle_id: string | null
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => fetch('/api/health').then(json<{ ok: boolean; llm_mode: string; fhir: boolean }>),
  createCase: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return fetch('/api/cases', { method: 'POST', body: form }).then(json<Case>)
  },
  extract: (id: string) => fetch(`/api/cases/${id}/extract`, { method: 'POST' }).then(json<Case>),
  saveReport: (id: string, report: NorReport) =>
    fetch(`/api/cases/${id}/report`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
    }).then(json<Case>),
  submit: (id: string) => fetch(`/api/cases/${id}/submit`, { method: 'POST' }).then(json<unknown>),
}
