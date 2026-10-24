import { useState } from 'react'
import { api, dateFmt, type EnfCase, type EnfStatus } from '../api'
import { useLoad } from '../hooks'
import { Badge, Modal, Panel, Spinner, Welcome, useToast } from '../ui'

const TONE: Record<string, string> = {
  clear: 'green', monitoring: 'blue', flagged: 'amber', under_review: 'amber', restricted: 'amber',
  suspended: 'red', blacklisted: 'red', reinstated: 'green', open: 'amber', recommended: 'purple', closed: 'gray',
}
const SEV: Record<string, string> = { low: 'gray', medium: 'amber', high: 'red', critical: 'red' }
const label = (s: string) => s.replace('_', ' ').replace(/^./, (c) => c.toUpperCase())
const TYPE: Record<string, string> = { sme: 'SME', corporate: 'Corporate', funder: 'Funder / investor', support: 'Business support' }

/** Shown to a suspended or restricted organisation. It sees its status and can appeal. Nothing else. */
export function StatusBanner() {
  const toast = useToast()
  const s = useLoad<EnfStatus>(() => api.enfStatus())
  const [text, setText] = useState('')
  if (!s.data || s.data.status === 'clear') return null
  const blocked = s.data.status === 'suspended' || s.data.status === 'blacklisted'
  async function send() {
    try { await api.enfAppeal(text); toast('Appeal sent. A reviewer will look at it.'); setText(''); s.reload() }
    catch (err) { toast((err as Error).message, 'error') }
  }
  return (
    <div className={`enf-banner ${blocked ? 'red' : 'amber'}`} role="alert">
      <b>{blocked ? 'ACCOUNT TEMPORARILY SUSPENDED' : 'SOME ACTIONS ARE RESTRICTED'}</b>
      <p>{s.data.message ?? 'Some actions on your account are restricted while a trust and safety matter is reviewed.'}</p>
      {s.data.restrictions && s.data.restrictions.length > 0 && <ul>{s.data.restrictions.map((r) => <li key={r}>{r}</li>)}</ul>}
      {s.data.reference && <p className="hint">Case reference <b className="mono">{s.data.reference}</b></p>}
      {s.data.appeal ? <p><b>Your appeal:</b> {label(s.data.appeal.status)}{s.data.appeal.note ? ` · ${s.data.appeal.note}` : ''}</p> : (
        <div className="enf-appeal">
          <textarea rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Explain why you think this is a mistake, or send the information we asked for." />
          <button className="btn btn-primary btn-small" disabled={text.trim().length < 10} onClick={send}>Submit an appeal</button>
        </div>)}
    </div>
  )
}

function NewCase({ org, onClose, onDone }: { org: { id: string; name: string }; onClose: () => void; onDone: (c: EnfCase) => void }) {
  const toast = useToast()
  const opt = useLoad(() => api.enfOptions())
  const [reasons, setReasons] = useState<string[]>([])
  const [severity, setSeverity] = useState('medium')
  const [notes, setNotes] = useState('')
  const [kind, setKind] = useState('')
  const [ev, setEv] = useState('')
  async function go() {
    try {
      const c = await api.enfOpen({ organisation_id: org.id, reasons, severity, notes, evidence: kind && ev ? [{ kind, note: ev }] : [] })
      toast('Case opened. The entity is now under review.'); onDone(c)
    } catch (err) { toast((err as Error).message, 'error') }
  }
  return (
    <Modal onClose={onClose}><div className="modal-pad">
      <h3 style={{ margin: '0 0 4px' }}>Open a case on {org.name}</h3>
      <p className="hint" style={{ marginTop: 0 }}>Opening a case does not accuse anyone. It starts a review with evidence and a decision by a person.</p>
      {!opt.data ? <Spinner /> : <>
        <fieldset className="enf-reasons"><legend>Reasons</legend>
          {Object.entries(opt.data.reasons).map(([k, l]) => (
            <label key={k}><input type="checkbox" checked={reasons.includes(k)} onChange={(e) => setReasons(e.target.checked ? [...reasons, k] : reasons.filter((x) => x !== k))} /> {l}</label>))}
        </fieldset>
        <label className="field">Risk severity
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
        <label className="field">What was seen
          <textarea rows={3} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Facts only. Leave out personal details that are not needed." /></label>
        <div className="rv-grid">
          <label className="field">Evidence type<input value={kind} onChange={(e) => setKind(e.target.value)} placeholder="Document check" /></label>
          <label className="field" style={{ gridColumn: 'span 2' }}>Evidence<input value={ev} onChange={(e) => setEv(e.target.value)} placeholder="Same file hash as another organisation" /></label>
        </div>
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!reasons.length || notes.trim().length < 5} onClick={go}>Open case</button></div></>}
    </div></Modal>
  )
}

