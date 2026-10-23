import { api } from '../api'
import { useLoad } from '../hooks'
import { Badge, Panel, useToast } from '../ui'

/** The business turns its Readiness Passport on, copies the link, rotates it or switches it off. */
export function PassportCard() {
  const toast = useToast()
  const p = useLoad(() => api.passport())
  async function act(kind: 'enable' | 'rotate' | 'disable') {
    try {
      const next = await api.passportAction(kind)
      p.setData(next)
      toast(kind === 'enable' ? 'Your passport is live.' : kind === 'rotate' ? 'New link created. The old one no longer works.' : 'Your passport is switched off.')
    } catch (err) { toast((err as Error).message, 'error') }
  }
  async function copy(link: string) {
    try { await navigator.clipboard.writeText(link); toast('Link copied.') } catch { toast('Copy the link from the box.', 'error') }
  }
  const d = p.data
  return (
    <Panel title="Your Readiness Passport" sub="One link that shows a buyer what you can prove. You decide who sees it."
      right={d && <Badge tone={d.enabled ? 'green' : 'gray'}>{d.enabled ? 'Live' : 'Off'}</Badge>}>
      {d && !d.enabled && <>
        <ul className="plain-list">
          <li>Verified checks, with where each came from</li>
          <li>Your documents and when they expire</li>
          <li>What you do, and your buyers’ ratings</li>
        </ul>
        <p className="hint">It never shows your turnover, ownership or contact details.</p>
        <button className="btn btn-primary btn-full" onClick={() => act('enable')}>Create my passport</button></>}
      {d?.enabled && d.link && <div className="passport-share">
        {d.qr && <img src={d.qr} alt="QR code for your passport link" width={110} height={110} />}
        <div style={{ minWidth: 0, flex: 1 }}>
          <input readOnly value={d.link} onFocus={(e) => e.currentTarget.select()} aria-label="Passport link" />
          <div className="table-actions" style={{ marginTop: 10, flexWrap: 'wrap' }}>
            <button className="btn btn-primary btn-small" onClick={() => copy(d.link!)}>Copy link</button>
            <a className="btn btn-outline btn-small" href={d.link} target="_blank" rel="noreferrer">Open</a>
            <button className="btn btn-outline btn-small" onClick={() => act('rotate')}>New link</button>
            <button className="btn btn-outline btn-small" onClick={() => act('disable')}>Turn off</button>
          </div>
        </div>
      </div>}
    </Panel>
  )
}
