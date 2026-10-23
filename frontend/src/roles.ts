import type { Role } from './api'

export const ROLES: { key: Exclude<Role, 'admin'>; label: string; desc: string; points: string[] }[] = [
  { key: 'sme', label: 'SME', desc: 'Build a verified capability profile, see exactly what stands between you and each opportunity, and apply.',
    points: ['Readiness gaps with days and rand cost', 'Apply to matched opportunities', 'Your data, exportable and erasable'] },
  { key: 'corporate', label: 'Corporate / Buyer', desc: 'Post procurement opportunities as rules, and review ranked, explainable SME matches.',
    points: ['Requirements as weighted rules', 'Capacity-risk flags on every match', 'Consortium proposals when no one SME fits'] },
  { key: 'funder', label: 'Funder / Investor', desc: 'Publish grants, funding and investment programmes and find investment-ready businesses.',
    points: ['Ownership and turnover gates', 'Shortlists with audit trail', 'Human decides, system explains'] },
  { key: 'support', label: 'Business Support', desc: 'Connect SMEs to accelerators, mentoring and development programmes.',
    points: ['Match on readiness, not just size', 'See common bottlenecks', 'Track who applied and why'] },
]
