import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import {
  api, dateFmt, daysUntil, isProvider, KIND_LABEL, pretty, zar,
  type Doc, type Gap, type Kind, type Profile, type ProfileResponse, type Taxonomy, type UnlockResult, type Verification,
} from '../api'
import { useAuth } from '../auth'
import { ProfileHealth, ReadWithAi, SemanticSearch } from '../components/AiPanels'
import { PassportCard } from '../components/PassportCard'
import { useLoad } from '../hooks'
import {
  Badge, ErrorNote, Logo, MiniBar, Panel, QuadrantBadge, ScoreRing, Spinner, VerificationRow, Welcome, useToast,
} from '../ui'

/* ------------------------------------------------------------------ helpers */

/** Latest result per check, so the status list shows the current state of each. */
function latestChecks(vs: Verification[]) {
  const pick = (type: string, provider?: string) =>
    vs.find((v) => v.subject_type === type && (!provider || v.provider === provider)) // list is newest first
  return [
    { key: 'registry', label: 'Company registration', note: 'Registry adapter', v: pick('organisation', 'registry') },
    { key: 'tax', label: 'Tax compliance status', note: 'Tax authority adapter', v: pick('organisation', 'tax') },
    { key: 'identity', label: 'Representative identity', note: 'ID digits and selfie, image discarded', v: pick('identity') },
  ]
}
const isOk = (v?: Verification) => !!v && (v.result === 'verified' || v.review_status === 'approved')

function CheckRow({ label, note, v }: { label: string; note: string; v?: Verification }) {
  if (!v) return (
    <div className="verify-row"><span className="check-circle idle">·</span><div><b>{label}</b><small>{note}</small></div><Badge tone="gray">Not started</Badge></div>
  )
  return <VerificationRow v={v} />
}

/* ------------------------------------------------------------------ overview */

/** One concrete thing to do now, picked by what moves the SME closest to an award. */
function nextStep(
  p: ProfileResponse,
  checks: ReturnType<typeof latestChecks>,
  gaps: { label: string; issuer: string; days: number; cost_zar: number; also_unlocks: number; blocks: string[] }[],
  best: { opportunity: string; status: string } | undefined,
  applications: number,
): { title: string; text: string; cta: string; to?: string } {
  if (!p.completion.steps[0].done)
    return { title: 'Describe what your business delivers', text: 'Your profile is the input to every match. It takes two minutes.', cta: 'Complete profile', to: '/app/profile' }
  if (!isOk(checks.find((c) => c.key === 'identity')?.v))
    return { title: 'Run your identity check', text: 'Providers trust verified businesses more. Only the outcome is stored, never the image.', cta: 'Verify identity', to: '/app/verification' }
  if (!p.completion.steps[3].done)
    return { title: 'Upload your first compliance document', text: 'A tax compliance PIN is the most commonly required document.', cta: 'Upload a document', to: '/app/documents' }
  const g = gaps.slice().sort((a, b) => b.also_unlocks - a.also_unlocks || a.days - b.days)[0]
  if (g)
    return { title: `Get your ${g.label}`, text: `${g.issuer}: about ${g.days} days${g.cost_zar ? ` and ${zar(g.cost_zar)}` : ' at no cost'}. It clears a blocker on ${g.blocks.length} of your matches${g.also_unlocks ? ` and unlocks ${g.also_unlocks} more opportunities` : ''}.`, cta: 'Upload it', to: '/app/documents' }
  if (best && applications === 0)
    return { title: `Apply to ${best.opportunity}`, text: 'You are ready for your best match. Applying takes one click.', cta: 'See opportunities', to: '/app/opportunities' }
  return { title: 'You are all set', text: 'Keep documents current so you stay award-ready, and watch for new opportunities.', cta: 'Browse opportunities', to: '/app/opportunities' }
}

