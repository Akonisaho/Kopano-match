import { useRef, useState } from 'react'
import { api, dateFmt, pretty, type Doc, type DocReading, type ImportResult, type Semantic, type Performance } from '../api'
import { useLoad } from '../hooks'
import { PerformanceCard } from '../pages/Feedback'
import { Badge, Modal, Panel, Spinner, useToast } from '../ui'

const LEVEL_TONE: Record<string, string> = { ok: 'green', warn: 'amber', info: 'blue' }

/** AI reads one uploaded document. Opt-in per document, checked against the account, saved only on a click. */
export function ReadWithAi({ doc, onClose, onChanged }: { doc: Doc; onClose: () => void; onChanged: () => void }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<DocReading | null>(null)
  async function run() {
    setBusy(true)
    try { setRes(await api.readDocument(doc.id)) } catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  async function useExpiry(d: string) {
    try { await api.setExpiry(doc.id, d); toast('Expiry date updated.'); onChanged(); onClose() } catch (err) { toast((err as Error).message, 'error') }
  }
  async function fillProfile() {
    try {
      const cur = await api.profile()
      if (!cur.profile || !res?.draft) { toast('Complete your business profile first, then fill it from a document.', 'error'); return }
      const d = res.draft
      await api.saveProfile({
        ...cur.profile,
        sector: d.sector ?? cur.profile.sector,
        province: d.province ?? cur.profile.province,
        annual_turnover: d.annual_turnover ?? cur.profile.annual_turnover,
        years_trading: d.years_trading ?? cur.profile.years_trading,
        capability_codes: Array.from(new Set([...cur.profile.capability_codes, ...d.capability_codes])),
      })
      toast('Profile updated from the document.'); onChanged(); onClose()
    } catch (err) { toast((err as Error).message, 'error') }
  }
  const d = res?.draft
  const rows: [string, string | number | null | undefined][] = d ? [
    ['Document type', d.document_type], ['Company', d.company_name], ['Registration number', d.registration_number],
    ['Issuer', d.issuer], ['Expiry date', d.expiry_date ? dateFmt(d.expiry_date) : null], ['Sector', d.sector ? pretty(d.sector) : null],
    ['Province', d.province], ['Annual turnover', d.annual_turnover ? `R${d.annual_turnover.toLocaleString('en-ZA')}` : null],
    ['Years trading', d.years_trading], ['Capabilities', d.capability_codes.length ? d.capability_codes.join(', ') : null],
  ] : []
  const hasProfileFacts = !!d && (d.sector || d.province || d.annual_turnover || d.years_trading || d.capability_codes.length)
  return (
    <Modal onClose={onClose}>
      <h3 style={{ margin: '0 0 4px' }}>Read {doc.document_type} with AI</h3>
      {!res && <>
        <p className="hint">This sends the file to Google's Gemini service so it can read the text. Use it on sample or non-sensitive documents in this demo. The request is written to your audit log, and nothing is saved until you choose to.</p>
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy} onClick={run}>{busy ? 'Reading…' : 'Read this document'}</button></div></>}
      {res?.source === 'unavailable' && <><p className="callout amber">The AI reader is not available right now, so nothing was read. Nothing was changed. Try again in a moment.</p>
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}><button className="btn btn-outline" onClick={onClose}>Close</button></div></>}
      {res?.source === 'ai' && d && <>
        <p className="hint" style={{ marginTop: 0 }}>An AI draft. Check it against the document before you use it.</p>
        {res.checks.map((c, i) => <p key={i} className={`callout ${c.level === 'ok' ? 'green' : c.level === 'warn' ? 'amber' : 'gray'}`} style={{ margin: '0 0 8px', fontSize: 13 }}><Badge tone={LEVEL_TONE[c.level]}>{c.level === 'ok' ? 'Consistent' : c.level === 'warn' ? 'Check' : 'Note'}</Badge> {c.text}</p>)}
        <div className="table-wrap" style={{ margin: '12px 0' }}><table><tbody>{rows.map(([k, v]) => (
          <tr key={k}><td className="hint" style={{ width: 150 }}>{k}</td><td>{v ?? <span className="hint">not stated</span>}</td></tr>))}</tbody></table></div>
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
          {d.expiry_date && String(doc.expiry_date) !== d.expiry_date && <button className="btn btn-outline" onClick={() => useExpiry(d.expiry_date!)}>Use expiry {dateFmt(d.expiry_date)}</button>}
          {hasProfileFacts && <button className="btn btn-outline" onClick={fillProfile}>Add to my profile</button>}
          <button className="btn btn-primary" onClick={onClose}>Done</button></div></>}
    </Modal>
  )
}

