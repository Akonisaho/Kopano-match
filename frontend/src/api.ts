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
    request<LoginResult>('/auth/login', {
      method: 'POST',
      body: new URLSearchParams({ username: email, password }),
    }),
  register: (b: unknown) => request<{ access_token: string; role: Role }>('/auth/register', json('POST', b)),
  me: () => request<Me>('/me'),
  mfaVerify: (mfa_token: string, code: string) =>
    request<{ access_token: string; role: Role }>('/auth/mfa/verify', json('POST', { mfa_token, code })),
  mfaSetup: () => request<MfaSetup>('/auth/mfa/setup', json('POST')),
  mfaEnable: (code: string) => request<{ recovery_codes: string[] }>('/auth/mfa/enable', json('POST', { code })),
  mfaDisable: (code: string) => request<{ status: string }>('/auth/mfa/disable', json('POST', { code })),
  forgot: (email: string) => request<{ status: string }>('/auth/forgot', json('POST', { email })),
  reset: (token: string, new_password: string) =>
    request<{ status: string }>('/auth/reset', json('POST', { token, new_password })),
  notifications: () => request<NotificationBox>('/notifications'),
  markNotificationsRead: () => request<{ status: string }>('/notifications/read', json('POST')),
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
  simulate: (credentials: string[]) =>
    request<UnlockResult>('/smes/me/simulate', json('POST', { credentials })),
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
  consortium: (id: string) => request<{ consortium: Consortium | null; invitation: ConsortiumInvitation | null }>(`/opportunities/${id}/consortium`),
  match: (id: string) => request<MatchDetail>(`/matches/${id}`),
  decide: (id: string, action: 'shortlist' | 'reject') => request<unknown>(`/matches/${id}/${action}`, json('POST')),

  apply: (matchId: string) => request<{ id: string; status: string }>(`/applications/${matchId}`, json('POST')),
  applications: () => request<Application[]>('/applications'),

  overview: () => request<ProviderOverview>('/providers/overview'),
  directory: () => request<DirectorySme[]>('/providers/smes'),
  shortlist: () => request<ShortlistRow[]>('/providers/shortlist'),
  bottlenecks: () => request<UnlockMapData>('/providers/bottlenecks'),
  impact: () => request<ImpactData>('/providers/impact'),
  impactCsv: async () => (await raw('/providers/impact.csv')).blob(),
  award: (matchId: string, value: number) =>
    request<{ status: string; value: number }>(`/applications/${matchId}/award`, json('POST', { value })),
  inviteConsortium: (oppId: string) =>
    request<ConsortiumInvitation>(`/opportunities/${oppId}/consortium/invite`, json('POST')),
  consortia: () => request<ConsortiumInvite[]>('/consortia'),
  respondConsortium: (id: string, accept: boolean) =>
    request<{ status: string; my_response: string }>(`/consortia/${id}/respond`, json('POST', { accept })),
  dossier: (id: string) => request<DossierData>(`/matches/${id}/dossier`),

  feedbackAwaiting: () => request<AwaitingReview[]>('/feedback/awaiting'),
  feedbackGiven: () => request<FeedbackItem[]>('/feedback/given'),
  leaveFeedback: (applicationId: string, ratings: Record<string, number>, comment: string) =>
    request<{ id: string }>(`/feedback/${applicationId}`, json('POST', { ratings, comment: comment || null })),
  feedbackMine: () => request<{ items: FeedbackItem[]; performance: Performance }>('/feedback/mine'),
  respondFeedback: (id: string, text: string) => request<unknown>(`/feedback/${id}/respond`, json('POST', { text })),
  disputeFeedback: (id: string, text: string) => request<unknown>(`/feedback/${id}/dispute`, json('POST', { text })),
  feedbackDisputes: () => request<FeedbackItem[]>('/feedback/disputes'),
  resolveFeedback: (id: string, decision: 'uphold' | 'remove', note: string) =>
    request<unknown>(`/feedback/${id}/resolve`, json('POST', { decision, note })),
  trackRecord: (smeId: string) => request<Performance>(`/feedback/performance/${smeId}`),
  readDocument: (id: string) => request<DocReading>(`/documents/${id}/extract`, json('POST')),
  setExpiry: (id: string, expiry_date: string) => request<Doc>(`/documents/${id}/expiry`, json('PUT', { expiry_date })),
  semantic: (matchId: string) => request<Semantic>(`/matches/${matchId}/semantic`),
  profileQuality: () => request<{ flags: { level: string; text: string }[] }>('/smes/me/quality'),
  ecosystem: () => request<Ecosystem>('/admin/ecosystem'),
  evaluation: () => request<Evaluation>('/meta/evaluation'),
  importOpportunities: (file: File, dryRun: boolean) => {
    const form = new FormData(); form.append('file', file)
    return request<ImportResult>(`/opportunities/import?dry_run=${dryRun}`, { method: 'POST', body: form })
  },
  searchOpportunities: (query: string) => request<SearchResult<OppHit>>('/smes/me/search', json('POST', { query })),
  searchSmes: (query: string) => request<SearchResult<SmeHit>>('/providers/search', json('POST', { query })),
  ingestKeys: () => request<IngestKey[]>('/ingest/keys'),
  createIngestKey: (name: string) => request<IngestKey & { key: string }>('/ingest/keys', json('POST', { name })),
  revokeIngestKey: (id: string) => request<IngestKey>(`/ingest/keys/${id}/revoke`, json('POST')),
  passport: () => request<PassportState>('/smes/me/passport'),
  passportAction: (kind: 'enable' | 'rotate' | 'disable') => request<PassportState>(`/smes/me/passport/${kind}`, json('POST')),
  publicPassport: (token: string) => request<PassportView>(`/passport/${encodeURIComponent(token)}`),
  mode: () => request<{ ai: 'local' | 'gemini' | 'anthropic' | 'off'; email: string }>('/meta/mode'),
  publicOpportunities: () => request<PublicCard[]>('/public/opportunities'),
  publicOpportunity: (id: string) => request<PublicDetail>(`/public/opportunities/${id}`),
  publicPreview: (id: string, body: PreviewBody) => request<PublicPreview>(`/public/opportunities/${id}/preview`, json('POST', body)),
  importTemplate: async () => (await raw('/opportunities/import/template')).blob(),

  queue: () => request<Queue>('/admin/queue'),
  reviewVerification: (id: string, decision: string) =>
    request<unknown>(`/admin/verifications/${id}/review`, json('POST', { decision })),
  reviewMatch: (id: string, decision: string) =>
    request<unknown>(`/admin/matches/${id}/review`, json('POST', { decision })),
}