function CaseView({ id, onChange }: { id: string; onChange: () => void }) {
  const toast = useToast()
  const c = useLoad<EnfCase>(() => api.enfCase(id), [id])
  const opt = useLoad(() => api.enfOptions())
  const [note, setNote] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [evKind, setEvKind] = useState('')
  if (!c.data || !opt.data) return <Spinner />
  const x = c.data
  const severe = x.severity === 'high' || x.severity === 'critical'
  async function act(action: string, extra: Record<string, unknown> = {}) {
    try { await api.enfAct(id, { action, note, ...extra }); toast('Recorded in the audit log.'); setNote(''); c.reload(); onChange() }
    catch (err) { toast((err as Error).message, 'error') }
  }
  const ok = note.trim().length >= 3
  return (
    <Panel title={<>{x.organisation} <Badge tone={TONE[x.entity_status] ?? 'gray'}>{label(x.entity_status)}</Badge></>}
      sub={`${TYPE[x.org_type] ?? x.org_type} · case ${x.ref} · opened ${dateFmt(x.created_at)}`}
      right={<Badge tone={SEV[x.severity]}>{label(x.severity)} risk</Badge>}>
      <div className="enf-grid">
        <div><small>Reasons</small><b>{x.reasons.join(', ')}</b></div>
        <div><small>Verification</small><b>{label(x.verification_status)}</b></div>
        <div><small>Evidence</small><b>{x.evidence.length} item{x.evidence.length === 1 ? '' : 's'}</b></div>
        <div><small>Linked accounts</small><b>{x.linked?.length ? `${x.linked.length} to review` : 'None found'}</b></div>
      </div>
      {x.emergency && <div className="callout" style={{ background: '#fef2f2', color: '#991b1b', marginTop: 12 }}><b>Emergency suspension used.</b> {x.emergency_reason}<br /><small>It is a protective step, not a verdict. A reviewer must now review the case.</small></div>}
      {x.notes && <p className="quote">{x.notes}</p>}
      {x.evidence.map((e, i) => <p key={i} className="hint" style={{ margin: '4px 0' }}>· <b>{e.kind}:</b> {e.note}</p>)}
      {x.linked?.map((l) => <p key={l.id} className="hint" style={{ margin: '4px 0' }}>· Linked: <b>{l.name}</b> — {l.signal}. Flag for review, not a verdict.</p>)}
      {x.status === 'recommended' && <div className="callout purple" style={{ marginTop: 12 }}><b>Blacklist recommended by {x.recommended_by}.</b> A different administrator must approve it.</div>}

      <label className="field" style={{ marginTop: 16 }}>Note for the record (required for every action)
        <textarea rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you are taking this step" /></label>
      <div className="table-actions" style={{ flexWrap: 'wrap' }}>
        {severe && x.entity_status !== 'suspended' && x.entity_status !== 'blacklisted' && (
          <button className="btn-emergency" disabled={note.trim().length < 10} onClick={() => act('emergency_suspend')}>IMMEDIATE SUSPENSION</button>)}
        <button className="btn btn-outline btn-small" disabled={!ok} onClick={() => act('request_info')}>Request information</button>
        <button className="btn btn-outline btn-small" disabled={!ok} onClick={() => act('warn')}>Issue warning</button>
        <button className="btn btn-outline btn-small" disabled={!ok} onClick={() => act('suspend')}>Suspend account</button>
        {x.status === 'recommended'
          ? <><button className="btn btn-danger btn-small" disabled={note.trim().length < 10} onClick={() => act('approve_blacklist')}>Approve blacklist</button>
            <button className="btn btn-outline btn-small" disabled={!ok} onClick={() => act('reject_blacklist')}>Reject recommendation</button></>
          : <button className="btn btn-outline btn-small" disabled={note.trim().length < 10} onClick={() => act('recommend_blacklist')}>Recommend blacklist</button>}
        <button className="btn btn-outline btn-small" disabled={!ok} onClick={() => act('close')}>Close investigation</button>
        <button className="btn btn-primary btn-small" disabled={note.trim().length < 10} onClick={() => act('reinstate')}>Reinstate</button>
      </div>
      <details style={{ marginTop: 12 }}><summary>Restrict specific actions, or add evidence</summary>
        <div className="enf-reasons" style={{ marginTop: 8 }}>
          {Object.entries(opt.data.restrictions).map(([k, l]) => (
            <label key={k}><input type="checkbox" checked={picked.includes(k)} onChange={(e) => setPicked(e.target.checked ? [...picked, k] : picked.filter((p) => p !== k))} /> {l}</label>))}
        </div>
        <button className="btn btn-outline btn-small" style={{ marginTop: 8 }} disabled={!ok || !picked.length} onClick={() => act('restrict', { restrictions: picked })}>Restrict account</button>
        <div className="rv-grid" style={{ marginTop: 12 }}>
          <label className="field">Evidence type<input value={evKind} onChange={(e) => setEvKind(e.target.value)} placeholder="Document check" /></label>
        </div>
        <button className="btn btn-outline btn-small" disabled={!ok || evKind.length < 2} onClick={() => act('add_evidence', { evidence: { kind: evKind, note } })}>Add the note above as evidence</button>
      </details>
      {x.history && x.history.length > 0 && <>
        <h4 style={{ margin: '18px 0 6px' }}>Enforcement history</h4>
        <ol className="rv-timeline">{x.history.map((h, i) => (
          <li key={i}><span className="rv-year">{dateFmt(h.at)}</span><div><b>{label(h.action)}</b>
            <small>{label(h.from)} → {label(h.to)} · {h.by}{h.note ? ` · ${h.note}` : ''}</small></div></li>))}</ol></>}
    </Panel>
  )
}