export function SmeOverview() {
  const { me } = useAuth()
  const prof = useLoad(() => api.profile())
  const dash = useLoad(() => api.smeDashboard().catch(() => null))
  const apps = useLoad(() => api.applications())
  if (prof.loading || dash.loading) return <Spinner />
  if (prof.error) return <ErrorNote error={prof.error} />
  if (prof.data && !prof.data.profile) return <Navigate to="/onboarding" replace />
  const p = prof.data!
  const matches = dash.data?.matches ?? []
  const checks = latestChecks(p.verifications)
  const done = checks.filter((c) => isOk(c.v)).length
  const best = matches.slice().sort((a, b) => b.fit + b.readiness - (a.fit + a.readiness))[0]
  const step = nextStep(p, checks, dash.data?.open_gaps ?? [], best, apps.data?.length ?? 0)
  const first = me?.full_name.split(' ')[0] ?? ''
  const gaps = dash.data?.open_gaps ?? []
  const blocked = new Set(gaps.flatMap((g) => g.blocks))
  const locked = matches.filter((m) => blocked.has(m.opportunity)).reduce((sum, m) => sum + m.contract_value, 0)
  const journey: [string, boolean][] = [
    ['Profile', p.completion.percent >= 100], ['Verified', done === checks.length],
    ['Documents in order', gaps.length === 0], ['Applied', (apps.data?.length ?? 0) > 0],
  ]
  const firstOpen = journey.findIndex(([, ok]) => !ok)
  return (
    <>
      <section className="unlock-hero">
        <div>
          <small>{locked > 0 ? `${first}, this is waiting for you` : `Welcome, ${first}`}</small>
          {locked > 0
            ? <><h1>{zar(locked)}</h1><p>of opportunities are one step away. {step.title}.</p></>
            : <><h1>You are award ready</h1><p>{step.text}</p></>}
          {step.to && <Link className="btn btn-light" to={step.to}>{step.cta}</Link>}
        </div>
        {best && <div className="unlock-side"><ScoreRing value={best.fit} label="Fit" /><ScoreRing value={best.readiness} label="Ready" color="#f59e0b" /></div>}
      </section>
      <ol className="journey" aria-label="Your progress">
        {journey.map(([label, ok], i) => (
          <li key={label} className={ok ? 'done' : i === firstOpen ? 'now' : ''}><span>{ok ? '✓' : i + 1}</span>{label}</li>))}
      </ol>
      <div className="grid-2">
        <PassportCard />
        <Panel title="Best match" sub="Highest combined fit and readiness." right={best && <QuadrantBadge q={best.quadrant} />}>
          {best ? <>
            <h4 style={{ margin: '0 0 4px' }}>{best.opportunity}</h4>
            <p className="hint">{zar(best.contract_value)} · {best.gate === 'pass' ? 'All mandatory requirements met' : 'Mandatory documents outstanding'}</p>
            <Link className="btn btn-primary btn-full" style={{ marginTop: 12 }} to={`/app/matches/${best.match_id}`}>See why</Link>
          </> : <div className="empty"><strong>No matches yet</strong>Buyers run matching when they publish an opportunity.</div>}
        </Panel>
      </div>
      {dash.data && dash.data.open_gaps.length > 0 && <UnlockPlan gaps={dash.data.open_gaps} />}
      <Panel title="Top matches" right={<Link className="btn btn-outline btn-small" to="/app/opportunities">All opportunities</Link>}>
        {matches.length ? <div className="table-wrap"><table>
          <thead><tr><th>Opportunity</th><th>Value</th><th>Fit</th><th>Readiness</th><th>Position</th><th /></tr></thead>
          <tbody>{matches.slice(0, 5).map((m) => (
            <tr key={m.match_id}><td><b>{m.opportunity}</b></td><td>{zar(m.contract_value)}</td>
              <td className="mono">{m.fit}<MiniBar value={m.fit} /></td><td className="mono">{m.readiness}<MiniBar value={m.readiness} /></td>
              <td><QuadrantBadge q={m.quadrant} /></td><td><Link className="btn btn-outline btn-small" to={`/app/matches/${m.match_id}`}>View</Link></td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>No matches yet</strong></div>}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ unlock plan */

/** A what-if. Tick the documents you plan to get; the same rules re-score every opportunity. */
function UnlockPlan({ gaps }: { gaps: (Gap & { blocks: string[] })[] }) {
  const toast = useToast()
  const [picked, setPicked] = useState<string[]>(() => gaps.map((g) => g.credential))
  const [plan, setPlan] = useState<UnlockResult | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!picked.length) { setPlan(null); return }
    let live = true
    setBusy(true)
    api.simulate(picked).then((r) => live && setPlan(r)).catch((e) => toast((e as Error).message, 'error')).finally(() => live && setBusy(false))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picked.join(',')])

  const toggle = (c: string) => setPicked(picked.includes(c) ? picked.filter((x) => x !== c) : [...picked, c])
  const changed = plan?.opportunities.filter((o) => o.newly_award_ready || (o.before?.quadrant !== o.after.quadrant)) ?? []
  const gain = plan ? plan.after.value - plan.before.value : 0

  return (
    <Panel title="Your Unlock Plan" sub="Tick the documents you plan to get. The real rules re-score every opportunity. Nothing is saved." right={<Badge tone="purple">What if</Badge>}>
      <div className="grid-2" style={{ gridTemplateColumns: '1fr 1.2fr' }}>
        <div>
          {gaps.map((g) => (
            <label key={g.credential} className="check-row" style={{ alignItems: 'center', margin: '0 0 10px', padding: 12, border: '1px solid var(--line)', borderRadius: 12, background: picked.includes(g.credential) ? '#faf5ff' : '#fff' }}>
              <input type="checkbox" checked={picked.includes(g.credential)} onChange={() => toggle(g.credential)} />
              <span style={{ flex: 1 }}><b>{g.label}</b><br /><small className="hint">{g.issuer} · {g.days} days · {g.cost_zar ? zar(g.cost_zar) : 'no cost'}</small></span>
            </label>))}
        </div>
        <div>
          {!plan ? <div className="empty">{picked.length ? 'Working it out…' : 'Tick at least one document to see what it unlocks.'}</div> : <>
            <div className="delta" style={{ opacity: busy ? 0.6 : 1 }}>
              <small>Contract value you can be awarded</small>
              <div className="delta-row"><span>{zar(plan.before.value)}</span><i>→</i><b>{zar(plan.after.value)}</b>{gain > 0 && <em>+{zar(gain)}</em>}</div>
              <div className="delta-sub">{plan.before.award_ready} → {plan.after.award_ready} award-ready · {plan.total_days} days · {plan.total_cost_zar ? zar(plan.total_cost_zar) : 'no cost'}</div>
            </div>
            {plan.routes.length > 0 && plan.routes[0].gain_value > 0 && (
              <div className="callout purple" style={{ marginTop: 0, marginBottom: 12, background: '#faf5ff', color: '#4c1d95' }}>
                <b>Best first move: {plan.routes[0].label}.</b> On its own it opens {zar(plan.routes[0].gain_value)} of contracts in about {plan.routes[0].days} days
                ({plan.routes[0].issuer}{plan.routes[0].cost_zar ? `, ${zar(plan.routes[0].cost_zar)}` : ', no cost'}).</div>)}
            {changed.length > 0 ? <div className="table-wrap"><table>
              <thead><tr><th>Opportunity</th><th>Now</th><th>After</th></tr></thead>
              <tbody>{changed.map((o) => (
                <tr key={o.opportunity_id}><td><b>{o.title}</b><br /><small>{zar(o.contract_value)}</small></td>
                  <td>{o.before ? <QuadrantBadge q={o.before.quadrant} /> : <Badge tone="gray">Not matched</Badge>}</td>
                  <td><QuadrantBadge q={o.after.quadrant} />{o.newly_award_ready && <> <Badge tone="green">Newly award-ready</Badge></>}</td></tr>))}</tbody>
            </table></div> : <p className="hint">These documents do not change any opportunity's position.</p>}
          </>}
        </div>
      </div>
    </Panel>
  )
}

/* ------------------------------------------------------------------ profile */

const EMPTY: Profile = {
  sector: '', province: '', annual_turnover: 0, years_trading: 0, largest_past_contract: 0,
  capability_codes: [], ownership: [], visible_to_corporates: true,
}

export function ProfileForm({ initial, tax, onSaved, cta = 'Save profile' }: { initial: Profile | null; tax: Taxonomy; onSaved: () => void; cta?: string }) {
  const toast = useToast()
  const [p, setP] = useState<Profile>(initial ?? EMPTY)
  const [paste, setPaste] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const toggle = (l: string[], v: string) => (l.includes(v) ? l.filter((x) => x !== v) : [...l, v])

  async function save(e: FormEvent) {
    e.preventDefault(); setError(null); setBusy(true)
    try { await api.saveProfile(p); toast('Profile saved.'); onSaved() } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  async function draft() {
    setError(null)
    try {
      const { draft: d, source } = await api.extractProfile(paste)
      const clean = Object.fromEntries(Object.entries(d).filter(([, v]) => v !== null && !(Array.isArray(v) && v.length === 0)))
      setP({ ...p, ...clean })
      toast(source === 'llm' ? 'Draft filled from your text. Check every field before saving.' : 'Automatic reading is unavailable right now. Please fill the form by hand.', source === 'llm' ? 'success' : 'info')
    } catch (err) { setError((err as Error).message) }
  }

  return (
    <form onSubmit={save}>
      <ErrorNote error={error} />
      <details style={{ marginBottom: 18 }}><summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>Fill from a company profile (optional)</summary>
        <div className="field" style={{ marginTop: 10 }}><textarea rows={4} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder="Paste your company profile text here" />
          <span className="hint">Sent to an AI model to draft the fields. Do not paste ID numbers. Nothing is saved until you press save.</span></div>
        <button type="button" className="btn btn-outline btn-small" disabled={paste.length < 20} onClick={draft}>Draft the form</button></details>
      <div className="form-grid">
        <div className="field"><label htmlFor="sec">Sector</label>
          <select id="sec" required value={p.sector} onChange={(e) => setP({ ...p, sector: e.target.value })}><option value="">Choose…</option>{tax.sectors.map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select>
          <span className="hint">Used to score fit. Visible to providers you match with.</span></div>
        <div className="field"><label htmlFor="prov">Province</label>
          <select id="prov" required value={p.province} onChange={(e) => setP({ ...p, province: e.target.value })}><option value="">Choose…</option>{tax.provinces.map((s) => <option key={s}>{s}</option>)}</select></div>
        <div className="field"><label htmlFor="to">Annual turnover (R)</label>
          <input id="to" type="number" min={1} required value={p.annual_turnover || ''} onChange={(e) => setP({ ...p, annual_turnover: +e.target.value })} />
          <span className="hint">Used to flag contracts too large to carry safely.</span></div>
        <div className="field"><label htmlFor="yr">Years trading</label>
          <input id="yr" type="number" min={0} required value={p.years_trading} onChange={(e) => setP({ ...p, years_trading: +e.target.value })} /></div>
        <div className="field"><label htmlFor="lc">Largest past contract (R)</label>
          <input id="lc" type="number" min={0} value={p.largest_past_contract} onChange={(e) => setP({ ...p, largest_past_contract: +e.target.value })} /></div>
      </div>
      <div className="field"><span className="lbl">What you can deliver</span>
        <div className="cap-grid">{tax.capabilities.map((c) => (
          <label key={c.code}><input type="checkbox" checked={p.capability_codes.includes(c.code)} onChange={() => setP({ ...p, capability_codes: toggle(p.capability_codes, c.code) })} />{c.label} <small>{pretty(c.sector)}</small></label>))}</div></div>
      <div className="field"><span className="lbl">Ownership (optional)</span>
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>{tax.ownership.map((o) => (
          <label key={o} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}><input type="checkbox" checked={p.ownership.includes(o)} onChange={() => setP({ ...p, ownership: toggle(p.ownership, o) })} />{pretty(o)}</label>))}</div>
        <span className="hint">Special personal information. Only used to match a provider's stated transformation goal, and never listed in the directory.</span></div>
      <label className="check-row"><input type="checkbox" checked={p.visible_to_corporates} onChange={(e) => setP({ ...p, visible_to_corporates: e.target.checked })} />Let providers see my business in match results and the directory</label>
      <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : cta}</button>
    </form>
  )
}

export function SmeProfilePage() {
  const prof = useLoad(() => api.profile())
  const tax = useLoad(() => api.taxonomy())
  if (!prof.data || !tax.data) return <Spinner />
  const c = prof.data.completion
  return (
    <div className="grid-2" style={{ gridTemplateColumns: '2fr 1fr' }}>
      <Panel title="Business capability profile" sub="Structured data drives eligibility, matching and readiness.">
        <ProfileForm initial={prof.data.profile} tax={tax.data} onSaved={prof.reload} />
      </Panel>
      <div>
        <Panel title="Completion" right={<Badge tone={c.percent === 100 ? 'green' : 'amber'}>{c.percent}%</Badge>}>
          <div className="progress"><i style={{ width: `${c.percent}%` }} /></div>
          {c.steps.map((s) => <div key={s.label} className="verify-row"><span className={`check-circle ${s.done ? '' : 'idle'}`}>{s.done ? '✓' : '·'}</span><div><b>{s.label}</b></div><span /></div>)}
        </Panel>
        <ProfileHealth />
        <Panel title="Organisation"><p style={{ margin: 0, fontSize: 13 }}><b>{prof.data.organisation.name}</b><br /><span className="hint">Registration {prof.data.organisation.registration_number ?? 'not provided'}</span></p></Panel>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ verification */

export function IdentityCheck({ onDone }: { onDone: () => void }) {
  const toast = useToast()
  const [last4, setLast4] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); if (!file) return
    setError(null); setBusy(true)
    const form = new FormData(); form.append('id_last4', last4); form.append('selfie', file)
    try {
      const r = await api.verifyIdentity(form)
      toast(r.result === 'verified' ? 'Identity check passed.' : `Identity check: ${pretty(r.result)}. A reviewer will follow up.`, r.result === 'verified' ? 'success' : 'info')
      setFile(null); onDone()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit}>
      <ErrorNote error={error} />
      <div className="form-grid">
        <div className="field"><label htmlFor="l4">Last four digits of your ID number</label>
          <input id="l4" inputMode="numeric" pattern="\d{4}" maxLength={4} required value={last4} onChange={(e) => setLast4(e.target.value.replace(/\D/g, ''))} placeholder="1234" />
          <span className="hint">We never ask for or store the full number.</span></div>
        <div className="field"><label htmlFor="sf">Selfie (JPG or PNG)</label>
          <input id="sf" type="file" accept="image/png,image/jpeg" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <span className="hint">Sent to the identity provider and discarded. Only the outcome is kept.</span></div>
      </div>
      <button className="btn btn-primary" disabled={busy || !file || last4.length !== 4}>{busy ? 'Checking…' : 'Run identity check'}</button>
    </form>
  )
}

export function VerificationCentre() {
  const toast = useToast()
  const prof = useLoad(() => api.profile())
  const [busy, setBusy] = useState(false)
  if (!prof.data) return <Spinner />
  const p = prof.data
  const checks = latestChecks(p.verifications)
  const done = checks.filter((c) => isOk(c.v)).length
  async function refresh() {
    setBusy(true)
    try { const r = await api.reverify(); toast(`Registry and tax checks re-run: ${pretty(r.verification_status)}.`); prof.reload() }
    catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  return (
    <>
      <Welcome title="Verification centre" text="Verification is separate from matching, so trust decisions stay clear and auditable. Checks that do not pass go to a human reviewer, never a silent rejection."
        action={<button className="btn btn-primary" onClick={refresh} disabled={busy || !p.organisation.registration_number}>{busy ? 'Running…' : 'Re-run registry and tax checks'}</button>} />
      <div className="grid-2">
        <Panel title="Your verification status" right={<Badge tone={done === checks.length ? 'green' : 'amber'}>{done}/{checks.length} complete</Badge>}>
          {checks.map((c) => <CheckRow key={c.key} label={c.label} note={c.note} v={c.v} />)}
          {!p.organisation.registration_number && <div className="callout amber">Add a registration number to your organisation to run registry and tax checks.</div>}
        </Panel>
        <Panel title="Representative identity" sub="ID digits plus a selfie, through the identity provider adapter.">
          <IdentityCheck onDone={prof.reload} />
          <div className="callout blue"><b>Privacy by design:</b> the image is passed to the provider and discarded. We store the outcome, a confidence figure and the source label, nothing else. In this pilot the provider is a mock adapter and is labelled as one.</div>
        </Panel>
      </div>
      <Panel title="Full check history">{p.verifications.length ? p.verifications.map((v) => <VerificationRow key={v.id} v={v} />) : <div className="empty">No checks yet.</div>}</Panel>
    </>
  )
}

/* ------------------------------------------------------------------ documents */

export function DocumentUpload({ tax, onDone }: { tax: Taxonomy; onDone: () => void }) {
  const toast = useToast()
  const [type, setType] = useState('TCS')
  const [expiry, setExpiry] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); if (!file) return
    setError(null); setBusy(true)
    const form = new FormData(); form.append('document_type', type); form.append('file', file)
    if (expiry) form.append('expiry_date', expiry)
    try {
      const r = await api.upload(form)
      toast(r.verification === 'verified' ? 'Document uploaded and checked.' : `Uploaded. Check result: ${pretty(r.verification)}. A reviewer may follow up.`, r.verification === 'verified' ? 'success' : 'info')
      setFile(null); setExpiry(''); onDone()
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit}>
      <ErrorNote error={error} />
      <div className="form-grid">
        <div className="field"><label htmlFor="dt">Document type</label><select id="dt" value={type} onChange={(e) => setType(e.target.value)}>{tax.credentials.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}</select></div>
        <div className="field"><label htmlFor="ex">Expiry date</label><input id="ex" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} /><span className="hint">Expired documents count for 40% of readiness until renewed.</span></div>
      </div>
      <label className="upload-zone"><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <b>{file ? file.name : 'Choose a PDF, PNG or JPG'}</b><p>Maximum 5 MB. Type, size and content are checked, and a fingerprint detects reuse across businesses.</p></label>
      <button className="btn btn-primary" style={{ marginTop: 14 }} disabled={busy || !file}>{busy ? 'Uploading…' : 'Upload securely'}</button>
    </form>
  )
}

export function Documents() {
  const toast = useToast()
  const docs = useLoad(() => api.documents())
  const tax = useLoad(() => api.taxonomy())
  const [reading, setReading] = useState<Doc | null>(null)
  async function view(id: string) {
    try { window.open(URL.createObjectURL(await api.downloadDocument(id)), '_blank', 'noopener') }
    catch (err) { toast((err as Error).message, 'error') }
  }
  if (!tax.data) return <Spinner />
  return (
    <>
      <Welcome title="Documents" text="Files are security-sensitive evidence. Only your organisation and platform reviewers can open them, through an authenticated link." />
      <Panel title="Upload a document"><DocumentUpload tax={tax.data} onDone={docs.reload} /></Panel>
      <Panel title="Document register" right={<Badge tone="blue">Authenticated access only</Badge>}>
        {docs.data?.length ? <div className="table-wrap"><table>
          <thead><tr><th>Type</th><th>Issuer</th><th>Status</th><th>Expiry</th><th>Uploaded</th><th /></tr></thead>
          <tbody>{docs.data.map((d) => (
            <tr key={d.id}><td><b>{d.document_type}</b></td><td>{d.issuer}</td>
              <td><Badge tone={d.status === 'valid' ? 'green' : 'amber'}>{pretty(d.status)}</Badge></td>
              <td>{dateFmt(d.expiry_date)}</td><td>{dateFmt(d.uploaded_at)}</td>
              <td>{d.has_file ? <div className="table-actions"><button className="btn btn-outline btn-small" onClick={() => view(d.id)}>View</button><button className="btn btn-outline btn-small" onClick={() => setReading(d)}>Read with AI</button></div> : <span className="hint">Seeded record</span>}</td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>No documents yet</strong>Upload a tax compliance PIN or B-BBEE affidavit to improve your readiness.</div>}
      </Panel>
      {reading && <ReadWithAi doc={reading} onClose={() => setReading(null)} onChanged={docs.reload} />}
    </>
  )
}

/* ------------------------------------------------------------------ opportunities and applications */

export function SmeOpportunities() {
  const toast = useToast()
  const nav = useNavigate()
  const list = useLoad(() => api.smeOpportunities())
  const [kind, setKind] = useState<Kind | 'all'>('all')
  async function apply(matchId: string) {
    try { await api.apply(matchId); toast('Application submitted.'); list.reload() } catch (err) { toast((err as Error).message, 'error') }
  }
  if (!list.data) return <Spinner />
  const rows = list.data.filter((o) => kind === 'all' || o.kind === kind)
  const kinds = Array.from(new Set(list.data.map((o) => o.kind)))
  return (
    <>
      <Welcome title="Opportunities" text="Every open opportunity, with your own fit and readiness where you are eligible. Where you are not matched, a mandatory requirement is unmet." />
      <SemanticSearch mode="sme" />
      <div className="chips" style={{ marginBottom: 16 }}>
        {(['all', ...kinds] as (Kind | 'all')[]).map((k) => (
          <button key={k} className="chip" style={kind === k ? { background: '#4c1d95', color: '#fff', borderColor: '#4c1d95' } : undefined} onClick={() => setKind(k)}>{k === 'all' ? 'All' : KIND_LABEL[k]}</button>))}
      </div>
      <Panel>
        <div className="table-wrap"><table>
          <thead><tr><th>Opportunity</th><th>Type</th><th>Provider</th><th>Closes</th><th>Value</th><th>Fit</th><th>Readiness</th><th>Position</th><th /></tr></thead>
          <tbody>{rows.map((o) => {
            const left = daysUntil(o.deadline)
            return (
              <tr key={o.opportunity_id}>
                <td><b>{o.title}</b><br /><small>{pretty(o.sector)} · {o.province}</small></td>
                <td><Badge tone="purple">{KIND_LABEL[o.kind]}</Badge></td>
                <td>{o.provider}<br />{o.provider_status === 'verified' && <Badge tone="green">Verified provider</Badge>}</td>
                <td>{dateFmt(o.deadline)}{left !== null && left <= 14 && left >= 0 && <><br /><small style={{ color: '#b45309' }}>{left} days left</small></>}</td>
                <td>{zar(o.contract_value)}</td>
                {o.match ? <>
                  <td className="mono">{o.match.fit}<MiniBar value={o.match.fit} /></td><td className="mono">{o.match.readiness}<MiniBar value={o.match.readiness} /></td>
                  <td><QuadrantBadge q={o.match.quadrant} />{o.match.gap_count > 0 && <><br /><small>{o.match.gap_count} gap{o.match.gap_count > 1 ? 's' : ''} to close</small></>}</td>
                  <td><div className="table-actions">
                    <button className="btn btn-outline btn-small" onClick={() => nav(`/app/matches/${o.match!.match_id}`)}>Explain</button>
                    {o.match.application ? <Badge tone="blue">{pretty(o.match.application)}</Badge>
                      : o.match.status === 'rejected' ? <Badge tone="gray">Declined</Badge>
                      : <button className="btn btn-primary btn-small" onClick={() => apply(o.match!.match_id)}>Apply</button>}</div></td></> :
                  <td colSpan={4}><b style={{ fontSize: 12 }}>Not matched</b>{o.blockers.length > 0 && <ul className="blockers">{o.blockers.map((b) => <li key={b}>{b}</li>)}</ul>}</td>}
              </tr>)
          })}</tbody>
        </table></div>
      </Panel>
    </>
  )
}

export function Applications() {
  const { me } = useAuth()
  const apps = useLoad(() => api.applications())
  if (!me || !apps.data) return <Spinner />
  const provider = isProvider(me.role) || me.role === 'admin'
  return (
    <>
      <Welcome title="Applications" text={provider ? 'SMEs that applied to your opportunities. Open the match to see the full breakdown, then shortlist or reject.' : 'Track your applications. The provider’s decision updates the status here.'} />
      <Panel>
        {apps.data.length ? <div className="table-wrap"><table>
          <thead><tr><th>{provider ? 'SME' : 'Opportunity'}</th>{provider && <th>Opportunity</th>}<th>Fit</th><th>Readiness</th><th>Position</th><th>Status</th><th>Submitted</th><th /></tr></thead>
          <tbody>{apps.data.map((a) => (
            <tr key={a.id}><td><b>{provider ? a.sme : a.opportunity}</b></td>{provider && <td>{a.opportunity}</td>}
              <td className="mono">{a.fit}</td><td className="mono">{a.readiness}</td><td><QuadrantBadge q={a.quadrant} /></td>
              <td><Badge tone={a.status === 'shortlisted' ? 'green' : a.status === 'declined' ? 'red' : 'blue'}>{pretty(a.status ?? 'submitted')}</Badge></td>
              <td>{dateFmt(a.submitted_at)}</td><td><Link className="btn btn-outline btn-small" to={`/app/matches/${a.match_id}`}>Open</Link></td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>No applications yet</strong>{provider ? 'Applications appear here when SMEs apply.' : 'Open an opportunity you match and apply to start.'}</div>}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ onboarding */

export function Onboarding() {
  const nav = useNavigate()
  const { me, signOut } = useAuth()
  const prof = useLoad(() => api.profile())
  const tax = useLoad(() => api.taxonomy())
  const docs = useLoad(() => api.documents())
  const [step, setStep] = useState(1)
  if (!prof.data || !tax.data) return <div className="onboard-wrap"><Spinner /></div>
  const p = prof.data
  const checks = latestChecks(p.verifications)
  const canNext = step === 2 ? !!p.profile : true
  return (
    <div className="onboard-wrap"><div className="onboard-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Logo /><div style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Badge tone="purple">Step {step} of 4</Badge><button className="btn btn-ghost btn-small" onClick={() => { signOut(); nav('/') }}>Sign out</button></div></div>
      <div className="stepper">{[1, 2, 3, 4].map((i) => <i key={i} className={i < step ? 'done' : i === step ? 'active' : ''} />)}</div>
      {step === 1 && <>
        <h2 className="form-title">Welcome, {me?.full_name.split(' ')[0]}</h2>
        <p className="form-sub">Four short steps set you up for matching. Everything you enter is used for eligibility and readiness scoring, and nothing else.</p>
        <div className="callout blue" style={{ marginTop: 0 }}><b>{p.organisation.name}</b><br />Registration {p.organisation.registration_number ?? 'not provided'} · status {pretty(p.organisation.verification_status)}</div>
        <ul style={{ fontSize: 13, lineHeight: 1.9, color: '#475467' }}><li>Describe what your business delivers</li><li>Run identity, registry and tax checks</li><li>Upload a compliance document</li></ul></>}
      {step === 2 && <><h2 className="form-title">Build your capability profile</h2><p className="form-sub">These fields are the inputs to matching. Save to continue.</p>
        <ProfileForm initial={p.profile} tax={tax.data} onSaved={prof.reload} cta="Save and continue" /></>}
      {step === 3 && <><h2 className="form-title">Identity and organisation verification</h2><p className="form-sub">Checks that do not pass are reviewed by a person. Nobody is silently rejected.</p>
        {checks.filter((c) => c.key !== 'identity').map((c) => <CheckRow key={c.key} label={c.label} note={c.note} v={c.v} />)}
        <div style={{ marginTop: 18 }}><IdentityCheck onDone={prof.reload} /></div>
        {isOk(checks[2].v) && <div className="callout green">Identity verified.</div>}</>}
      {step === 4 && <><h2 className="form-title">Upload a compliance document</h2><p className="form-sub">A tax compliance PIN is the most commonly required. You can add more later.</p>
        <DocumentUpload tax={tax.data} onDone={docs.reload} />{docs.data?.length ? <div className="callout green">{docs.data.length} document{docs.data.length > 1 ? 's' : ''} on file.</div> : null}</>}
      <div className="onboard-actions">
        <button className="btn btn-outline" disabled={step === 1} onClick={() => setStep(step - 1)}>Back</button>
        {step < 4 ? <button className="btn btn-primary" disabled={!canNext} onClick={() => setStep(step + 1)}>Continue</button>
          : <button className="btn btn-primary" onClick={() => nav('/app')}>Finish onboarding</button>}
      </div>
    </div></div>
  )
}

export type { ProfileResponse }

/* ------------------------------------------------------------------ consortium invitations */

export function Consortia() {
  const toast = useToast()
  const list = useLoad(() => api.consortia())
  if (!list.data) return <Spinner />
  async function answer(id: string, accept: boolean) {
    try {
      const r = await api.respondConsortium(id, accept)
      toast(r.status === 'formed' ? 'Everyone accepted: the consortium is formed.' : accept ? 'Accepted. Waiting for your partners.' : 'Declined.', 'success')
      list.reload()
    } catch (err) { toast((err as Error).message, 'error') }
  }
  return (
    <>
      <Welcome title="Consortium invitations"
        text="When no single business can deliver a whole contract, a buyer can propose a group. You see your own part and how many partners there are. Partner names are shared only once everyone has accepted." />
      {list.data.length === 0 ? <Panel><div className="empty"><strong>No invitations</strong>If a buyer proposes you for a group bid, it appears here and in your notifications.</div></Panel>
        : list.data.map((c) => (
          <Panel key={c.id} title={c.opportunity.title} sub={`${c.opportunity.provider} · ${zar(c.opportunity.contract_value)}`}
            right={<Badge tone={c.status === 'formed' ? 'green' : c.status === 'declined' ? 'gray' : 'amber'}>{c.status === 'proposed' ? 'Waiting' : pretty(c.status)}</Badge>}>
            <p style={{ margin: '0 0 8px', fontSize: 13.5 }}><b>Your part{c.my_role === 'lead' ? ' (proposed lead)' : ''}:</b> {c.my_part.join(', ') || 'to be agreed'}</p>
            <p className="hint" style={{ margin: 0 }}>{c.partners} partner{c.partners === 1 ? '' : 's'} · {c.accepted} of {c.partners + 1} accepted · the group covers {c.coverage_pct}% of the scope</p>
            {c.status === 'formed' && <div className="callout green">Your partners: <b>{c.partner_names.join(', ')}</b></div>}
            {c.status === 'declined' && <div className="callout gray">A partner declined, so this proposal has lapsed.</div>}
            {c.status === 'proposed' && c.my_response === 'pending' && (
              <div className="table-actions" style={{ marginTop: 14 }}>
                <button className="btn btn-primary" onClick={() => answer(c.id, true)}>Accept</button>
                <button className="btn btn-outline" onClick={() => answer(c.id, false)}>Decline</button></div>)}
            {c.status === 'proposed' && c.my_response === 'accepted' && <div className="callout blue">You accepted. Waiting for the others.</div>}
          </Panel>))}
    </>
  )
}
