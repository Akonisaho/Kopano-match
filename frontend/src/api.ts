// Token lives in sessionStorage: cleared when the tab closes, and the server expires it in 30 minutes.
// Trade-off to state honestly: any XSS could read it. React escapes output and we render no raw HTML.
const KEY = 'kopano_token'

export const getToken = () => sessionStorage.getItem(KEY)
export const setToken = (t: string | null) =>
  t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY)

/** Seconds until the access token expires, read from its payload (display only; the server enforces it). */
export function tokenSecondsLeft(): number | null {
  const t = getToken()
  if (!t) return null
  try {
    const payload = JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return Math.max(0, payload.exp - Math.floor(Date.now() / 1000))
  } catch {
    return null
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function detailText(d: unknown): string {
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((e) => (e?.msg ?? '').replace(/^Value error, /, '')).join('; ')
  return 'Something went wrong'
}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams))
    headers.set('Content-Type', 'application/json')
  const res = await fetch(`/api${path}`, { ...init, headers })
  if (res.status === 401 && token) {
    setToken(null)
    window.location.assign('/login')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, detailText(body.detail))
  }
  return res
}

const request = async <T>(path: string, init: RequestInit = {}): Promise<T> => (await raw(path, init)).json()

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; role: Role }>('/auth/login', {
      method: 'POST',
      body: new URLSearchParams({ username: email, password }),
    }),
  register: (b: unknown) => request<{ access_token: string; role: Role }>('/auth/register', json('POST', b)),
  me: () => request<Me>('/me'),
  myData: () => request<unknown>('/me/data'),
  myAudit: () => request<{ action: string; entity_type: string; timestamp: string }[]>('/me/audit'),
  deleteMe: () => request<unknown>('/me/delete', json('POST')),
  taxonomy: () => request<Taxonomy>('/meta/taxonomy'),
  showcase: () => request<Showcase>('/meta/showcase'),

  profile: () => request<ProfileResponse>('/smes/me'),
  saveProfile: (b: Profile) => request<Profile>('/smes/me', json('PUT', b)),
  extractProfile: (text: string) =>
    request<{ source: string; draft: Partial<Profile> }>('/smes/me/extract', json('POST', { text })),
  reverify: () => request<{ verification_status: string }>('/smes/me/verify', json('POST')),
  verifyIdentity: (form: FormData) =>
    request<{ result: string; confidence: number; source_label: string; retained: string }>(
      '/smes/me/verify-identity', { method: 'POST', body: form }),
  smeDashboard: () => request<SmeDashboard>('/smes/me/dashboard'),
  smeOpportunities: () => request<SmeOpportunity[]>('/smes/me/opportunities'),
  documents: () => request<Doc[]>('/documents'),
  upload: (form: FormData) => request<Doc & { verification: string }>('/documents', { method: 'POST', body: form }),
  downloadDocument: async (id: string) => (await raw(`/documents/${id}/file`)).blob(),

  opportunities: () => request<OppSummary[]>('/opportunities'),
  opportunity: (id: string) => request<OppDetail>(`/opportunities/${id}`),
  createOpportunity: (b: unknown) => request<OppSummary>('/opportunities', json('POST', b)),
  extractOpportunity: (text: string) =>
    request<{ source: string; draft: ReqDraft }>('/opportunities/extract', json('POST', { text })),
  runMatch: (id: string) => request<MatchRow[]>(`/opportunities/${id}/match`, json('POST')),
  matches: (id: string) => request<MatchRow[]>(`/opportunities/${id}/matches`),
  consortium: (id: string) => request<{ consortium: Consortium | null }>(`/opportunities/${id}/consortium`),
  match: (id: string) => request<MatchDetail>(`/matches/${id}`),
  decide: (id: string, action: 'shortlist' | 'reject') => request<unknown>(`/matches/${id}/${action}`, json('POST')),

  apply: (matchId: string) => request<{ id: string; status: string }>(`/applications/${matchId}`, json('POST')),
  applications: () => request<Application[]>('/applications'),

  overview: () => request<ProviderOverview>('/providers/overview'),
  directory: () => request<DirectorySme[]>('/providers/smes'),
  shortlist: () => request<ShortlistRow[]>('/providers/shortlist'),

  queue: () => request<Queue>('/admin/queue'),
  reviewVerification: (id: string, decision: string) =>
    request<unknown>(`/admin/verifications/${id}/review`, json('POST', { decision })),
  reviewMatch: (id: string, decision: string) =>
    request<unknown>(`/admin/matches/${id}/review`, json('POST', { decision })),
}

export type Role = 'sme' | 'corporate' | 'funder' | 'support' | 'admin'
export type Quadrant = 'award_now' | 'coachable' | 'ready_weak_fit' | 'develop'
export type Kind = 'procurement' | 'grant' | 'funding' | 'investor' | 'support'