/** Risk & enforcement for platform reviewers: investigate, restrict, suspend, appeal, reinstate. */
export function Enforcement() {
  const o = useLoad(() => api.enfOverview())
  const [q, setQ] = useState('')
  const [found, setFound] = useState<{ id: string; name: string; org_type: string; status: string; registration_number: string | null }[] | null>(null)
  const [creating, setCreating] = useState<{ id: string; name: string } | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const toast = useToast()
  if (!o.data) return <Spinner />
  async function search() {
    try { setFound(await api.enfSearch(q)) } catch (err) { toast((err as Error).message, 'error') }
  }
  const counts = o.data.counts
  return (
    <>
      <Welcome title="Risk & enforcement" text="Investigate, restrict and suspend with evidence and a recorded reason. A person decides every outcome. Severe cases can be suspended at once, then reviewed." />
      <div className="enf-counts">{['under_review', 'flagged', 'restricted', 'suspended', 'blacklisted', 'reinstated'].map((s) => (
        <div key={s}><b>{counts[s] ?? 0}</b><span>{label(s)}</span></div>))}</div>
      <Panel title="Find an entity" sub="Search by organisation name, registration number, or a person's name, email or phone.">
        <div className="table-actions">
          <input aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && q.length >= 2 && search()} placeholder="Name, registration number, email or phone" style={{ flex: 1, border: '1px solid #d7deea', borderRadius: 9, padding: '9px 11px' }} />
          <button className="btn btn-primary" disabled={q.length < 2} onClick={search}>Search</button></div>
        {found && (found.length ? <div className="table-wrap" style={{ marginTop: 10 }}><table>
          <thead><tr><th>Entity</th><th>Type</th><th>Registration</th><th>Status</th><th /></tr></thead>
          <tbody>{found.map((f) => (
            <tr key={f.id}><td><b>{f.name}</b></td><td>{TYPE[f.org_type] ?? f.org_type}</td><td className="mono">{f.registration_number ?? '–'}</td>
              <td><Badge tone={TONE[f.status] ?? 'gray'}>{label(f.status)}</Badge></td>
              <td><button className="btn btn-outline btn-small" onClick={() => setCreating({ id: f.id, name: f.name })}>Open case</button></td></tr>))}</tbody>
        </table></div> : <p className="hint" style={{ margin: '10px 0 0' }}>Nobody found.</p>)}
      </Panel>
      <Panel title="Cases" sub="Newest activity first. Opening a case does not accuse anyone.">
        {o.data.cases.length ? <div className="table-wrap"><table>
          <thead><tr><th>Entity</th><th>Type</th><th>Reasons</th><th>Severity</th><th>Entity status</th><th>Case</th><th /></tr></thead>
          <tbody>{o.data.cases.map((c) => (
            <tr key={c.id}><td><b>{c.organisation}</b>{c.emergency && <><br /><Badge tone="red">Emergency</Badge></>}</td><td>{TYPE[c.org_type] ?? c.org_type}</td>
              <td>{c.reasons.join(', ')}</td><td><Badge tone={SEV[c.severity]}>{label(c.severity)}</Badge></td>
              <td><Badge tone={TONE[c.entity_status] ?? 'gray'}>{label(c.entity_status)}</Badge></td>
              <td><Badge tone={TONE[c.status] ?? 'gray'}>{label(c.status)}</Badge></td>
              <td><button className="btn btn-primary btn-small" onClick={() => setOpen(c.id)}>Open</button></td></tr>))}</tbody>
        </table></div> : <div className="empty"><strong>No cases</strong>Search for an entity above to open one.</div>}
      </Panel>
      {open && <CaseView key={open} id={open} onChange={o.reload} />}
      {o.data.appeals.length > 0 && (
        <Panel title="Appeals" sub="A different reviewer should decide where there is one.">
          {o.data.appeals.map((a) => <AppealRow key={a.id} a={a} onDone={o.reload} />)}
        </Panel>)}
      {creating && <NewCase org={creating} onClose={() => setCreating(null)} onDone={(c) => { setCreating(null); setFound(null); o.reload(); setOpen(c.id) }} />}
    </>
  )
}