export interface LoginResult {
  access_token?: string; role?: Role; mfa_required?: boolean; mfa_token?: string
}
export interface MfaSetup { secret: string; otpauth_uri: string; qr: string }
export interface NotificationBox {
  unread: number
  items: { id: string; title: string; body: string; link: string | null; created_at: string; read: boolean }[]
}
export type Role = 'sme' | 'corporate' | 'funder' | 'support' | 'admin'
export type Quadrant = 'award_now' | 'coachable' | 'ready_weak_fit' | 'develop'
export type Kind = 'procurement' | 'grant' | 'funding' | 'investor' | 'support'

export interface Me {
  id: string; email: string; full_name: string; role: Role; mfa_enabled: boolean
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
export interface UnlockResult {
  selected: { code: string; label: string; issuer: string; days: number; cost_zar: number }[]
  total_days: number
  total_cost_zar: number
  routes: { code: string; label: string; issuer: string; days: number; cost_zar: number; gain_value: number; newly_award_ready: number }[]
  before: { award_ready: number; value: number }
  after: { award_ready: number; value: number }
  opportunities: {
    opportunity_id: string; title: string; contract_value: number; newly_award_ready: boolean
    before: { quadrant: Quadrant; fit: number; readiness: number } | null
    after: { quadrant: Quadrant; fit: number; readiness: number }
  }[]
}
export interface UnlockMapData {
  rows: {
    credential: string; label: string; issuer: string; days: number; cost_zar: number
    smes_blocked: number; opportunities_blocked: number; value_locked: number; would_unlock: number
  }[]
  total_value_locked: number; smes_considered: number; opportunities_considered: number
}
export interface DossierData {
  generated_at: string; match_id: string; model_version: string; status: string
  opportunity: { title: string; kind: Kind; provider: string; contract_value: number; duration_months: number; payment_terms_days: number; deadline: string | null }
  sme: { name: string; verification_status: string }
  rules: { type: string; value: Record<string, unknown>; mandatory: boolean; weight: number }[]
  result: { gate: string; quadrant: Quadrant; fit: number; readiness: number; components: Record<string, number> | null; gaps: Gap[] | null; risk_flags: RiskFlags }
  verifications: Verification[]
  decisions: { action: string; at: string; by_role: string | null; by_organisation: string | null; snapshot: { fit: number; readiness: number; quadrant: Quadrant } | null }[]
  matches_decision_snapshot: boolean | null
}
export interface ImpactData {
  applications: number; awards: number; smes_awarded: number; value_awarded: number; conversion_pct: number
  days_to_award_median: number | null; days_to_award_mean: number | null
  awarded_despite_gap: { awards: number; value: number; meaning: string }
  ownership: Record<'youth' | 'black' | 'black_women', { awards: number; value: number; share_pct: number }>
  by_province: { name: string; value: number }[]; by_sector: { name: string; value: number }[]
}
export interface ConsortiumInvitation {
  id: string; status: 'proposed' | 'formed' | 'declined'; coverage_pct: number
  members: { sme_id: string; name: string; role: string; scope: string[]; response: 'pending' | 'accepted' | 'declined' }[]
}
export interface ConsortiumInvite {
  id: string; status: 'proposed' | 'formed' | 'declined'
  opportunity: { id: string; title: string; contract_value: number; provider: string }
  my_role: string; my_part: string[]; my_response: 'pending' | 'accepted' | 'declined'
  partners: number; accepted: number; coverage_pct: number; partner_names: string[]
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
const ACRONYM: Record<string, string> = { ict: 'ICT', bbbee: 'B-BBEE', csd: 'CSD', cidb: 'CIDB' }
export const pretty = (s: string) =>
  s.split('_').map((w, k) => ACRONYM[w.toLowerCase()] ?? (k === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(' ')
export const dateFmt = (s: string | null) =>
  s ? new Date(s).toLocaleDateString('en-ZA', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const daysUntil = (s: string | null) =>
  s ? Math.ceil((new Date(s).getTime() - Date.now()) / 86400000) : null

export const KIND_LABEL: Record<Kind, string> = {
  procurement: 'Procurement', grant: 'Grant', funding: 'Funding', investor: 'Investment', support: 'Business support',
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

export interface AwaitingReview { application_id: string; sme: string; opportunity: string; awarded_value: number; awarded_at: string }
export interface FeedbackItem {
  id: string; sme: string; provider: string; ratings: Record<string, number>; comment: string | null
  status: 'published' | 'responded' | 'disputed' | 'upheld' | 'removed'
  response: string | null; dispute_reason: string | null; resolution_note: string | null; created_at: string
}
export interface Performance {
  reviews: number; reliable: boolean; overall: number | null
  criteria: { key: string; label: string; average: number | null }[]
  disputed_open: number; responded: number
  summary: null | { source: 'ai' | 'figures'; summary: string; strengths: string[]; development_areas: string[] }
}
export interface DocReading {
  source: 'ai' | 'local' | 'unavailable'; provider?: string
  draft: null | {
    document_type: string | null; company_name: string | null; registration_number: string | null
    issuer: string | null; expiry_date: string | null; sector: string | null; province: string | null
    annual_turnover: number | null; years_trading: number | null; capability_codes: string[]
  }
  checks: { level: 'ok' | 'warn' | 'info'; text: string }[]
}
export interface Semantic {
  source: 'ai' | 'local' | 'keywords'; score: number; matched_themes: string[]; concerns: string[]
  rationale: string; advisory: string; embedding_similarity?: number
}
export interface ImportResult { rows: number; created: number; errors: { row: number; error: string }[]; titles: string[] }
export interface Ecosystem {
  totals: { businesses: number; youth_owned: number; opportunities: number; open_value: number; matches: number; applications: number; awards: number; awarded_value: number }
  funnel: { stage: string; count: number }[]
  sectors: { sector: string; businesses: number | string; opportunities: number | string; value: number; pressure: number }[]
  provinces: { province: string; businesses: number | string; opportunities: number | string }[]
  skills: { code: string; label: string; requested: number; businesses: number; shortfall: boolean }[]
  underserved: { label: string; requested: number; businesses: number }[]
  credential_gaps: { label: string; matches_blocked: number }[]
  quadrants: Record<string, number>
  quality: { reviews: number; criteria: { key: string; label: string; average: number | null }[] }
  employment: { jobs_potential: number; assumption: string }
}
export interface Evaluation {
  model_version: string
  data: { source: string; businesses: number; opportunities: number; personal_data: boolean }
  scenarios: { passed: number; total: number; items: { name: string; ok: boolean }[] }
  benchmark: {
    opportunities: number; businesses: number; rubric: string
    methods: { method: string; ndcg_at_5: number; precision_at_3: number }[]
    relevant_pairs: number; relevant_excluded_by_gates: number
  }
  determinism: { identical: boolean; fingerprint: string; runs: number }
  robustness: { perturbation: string; trials: number; top3_overlap: number; quadrant_stable: number }
  fairness: {
    counterfactual_pairs: number; scores_changed_by_ownership: number; disclosed_max_fit_effect: number
    groups: { group: string; businesses: number; kept_rate: number; award_ready_rate: number }[]
    disparate_impact: { attribute: string; ratio: number; within_four_fifths: boolean }[]
    note: string
  }
  limitations: string[]; human_oversight: string[]
}

export interface SearchResult<T> { source: 'embeddings' | 'keywords'; results: T[] }
export interface OppHit {
  opportunity_id: string; title: string; kind: Kind; sector: string; province: string; contract_value: number
  similarity: number; match: null | { match_id: string; quadrant: Quadrant; fit: number; readiness: number }
}
export interface SmeHit {
  sme_id: string; name: string; sector: string; province: string; years_trading: number
  verification_status: string; similarity: number
}
export interface IngestKey { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked: boolean }

export interface PassportView {
  name: string; sector: string | null; province: string | null; years_trading: number | null
  capabilities: string[]; checks: { label: string; ok: boolean; source: string }[]
  credentials: { label: string; status: string; expires: string | null }[]; credentials_valid: number
  track_record: { reviews: number; overall: number | null; reliable: boolean }
  as_of: string; notice: string
}
export interface PassportState { enabled: boolean; link: string | null; qr: string | null; preview: PassportView }

export interface PublicCard {
  id: string; title: string; kind: Kind; sector: string; province: string; contract_value: number
  deadline: string | null; provider: string | null
}
export interface PublicDetail extends PublicCard {
  description: string | null; duration_months: number; payment_terms_days: number
  scope: { label: string; value: number }[]
  requirements: { text: string; mandatory: boolean; kind: string; days?: number; cost_zar?: number }[]
  preference: string[]
}
export interface PreviewBody {
  sector: string; province: string; years_trading: number; annual_turnover: number
  capability_codes: string[]; documents: string[]
}
export interface PublicPreview {
  gate: 'pass' | 'remediable' | 'fail'; quadrant: Quadrant; fit: number; readiness: number
  components: Record<string, number>; gaps: Gap[]; risk: RiskFlags; fail_reasons: string[]; summary: string
  unlock: { days: number; cost_zar: number; documents: number }; stored: false
}
