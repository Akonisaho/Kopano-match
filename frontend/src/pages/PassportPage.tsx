import { Link, useParams } from 'react-router-dom'
import { api, dateFmt, pretty } from '../api'
import { useLoad } from '../hooks'
import { Badge, Logo, Spinner } from '../ui'

/** The public page a business shares with a buyer. No sign-in. Only what the business chose to show. */
export default function PassportPage() {
  const { token = '' } = useParams()
  const d = useLoad(() => api.publicPassport(token), [token])
  return (
    <div className="passport-page">
      <header className="topbar"><Link to="/"><Logo /></Link>
        <div className="top-actions no-print"><button className="btn btn-outline" onClick={() => window.print()}>Print or save as PDF</button></div></header>
      <main className="passport-wrap">
        {d.loading && <Spinner />}
        {d.error && <div className="passport-card"><div className="passport-body"><h2>This passport is not available</h2>
          <p className="hint">The link may have been switched off or replaced by the business. Ask them for a new one.</p></div></div>}
        {d.data && (() => {
          const x = d.data
          const tr = x.track_record
          return (
            <article className="passport-card">
              <div className="passport-head">
                <small>Readiness Passport</small>
                <h1>{x.name}</h1>
                <p>{[x.sector && pretty(x.sector), x.province, x.years_trading != null && `${x.years_trading} years trading`].filter(Boolean).join('  ·  ')}</p>
                <span className="passport-asof">As of {dateFmt(x.as_of)}</span>
              </div>
              <div className="passport-body">
                <section>
                  <h3>Verified checks</h3>
                  {x.checks.length ? x.checks.map((c) => (
                    <div key={c.label} className="pp-row"><span className={`pp-dot ${c.ok ? 'ok' : 'warn'}`}>{c.ok ? '✓' : '!'}</span>
                      <div><b>{c.label}</b><small>{c.ok ? 'Verified' : 'Not verified'} · {c.source}</small></div></div>)) : <p className="hint">No checks on record.</p>}
                </section>
                <section>
                  <h3>Credentials <span className="hint">({x.credentials_valid} valid)</span></h3>
                  {x.credentials.length ? x.credentials.map((c) => (
                    <div key={c.label} className="pp-row"><span className={`pp-dot ${c.status === 'valid' ? 'ok' : 'warn'}`}>{c.status === 'valid' ? '✓' : '!'}</span>
                      <div><b>{c.label}</b><small>{c.status === 'valid' ? 'Valid' : pretty(c.status)}{c.expires ? ` · until ${dateFmt(c.expires)}` : ''}</small></div></div>)) : <p className="hint">No documents on file.</p>}
                </section>
                <section>
                  <h3>What they do</h3>
                  <div className="chips">{x.capabilities.map((c) => <span key={c} className="chip">{c}</span>)}</div>
                </section>
                <section>
                  <h3>Track record</h3>
                  {tr.reviews ? <p style={{ margin: 0 }}><b className="pp-score">{tr.overall?.toFixed(1)}</b> out of 5 from {tr.reviews} buyer review{tr.reviews === 1 ? '' : 's'} <Badge tone={tr.reliable ? 'green' : 'amber'}>{tr.reliable ? 'Established' : 'Early signal'}</Badge></p>
                    : <p className="hint" style={{ margin: 0 }}>No buyer reviews yet.</p>}
                </section>
                <p className="hint passport-notice">{x.notice}</p>
              </div>
              <div className="passport-foot no-print">
                <span>Want one for your business?</span>
                <Link className="btn btn-primary btn-small" to="/register">Create your passport</Link>
              </div>
            </article>)
        })()}
      </main>
    </div>
  )
}