export interface Me {
  id: string; email: string; full_name: string; role: Role
  organisation: { id: string; name: string; verification_status: string } | null
}
export interface Taxonomy {
  sectors: string[]; provinces: string[]; ownership: string[]
  capabilities: { code: string; sector: string; label: string }[]
  credentials: { code: string; label: string; issuer: string; days: number; cost_zar: number }[]
}
export interface Profile {
  sector: string; province: string; annual_turnover: number; years_trading: number
  largest_past_contract: number; capability_codes: string[]; ownership: string[]
  visible_to_corporates: boolean
}
export interface Verification {
  document_type?: string | null
  id: string; subject_type: string; provider: string; result: string
  source_label: string; flagged: boolean; review_status: string | null
}
export interface Completion { percent: number; steps: { label: string; done: boolean }[] }
export interface ProfileResponse {
  profile: Profile | null
  organisation: { name: string; registration_number: string | null; verification_status: string }
  verifications: Verification[]
  completion: Completion
}
export interface Doc {
  id: string; document_type: string; issuer: string; expiry_date: string | null
  status: string; uploaded_at: string; has_file: boolean
}
export interface Gap {
  credential: string; label: string; status: string; mandatory: boolean
  issuer: string; days: number; cost_zar: number; also_unlocks: number
}
export interface RiskFlags {
  overtrading: boolean; overtrading_pct: number; working_capital_zar: number
  concentration: boolean; concentration_pct: number
}
export interface OppSummary {
  id: string; title: string; sector: string; province: string; contract_value: number
  duration_months: number; status: string; kind: Kind; deadline: string | null
  provider: string | null; quadrants?: Partial<Record<Quadrant, number>>
}
export interface OppDetail extends OppSummary {
  description: string | null; payment_terms_days: number
  scope_items: { code: string; value: number }[]
  requirements: { id: string; requirement_type: string; requirement_value: Record<string, unknown>; mandatory: boolean; weight: number }[]
}
export interface ReqDraft {
  sector: string | null; province: string | null; min_years: number | null
  required_documents: string[]; capability_codes: string[]
}
export interface MatchRow {
  match_id: string; sme_id: string; sme_name: string; verification_status: string
  gate: string; quadrant: Quadrant; fit: number; readiness: number; overall: number
  risk_flags: RiskFlags; gap_count: number; status: string
}
export interface Consortium {
  lead: { sme_id: string; name: string }; members: { sme_id: string; name: string }[]
  coverage_pct: number; uncovered_codes: string[]
}
export interface MatchDetail {
  match_id: string
  opportunity: { id: string; title: string; kind: Kind; contract_value: number }
  sme: { id: string; name: string; verification_status: string }
  verifications: Verification[]
  gate: string; quadrant: Quadrant; fit: number; readiness: number
  components: Record<string, number>; gaps: Gap[]; risk_flags: RiskFlags
  rationale: string; rationale_source: string; status: string; model_version: string
}
export interface SmeDashboard {
  readiness_score: number | null
  open_gaps: (Gap & { blocks: string[] })[]
  matches: { match_id: string; opportunity: string; contract_value: number; quadrant: Quadrant; fit: number; readiness: number; gate: string; status: string }[]
}
export interface SmeOpportunity {
  opportunity_id: string; title: string; kind: Kind; provider: string; provider_status: string
  sector: string; province: string; contract_value: number; deadline: string | null
  blockers: string[]
  match: null | {
    match_id: string; quadrant: Quadrant; fit: number; readiness: number; gate: string
    gap_count: number; status: string; application: string | null
  }
}
export interface Application {
  id: string; match_id: string; opportunity: string; sme: string; status: string | null
  fit: number; readiness: number; quadrant: Quadrant; submitted_at: string
}
export interface ProviderOverview {
  organisation: { name: string; verification_status: string } | null
  active_opportunities: number; closing_soon: number; matched_smes: number
  high_fit: number; shortlisted: number; flagged: number; by_quadrant: Partial<Record<Quadrant, number>>
}
export interface DirectorySme {
  id: string; name: string; sector: string; province: string; years_trading: number
  capability_codes: string[]; verification_status: string; checks_passed: number; documents_on_file: number
}
export interface ShortlistRow {
  match_id: string; opportunity: string; sme: string; fit: number; readiness: number
  quadrant: Quadrant; risk_flags: RiskFlags; gap_count: number; application: string | null
}
export interface Queue {
  verifications: { id: string; subject_type: string; organisation: string | null; document_type?: string | null; result: string; source_label: string; checked_at: string }[]
  matches: { id: string; sme: string; opportunity: string; fit: number; readiness: number; reason: string }[]
}
export interface Showcase {
  smes: number; opportunities: number
  chart: null | { contract_value: number; dots: { fit: number; readiness: number; quadrant: Quadrant; overtrading: boolean }[] }
  example?: null | { fit: number; readiness: number; days: number; cost_zar: number; gaps: { label: string; issuer: string; days: number; cost_zar: number; also_unlocks: number }[] }
  consortium?: null | { opportunity_value: number; members: number; coverage_pct: number; scope_lines: number }
}

export const PROVIDER_ROLES: Role[] = ['corporate', 'funder', 'support']
export const isProvider = (r: Role) => PROVIDER_ROLES.includes(r)

export const zar = (n: number) => 'R' + Math.round(n).toLocaleString('en-ZA').replace(/ /g, ' ')
export const pretty = (s: string) =>
  s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()).replace(/Ict/g, 'ICT').replace(/Bbbee/g, 'B-BBEE')
export const dateFmt = (s: string | null) =>
  s ? new Date(s).toLocaleDateString('en-ZA', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const daysUntil = (s: string | null) =>
  s ? Math.ceil((new Date(s).getTime() - Date.now()) / 86400000) : null

export const KIND_LABEL: Record<Kind, string> = {
  procurement: 'Procurement', grant: 'Grant', funding: 'Funding', investor: 'Investor', support: 'Business support',
}
export const QUADRANT_LABEL: Record<Quadrant, string> = {
  award_now: 'Award ready', coachable: 'Coachable', ready_weak_fit: 'Ready, weak fit', develop: 'Develop',
}
export const QUADRANT_COLOR: Record<Quadrant, string> = {
  award_now: '#7c3aed', coachable: '#f59e0b', ready_weak_fit: '#2563eb', develop: '#98a2b3',
}
export const QUADRANT_BADGE: Record<Quadrant, string> = {
  award_now: 'purple', coachable: 'amber', ready_weak_fit: 'blue', develop: 'gray',
}
