import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, dateFmt, pretty, QUADRANT_LABEL, zar, type Doc, type DocReading, type ImportResult, type OppHit, type Performance, type Semantic, type SmeHit } from '../api'
import { useLoad } from '../hooks'
import { useT } from '../i18n'
import { PerformanceCard } from '../pages/Feedback'
import { TrackRecordReviews } from './Reputation'
import { Badge, Modal, Panel, Spinner, useToast } from '../ui'
import { VoiceButton } from './Voice'

const LEVEL_TONE: Record<string, string> = { ok: 'green', warn: 'amber', info: 'blue' }

/** One uploaded document is read, checked against the account, and saved only on a click. */
export function ReadWithAi({ doc, onClose, onChanged, auto }: { doc: Doc; onClose: () => void; onChanged: () => void; auto?: boolean }) {
  const t = useT()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<DocReading | null>(null)
  const [filled, setFilled] = useState<string | null>(null)
  async function run() {
    setBusy(true)
    try {
      const r = await api.readDocument(doc.id)
      setRes(r)
      // Read on this computer and no date was typed: take it from the document
      if (auto && r.source === 'local' && r.draft?.expiry_date && !doc.expiry_date) {
        await api.setExpiry(doc.id, r.draft.expiry_date)
        setFilled(r.draft.expiry_date)
        onChanged()
      }
    } catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  const mode = useLoad(() => api.mode().catch(() => null))
  const here = mode.data?.ai === 'local'
  useEffect(() => { if (auto) run() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  async function useExpiry(d: string) {
    try { await api.setExpiry(doc.id, d); toast(t('Expiry date updated.')); onChanged(); onClose() } catch (err) { toast((err as Error).message, 'error') }
  }
  async function fillProfile() {
    try {
      const cur = await api.profile()
      if (!cur.profile || !res?.draft) { toast(t('Complete your business profile first, then fill it from a document.'), 'error'); return }
      const d = res.draft
      await api.saveProfile({
        ...cur.profile,
        sector: d.sector ?? cur.profile.sector,
        province: d.province ?? cur.profile.province,
        annual_turnover: d.annual_turnover ?? cur.profile.annual_turnover,
        years_trading: d.years_trading ?? cur.profile.years_trading,
        capability_codes: Array.from(new Set([...cur.profile.capability_codes, ...d.capability_codes])),
      })
      toast(t('Profile updated from the document.')); onChanged(); onClose()
    } catch (err) { toast((err as Error).message, 'error') }
  }
  const d = res?.draft
  const rows: [string, string | number | null | undefined][] = d ? [
    ['Document type', d.document_type], ['Company', d.company_name], ['Registration number', d.registration_number],
    ['Issuer', d.issuer], ['Expiry date', d.expiry_date ? dateFmt(d.expiry_date) : null], ['Sector', d.sector ? t(pretty(d.sector)) : null],
    ['Province', d.province], ['Annual turnover', d.annual_turnover ? `R${d.annual_turnover.toLocaleString('en-ZA')}` : null],
    ['Years trading', d.years_trading], ['Capabilities', d.capability_codes.length ? d.capability_codes.join(', ') : null],
  ] : []
  const hasProfileFacts = !!d && Boolean(d.sector || d.province || d.annual_turnover || d.years_trading || d.capability_codes.length)
  return (
    <Modal small onClose={onClose}><div className="modal-pad">
      <h3 style={{ margin: '0 0 4px' }}>{here ? t('Reading your {type}', { type: doc.document_type }) : t('Read {type} with AI', { type: doc.document_type })}</h3>
      {!res && <>
        {busy ? <div className="reading"><i /><span>{t('Reading the document and checking it against your account…')}</span></div>
          : <p className="hint">{here ? t('The file is read on this computer and is not sent anywhere. Nothing is saved until you choose to.') : t("This sends the file to Google's Gemini service so it can read the text. Use it on sample or non-sensitive documents in this demo. The request is written to your audit log, and nothing is saved until you choose to.")}</p>}
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onClose}>{t('Cancel')}</button>
          <button className="btn btn-primary" disabled={busy} onClick={run}>{busy ? t('Reading…') : t('Read this document')}</button></div></>}
      {res?.source === 'unavailable' && <><p className="callout amber">{here ? t('There is no readable text in this file (it may be a scan), so nothing was read. Type the details in instead.') : t('The AI reader is not available right now, so nothing was read. Nothing was changed. Try again in a moment.')}</p>
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}><button className="btn btn-outline" onClick={onClose}>{t('Close')}</button></div></>}
      {(res?.source === 'ai' || res?.source === 'local') && d && <>
        <p className="hint" style={{ marginTop: 0 }}>{res.source === 'local' ? t('Read on this computer, nothing sent anywhere. Check it against the document before you use it.') : t('An AI draft. Check it against the document before you use it.')}</p>
        {filled && <p className="callout green" style={{ margin: '0 0 8px', fontSize: 13 }}><Badge tone="green">{t('Filled in')}</Badge> {t('Expiry date {d}, taken from the document.', { d: dateFmt(filled) })}</p>}
        {res.checks.map((c, i) => <p key={i} className={`callout ${c.level === 'ok' ? 'green' : c.level === 'warn' ? 'amber' : 'gray'}`} style={{ margin: '0 0 8px', fontSize: 13 }}><Badge tone={LEVEL_TONE[c.level]}>{c.level === 'ok' ? t('Consistent') : c.level === 'warn' ? t('Check') : t('Note')}</Badge> {t(c.text)}</p>)}
        <div className="table-wrap" style={{ margin: '12px 0' }}><table><tbody>{rows.map(([k, v]) => (
          <tr key={k}><td className="hint" style={{ width: 150 }}>{t(k)}</td><td>{v ?? <span className="hint">{t('not stated')}</span>}</td></tr>))}</tbody></table></div>
        <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
          {d.expiry_date && String(doc.expiry_date) !== d.expiry_date && <button className="btn btn-outline" onClick={() => useExpiry(d.expiry_date!)}>{t('Use expiry {d}', { d: dateFmt(d.expiry_date) })}</button>}
          {hasProfileFacts && <button className="btn btn-outline" onClick={fillProfile}>{t('Add to my profile')}</button>}
          <button className="btn btn-primary" onClick={onClose}>{t('Done')}</button></div></>}
    </div></Modal>
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
      right={<Badge tone="purple">{s ? (s.source === 'ai' ? 'AI · advisory' : s.source === 'local' ? 'Local analysis · advisory' : 'Keywords · advisory') : 'Advisory'}</Badge>}>
      {!s && <><p className="hint" style={{ marginTop: 0 }}>It sees no business name, no ownership and no size. It sits beside the score and never changes a score, a gate or a shortlist.</p>
        <button className="btn btn-outline" disabled={busy} onClick={run}>{busy ? 'Reading…' : 'Run the meaning check'}</button></>}
      {s && <>
        <div className="perf-head"><b className="perf-score">{s.score}</b><span className="hint">out of 100 for meaning</span>
          {s.embedding_similarity !== undefined && <Badge tone="blue">Embedding similarity {s.embedding_similarity}%</Badge>}</div>
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
  return <><TrackRecordReviews smeId={smeId} /><PerformanceCard p={t.data} /></>
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


/** Describe it in your own words; results come back by meaning, with the rule-based position beside them. */
export function SemanticSearch({ mode }: { mode: 'sme' | 'provider' }) {
  const t = useT()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<{ source: string; hits: (OppHit | SmeHit)[] } | null>(null)
  async function go() {
    if (q.trim().length < 3) return
    setBusy(true)
    try {
      const r = mode === 'sme' ? await api.searchOpportunities(q) : await api.searchSmes(q)
      setRes({ source: r.source, hits: r.results })
    } catch (err) { toast((err as Error).message, 'error') } finally { setBusy(false) }
  }
  const isOpp = (h: OppHit | SmeHit): h is OppHit => 'opportunity_id' in h
  return (
    <Panel title={mode === 'sme' ? t('Find opportunities in your own words') : t('Find businesses in your own words')}
      sub={mode === 'sme' ? t('Describe what you do or what you are looking for. Results are ranked by meaning, and your eligibility is shown beside each one.')
        : t('Describe what you need. Only sector, location, years trading and capabilities are compared: no names, size or ownership.')}
      right={res && <Badge tone={res.source === 'embeddings' ? 'purple' : 'gray'}>{res.source === 'embeddings' ? t('Semantic search') : t('Keyword search')}</Badge>}>
      <form className="table-actions" style={{ flexWrap: 'nowrap' }} onSubmit={(e) => { e.preventDefault(); go() }}>
        <input style={{ flex: 1, minWidth: 0, border: '1px solid #d7deea', borderRadius: 11, padding: '11px 13px' }} maxLength={500} value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={mode === 'sme' ? t('e.g. we resurface roads and fix drainage in Gauteng') : t('e.g. a team that can build and maintain rural roads')} />
        <VoiceButton onText={setQ} />
        <button className="btn btn-primary" disabled={busy || q.trim().length < 3}>{busy ? t('Searching…') : t('Search')}</button>
      </form>
      {res && (res.hits.length ? <div style={{ marginTop: 14 }}>{res.hits.map((h) => (
        <div key={isOpp(h) ? h.opportunity_id : h.sme_id} className="metric-row" style={{ alignItems: 'flex-start' }}>
          <div style={{ minWidth: 0 }}>
            <b>{isOpp(h) ? h.title : h.name}</b>
            <div className="hint">{pretty(h.sector)} · {h.province}{isOpp(h) ? ` · ${zar(h.contract_value)}` : ` · ${h.years_trading} yrs`}</div>
            {isOpp(h) ? (h.match
              ? <small>{t('Your position:')} <Link to={`/app/matches/${h.match.match_id}`}>{QUADRANT_LABEL[h.match.quadrant]}</Link> (fit {h.match.fit}, readiness {h.match.readiness})</small>
              : <small className="hint">{t('Not matched: a mandatory requirement is unmet.')}</small>)
              : <Badge tone={h.verification_status === 'verified' ? 'green' : 'amber'}>{h.verification_status === 'verified' ? 'Verified' : 'In review'}</Badge>}
          </div>
          <div style={{ width: 110, flex: '0 0 auto', textAlign: 'right' }}><b className="mono">{h.similarity}%</b><div className="progress" style={{ height: 6 }} aria-hidden><i style={{ width: `${h.similarity}%` }} /></div></div>
        </div>))}
        <p className="hint" style={{ marginBottom: 0 }}>{t('Similarity says what to look at. It never decides who qualifies.')}</p></div>
        : <p className="hint">Nothing came back.</p>)}
    </Panel>
  )
}

/** A buyer's own system posts opportunities with a key. The key is shown once; only a hash is kept. */
export function IngestPanel() {
  const toast = useToast()
  const keys = useLoad(() => api.ingestKeys())
  const [name, setName] = useState('')
  const [fresh, setFresh] = useState<string | null>(null)
  async function create() {
    try { const k = await api.createIngestKey(name); setFresh(k.key); setName(''); keys.reload() } catch (err) { toast((err as Error).message, 'error') }
  }
  async function revoke(id: string) {
    try { await api.revokeIngestKey(id); toast('Key revoked. The feed has stopped.'); keys.reload() } catch (err) { toast((err as Error).message, 'error') }
  }
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return (
    <Panel title="Connect your procurement system" sub="Your system posts opportunities to the platform with an API key, and they are matched on arrival.">
      <form className="table-actions" style={{ flexWrap: 'nowrap' }} onSubmit={(e) => { e.preventDefault(); create() }}>
        <input style={{ flex: 1, minWidth: 0, border: '1px solid #d7deea', borderRadius: 11, padding: '11px 13px' }} maxLength={60} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name this connection, e.g. SAP export" />
        <button className="btn btn-primary" disabled={name.trim().length < 2}>Create key</button>
      </form>
      {fresh && <div className="callout green" style={{ marginTop: 12 }}>
        <b>Copy this key now. It is not shown again.</b>
        <pre style={{ margin: '8px 0', overflowX: 'auto', fontSize: 12 }}>{fresh}</pre>
        <pre style={{ margin: 0, overflowX: 'auto', fontSize: 12 }}>{`curl -X POST ${origin}/api/ingest/opportunities \\\n  -H "X-API-Key: ${fresh.slice(0, 10)}…" -H "Content-Type: application/json" \\\n  -d '{"opportunities":[{"title":"…","sector":"construction","province":"Gauteng",\n       "contract_value":900000,"duration_months":6,\n       "scope_items":[{"code":"CON-ROADS","value":900000}],"requirements":[]}]}'`}</pre></div>}
      {keys.data && keys.data.length > 0 && <div className="table-wrap" style={{ marginTop: 12 }}><table>
        <thead><tr><th>Name</th><th>Key</th><th>Last used</th><th /></tr></thead>
        <tbody>{keys.data.map((k) => (
          <tr key={k.id}><td>{k.name}</td><td className="mono">{k.prefix}…</td><td>{k.last_used_at ? dateFmt(k.last_used_at) : 'never'}</td>
            <td>{k.revoked ? <Badge tone="gray">Revoked</Badge> : <button className="btn btn-outline btn-small" onClick={() => revoke(k.id)}>Revoke</button>}</td></tr>))}</tbody>
      </table></div>}
    </Panel>
  )
}
