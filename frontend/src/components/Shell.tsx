import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { isProvider, tokenSecondsLeft, type Role } from '../api'
import { roleLabel, useAuth } from '../auth'
import { Logo } from '../ui'
import NotificationBell from './NotificationBell'

type NavItem = [path: string, label: string, icon: string]

const NAV: Record<string, NavItem[]> = {
  sme: [['/app', 'Overview', 'OV'], ['/app/profile', 'Business profile', 'PF'], ['/app/verification', 'Verification', 'VR'],
    ['/app/documents', 'Documents', 'DC'], ['/app/opportunities', 'Opportunities', 'OP'], ['/app/applications', 'Applications', 'AP'], ['/app/consortia', 'Consortia', 'CN'],
    ['/app/security', 'Trust & security', 'SC']],
  provider: [['/app', 'Overview', 'OV'], ['/app/post', 'Post opportunity', 'PO'], ['/app/shortlist', 'Shortlists', 'SL'],
    ['/app/applications', 'Applications', 'AP'], ['/app/smes', 'Verified SMEs', 'SME'], ['/app/insights', 'Unlock Map', 'UM'], ['/app/impact', 'Impact', 'IM'], ['/app/security', 'Trust & security', 'SC']],
  admin: [['/app/queue', 'Review queue', 'RQ'], ['/app/security', 'Trust & security', 'SC']],
}

const TITLES: [string, string][] = [
  ['/app/profile', 'Business profile'], ['/app/verification', 'Verification centre'], ['/app/documents', 'Documents'],
  ['/app/opportunities/', 'Opportunity'], ['/app/opportunities', 'Opportunities'], ['/app/applications', 'Applications'],
  ['/app/post', 'Create opportunity'], ['/app/shortlist', 'Shortlists'], ['/app/smes', 'Verified SMEs'], ['/app/insights', 'Unlock Map'], ['/app/impact', 'Impact report'], ['/app/consortia', 'Consortium invitations'],
  ['/app/security', 'Trust & security'], ['/app/queue', 'Review queue'], ['/app/matches/', 'Match detail'], ['/app', 'Dashboard'],
]

function useSessionLeft() {
  const [left, setLeft] = useState<number | null>(tokenSecondsLeft())
  const { signOut } = useAuth()
  const nav = useNavigate()
  useEffect(() => {
    const t = setInterval(() => {
      const s = tokenSecondsLeft()
      setLeft(s)
      if (s === 0) { signOut(); nav('/login') }
    }, 15000)
    return () => clearInterval(t)
  }, [signOut, nav])
  return left
}

export const navFor = (role: Role) => NAV[isProvider(role) ? 'provider' : role]

export default function Shell() {
  const { me, signOut } = useAuth()
  const loc = useLocation()
  const nav = useNavigate()
  const left = useSessionLeft()
  if (!me) return null
  const title = TITLES.find(([p]) => loc.pathname === p || loc.pathname.startsWith(p))?.[1] ?? 'Dashboard'
  const mins = left === null ? null : Math.ceil(left / 60)
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/app" className="brand"><Logo dark /></Link>
        <nav className="side-nav" aria-label="Main">
          {navFor(me.role).map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === '/app'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="nav-icon">{icon}</span><span>{label}</span>
            </NavLink>))}
        </nav>
        <div className="side-spacer" />
        <div className="side-user">
          <strong>{me.full_name}</strong>
          <small>{me.organisation?.name ?? roleLabel(me.role)}</small>
          <button className="btn btn-ghost btn-small" style={{ color: '#cbd5e1', paddingLeft: 0 }} onClick={() => { signOut(); nav('/') }}>Sign out</button>
        </div>
      </aside>
      <main className="app-main">
        <header className="app-header">
          <h2>{title}</h2>
          <div className="header-actions">
            <NotificationBell />
            <span className={`security-chip ${mins !== null && mins <= 5 ? 'warn' : ''}`} title="Access tokens expire after 30 minutes">
              Secure session · {roleLabel(me.role)}{mins !== null ? ` · ${mins} min left` : ''}
            </span>
          </div>
        </header>
        <div className="app-content"><Outlet /></div>
      </main>
    </div>
  )
}
