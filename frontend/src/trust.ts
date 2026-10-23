// Each control is marked in place or roadmap. Keep this list true to the code.
export interface Control { i: string; t: string; ok: boolean; d: string }

export const TRUST: Control[] = [
  { i: 'ID', t: 'Identity checks', ok: true, d: 'ID last four digits and a selfie go to the identity provider adapter. The image is discarded; only the outcome is stored. Today the provider is a labelled mock.' },
  { i: 'ORG', t: 'Registry and tax checks', ok: true, d: 'Registration and tax status run through adapters. Failures route to a human reviewer instead of silently rejecting the SME. Live CIPC and SARS adapters are next.' },
  { i: 'DOC', t: 'Document security', ok: true, d: 'Type, size and magic-byte checks, SHA-256 duplicate detection across organisations, expiry checks, and files served only through an authenticated endpoint.' },
  { i: 'LOG', t: 'Tamper-proof audit', ok: true, d: 'Every state change is logged. The application database role has no UPDATE or DELETE on the audit table, so it cannot rewrite its own trail.' },
  { i: 'ACC', t: 'Role and object access', ok: true, d: 'Deny-by-default roles, and every read is scoped to the caller’s organisation. One SME cannot read another’s documents or matches.' },
  { i: 'POPIA', t: 'Your data, your control', ok: true, d: 'Consent is recorded with its version. Export everything held about you as JSON, or erase your account by anonymisation while the audit trail survives.' },
  { i: 'MFA', t: 'MFA and rate limiting', ok: false, d: 'Multi-factor sign-in, login rate limiting and password reset are not built yet.' },
  { i: 'AV', t: 'Malware scanning', ok: false, d: 'Uploads are validated but not yet scanned by an antivirus engine. Encryption at rest and managed key storage are also on the roadmap.' },
]