function AppealRow({ a, onDone }: { a: { id: string; organisation: string; text: string; status: string; decision_note: string | null; created_at: string }; onDone: () => void }) {
  const toast = useToast()
  const [note, setNote] = useState('')
  async function decide(d: string) {
    try { await api.enfDecideAppeal(a.id, d, note); toast('Decision recorded.'); setNote(''); onDone() }
    catch (err) { toast((err as Error).message, 'error') }
  }
  const pending = a.status === 'submitted' || a.status === 'more_info'
  return (
    <div className="feedback-card">
      <div style={{ display: 'flex', justifyContent: 'space-between' }}><b>{a.organisation}</b><Badge tone={pending ? 'amber' : a.status === 'approved' ? 'green' : 'gray'}>{label(a.status)}</Badge></div>
      <p className="quote">{a.text}</p>
      {a.decision_note && <p className="quote reply"><b>Decision:</b> {a.decision_note}</p>}
      {pending && <>
        <input aria-label="Decision note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason for your decision" style={{ width: '100%', border: '1px solid #d7deea', borderRadius: 9, padding: '8px 10px' }} />
        <div className="table-actions" style={{ marginTop: 8 }}>
          <button className="btn btn-primary btn-small" disabled={note.trim().length < 3} onClick={() => decide('approve')}>Approve and reinstate</button>
          <button className="btn btn-outline btn-small" disabled={note.trim().length < 3} onClick={() => decide('more_info')}>Ask for more information</button>
          <button className="btn btn-outline btn-small" disabled={note.trim().length < 3} onClick={() => decide('reject')}>Reject</button></div></>}
    </div>
  )
}
