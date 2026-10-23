import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, dateFmt, type NotificationBox } from '../api'

/** The bell: the same notices that go out by email, kept in the app so they work offline too. */
export default function NotificationBell() {
  const nav = useNavigate()
  const [box, setBox] = useState<NotificationBox | null>(null)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const load = () => api.notifications().then(setBox).catch(() => {})
  useEffect(() => {
    load()
    const t = setInterval(load, 45000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  async function markRead() { await api.markNotificationsRead(); load() }
  const unread = box?.unread ?? 0

  return (
    <div className="bell" ref={ref}>
      <button className="bell-btn" aria-label={`Notifications, ${unread} unread`} aria-expanded={open} onClick={() => { setOpen(!open); if (!open) load() }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
        {unread > 0 && <span className="bell-count">{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && (
        <div className="bell-pop" role="dialog" aria-label="Notifications">
          <div className="bell-head"><b>Notifications</b>{unread > 0 && <button className="btn btn-ghost btn-small" onClick={markRead}>Mark all read</button>}</div>
          {box?.items.length ? box.items.map((n) => (
            <button key={n.id} className={`bell-item ${n.read ? '' : 'unread'}`} onClick={() => { setOpen(false); if (n.link) nav(n.link) }}>
              <b>{n.title}</b><span>{n.body}</span><small>{dateFmt(n.created_at)}</small>
            </button>)) : <p className="empty" style={{ padding: 24 }}>Nothing yet.</p>}
        </div>
      )}
    </div>
  )
}
