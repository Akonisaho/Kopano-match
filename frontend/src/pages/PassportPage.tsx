import { Link, useParams } from 'react-router-dom'
import { api, dateFmt, pretty } from '../api'
import { useLoad } from '../hooks'
import { LangSwitch, useT } from '../i18n'
import { Badge, Logo, Spinner } from '../ui'

/** The public page a business shares with a corporate. No sign-in. Only what the business chose to show. */
export default function PassportPage() {
  const { token = '' } = useParams()
  const t = useT()
  const d = useLoad(() => api.publicPassport(token), [token])
  return (
    <div className="passport-page">
      <header className="topbar"><Link to="/"><Logo /></Link>
        <div className="top-actions no-print"><LangSwitch /><button className="btn btn-outline" onClick={() => window.print()}>{t('Print or save as PDF')}</button></div></header>
      <main className="passport-wrap">
        {d.loading && <Spinner />}
        {d.error && <div className="passport-card"><div className="passport-body"><h2>{t('This passport is not available')}</h2>
          <p className="hint">{t('The link may have been switched off or replaced by the business. Ask them for a new one.')}</p></div></div>}
        {d.data && (() => {
          const x = d.data
          const tr = x.track_record
          return (
            <article className="passport-card">
              <div className="passport-head">
                <small>{t('Readiness Passport')}</small>
                <h1>{x.name}</h1>
                <p>{[x.sector && t(pretty(x.sector)), x.province, x.years_trading != null && t('{n} years trading', { n: x.years_trading })].filter(Boolean).join('  ·  ')}</p>
                <span className="passport-asof">{t('As of')} {dateFmt(x.as_of)}</span>
              </div>
              <div className="passport-body">
                <section>
                  <h3>{t('Verified checks')}</h3>
                  {x.checks.length ? x.checks.map((c) => (
                    <div key={c.label} className="pp-row"><span className={`pp-dot ${c.ok ? 'ok' : 'warn'}`}>{c.ok ? '✓' : '!'}</span>
                      <div><b>{t(c.label)}</b><small>{c.ok ? t('Verified') : t('Not verified')} · {c.source}</small></div></div>)) : <p className="hint">{t('No checks on record.')}</p>}
                </section>
                <section>
                  <h3>{t('Credentials')} <span className="hint">({t('{n} valid', { n: x.credentials_valid })})</span></h3>
                  {x.credentials.length ? x.credentials.map((c) => (
                    <div key={c.label} className="pp-row"><span className={`pp-dot ${c.status === 'valid' ? 'ok' : 'warn'}`}>{c.status === 'valid' ? '✓' : '!'}</span>
                      <div><b>{t(c.label)}</b><small>{c.status === 'valid' ? t('Valid') : t(pretty(c.status))}{c.expires ? ` · ${t('until')} ${dateFmt(c.expires)}` : ''}</small></div></div>)) : <p className="hint">{t('No documents on file.')}</p>}
                </section>
                <section>
                  <h3>{t('What they do')}</h3>
                  <div className="chips">{x.capabilities.map((c) => <span key={c} className="chip">{t(c)}</span>)}</div>
                </section>
                <section>
                  <h3>{t('Track record')}</h3>
                  {tr.reviews ? <p style={{ margin: 0 }}><b className="pp-score">{tr.overall?.toFixed(1)}</b> {tr.reviews === 1 ? t('out of 5 from 1 corporate review') : t('out of 5 from {n} corporate reviews', { n: tr.reviews })} <Badge tone={tr.reliable ? 'green' : 'amber'}>{tr.reliable ? t('Established') : t('Early signal')}</Badge></p>
                    : <p className="hint" style={{ margin: 0 }}>{t('No corporate reviews yet.')}</p>}
                </section>
                <p className="hint passport-notice">{t(x.notice)}</p>
              </div>
              <div className="passport-foot no-print">
                <span>{t('Want one for your business?')}</span>
                <Link className="btn btn-primary btn-small" to="/register">{t('Create your passport')}</Link>
              </div>
            </article>)
        })()}
      </main>
    </div>
  )
}