/** Plain-rule checks on the business profile: incomplete, inconsistent or doubtful details. */
export function ProfileHealth() {
  const q = useLoad(() => api.profileQuality())
  if (!q.data) return null
  const flags = q.data.flags
  return (
    <Panel title="Profile health" right={<Badge tone={flags.some((f) => f.level === 'warn') ? 'amber' : 'green'}>{flags.length ? `${flags.length} to look at` : 'All clear'}</Badge>}>
      {flags.length ? flags.map((f, i) => <p key={i} className={`callout ${f.level === 'warn' ? 'amber' : 'gray'}`} style={{ margin: '0 0 8px', fontSize: 13 }}>{f.text}</p>)
        : <p className="hint" style={{ margin: 0 }}>Nothing looks inconsistent or missing.</p>}
      <p className="hint" style={{ marginBottom: 0 }}>Found by plain rules, not an AI verdict. They are prompts to check, never a reason to reject you.</p>
    </Panel>
  )
}

/** Advisory meaning check, run on request. It sits beside the score and never changes it. */
export function MeaningCheck({ matchId }: { matchId: string }) {
  const toast = useToast()
  const [s, setS] = useState<Semantic | null>(null)
  const [busy, setBusy] = useState(false)
  async function run() {
    setBusy(true)
    try { setS(await api.semantic(matchId)) } catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  return (
    <Panel title="Meaning check" sub="Reads the opportunity text and the business capabilities by meaning, not keywords."
      right={<Badge tone="purple">{s ? (s.source === 'ai' ? 'AI · advisory' : 'Keywords · advisory') : 'Advisory'}</Badge>}>
      {!s && <><p className="hint" style={{ marginTop: 0 }}>It sees no business name, no ownership and no size. It sits beside the score and never changes a score, a gate or a shortlist.</p>
        <button className="btn btn-outline" disabled={busy} onClick={run}>{busy ? 'Reading…' : 'Run the meaning check'}</button></>}
      {s && <>
        <div className="perf-head"><b className="perf-score">{s.score}</b><span className="hint">out of 100 for meaning</span></div>
        {s.matched_themes.length > 0 && <p style={{ margin: '0 0 6px', fontSize: 13 }}><b>Matches on:</b> {s.matched_themes.join(', ')}</p>}
        {s.concerns.length > 0 && <p style={{ margin: '0 0 6px', fontSize: 13 }}><b>Worth checking:</b> {s.concerns.join(', ')}</p>}
        {s.rationale && <p style={{ margin: '0 0 6px', fontSize: 13 }}>{s.rationale}</p>}
        <p className="hint" style={{ marginBottom: 0 }}>{s.advisory}</p></>}
    </Panel>
  )
}

/** A buyer reads the track record of a business that chose to be visible. */
export function TrackRecord({ smeId }: { smeId: string }) {
  const t = useLoad<Performance>(() => api.trackRecord(smeId), [smeId])
  if (t.error) return null
  if (!t.data) return <Spinner />
  return <PerformanceCard p={t.data} />
}

/** Bulk-load opportunities from a CSV export. Checked first, all or nothing. */
export function ImportPanel({ onImported }: { onImported?: () => void }) {
  const toast = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [res, setRes] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  async function go(dry: boolean) {
    if (!file) return
    setBusy(true)
    try {
      const r = await api.importOpportunities(file, dry)
      setRes(r)
      if (!dry) { toast(`${r.created} opportunities imported.`); setFile(null); if (input.current) input.current.value = ''; onImported?.() }
    } catch (err) {
      toast((err as Error).message === 'Something went wrong' ? 'Nothing was imported. Fix the rows below.' : (err as Error).message, 'error')
      try { setRes(await api.importOpportunities(file, true)) } catch { /* the toast already said it */ }
    } finally { setBusy(false) }
  }
  async function template() {
    const url = URL.createObjectURL(await api.importTemplate())
    const a = document.createElement('a'); a.href = url; a.download = 'opportunities-template.csv'; a.click(); URL.revokeObjectURL(url)
  }
  return (
    <Panel title="Import from your procurement system" sub="Export your opportunities as CSV and upload them here. Rows are checked first, and nothing is imported if any row has a problem.">
      <div className="table-actions" style={{ flexWrap: 'wrap' }}>
        <input ref={input} type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setRes(null) }} />
        <button className="btn btn-outline btn-small" disabled={!file || busy} onClick={() => go(true)}>Check file</button>
        <button className="btn btn-primary btn-small" disabled={!file || busy} onClick={() => go(false)}>Import</button>
        <button className="btn btn-outline btn-small" onClick={template}>Download template</button>
      </div>
      {res && res.errors.length === 0 && <p className="callout green" style={{ marginBottom: 0 }}>{res.created ? `Imported ${res.created}` : `${res.rows} row${res.rows === 1 ? '' : 's'} look good`}: {res.titles.slice(0, 4).join(', ')}{res.titles.length > 4 ? '…' : ''}</p>}
      {res && res.errors.length > 0 && <div className="callout amber" style={{ marginBottom: 0 }}>{res.errors.map((e) => <div key={e.row}>Row {e.row}: {e.error}</div>)}</div>}
    </Panel>
  )
}
