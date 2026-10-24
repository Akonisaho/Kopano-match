import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { isProvider, tokenSecondsLeft, type Role } from '../api'
import { roleLabel, useAuth } from '../auth'
import { LangSwitch, useT } from '../i18n'
import { Logo } from '../ui'
import { Icon } from './Icon'
import NotificationBell from './NotificationBell'
import { StatusBanner } from '../pages/Enforcement'

const ICON: Record<string, string> = {
  OV: 'home', PF: 'user', VR: 'shield', DC: 'file', OP: 'search', AP: 'send', CN: 'users', SC: 'lock',
  PO: 'plus', SL: 'bookmark', SME: 'building', UM: 'unlock', IM: 'chart', RQ: 'inbox', FB: 'award', EC: 'trending', RE: 'shield',
}
const initialsOf = (name: string) => name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()

type NavItem = [path: string, label: string, icon: string, more?: boolean]

const NAV: Record<string, NavItem[]> = {
  sme: [['/app', 'Home', 'OV'], ['/app/opportunities', 'Opportunities', 'OP'], ['/app/documents', 'Documents', 'DC'],
    ['/app/applications', 'Applications', 'AP'], ['/app/profile', 'Business profile', 'PF'],
    ['/app/verification', 'Verification', 'VR', true], ['/app/consortia', 'Consortia', 'CN', true],
    ['/app/feedback', 'Feedback', 'FB', true], ['/app/security', 'Trust & security', 'SC', true]],
  provider: [['/app', 'Home', 'OV'], ['/app/post', 'Post opportunity', 'PO'], ['/app/shortlist', 'Shortlists', 'SL'],
    ['/app/smes', 'Verified SMEs', 'SME'], ['/app/impact', 'Impact', 'IM'],
    ['/app/applications', 'Applications', 'AP', true], ['/app/insights', 'Unlock Map', 'UM', true],
    ['/app/feedback', 'Feedback', 'FB', true], ['/app/security', 'Trust & security', 'SC', true]],
  admin: [['/app/ecosystem', 'Ecosystem', 'EC'], ['/app/queue', 'Review queue', 'RQ'], ['/app/enforcement', 'Risk & enforcement', 'RE'],
    ['/app/security', 'Trust & security', 'SC', true]],
}

const TITLES: [string, string][] = [
  ['/app/profile', 'Business profile'], ['/app/verification', 'Verification centre'], ['/app/documents', 'Documents'],
  ['/app/opportunities/', 'Opportunity'], ['/app/opportunities', 'Opportunities'], ['/app/applications', 'Applications'],
  ['/app/post', 'Create opportunity'], ['/app/shortlist', 'Shortlists'], ['/app/smes', 'Verified SMEs'], ['/app/insights', 'Unlock Map'], ['/app/impact', 'Impact report'], ['/app/consortia', 'Consortium invitations'],
  ['/app/security', 'Trust & security'], ['/app/enforcement', 'Risk & enforcement'], ['/app/queue', 'Review queue'], ['/app/ecosystem', 'Ecosystem'], ['/app/feedback', 'Feedback'], ['/app/matches/', 'Match detail'], ['/app', 'Dashboard'],
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
  const t = useT()
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
          {navFor(me.role).filter((n) => !n[3]).map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === '/app'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="nav-icon"><Icon name={ICON[icon] ?? 'sparkles'} size={18} /></span><span>{t(label)}</span>
            </NavLink>))}
          {navFor(me.role).some((n) => n[3]) && <div className="nav-more-label">{t('More')}</div>}
          {navFor(me.role).filter((n) => n[3]).map(([to, label, icon]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `secondary ${isActive ? 'active' : ''}`}>
              <span className="nav-icon"><Icon name={ICON[icon] ?? 'sparkles'} size={16} /></span><span>{t(label)}</span>
            </NavLink>))}
        </nav>
        <div className="side-spacer" />
        <div className="side-user">
          <strong>{me.full_name}</strong>
          <small>{me.organisation?.name ?? roleLabel(me.role)}</small>
          <button className="btn btn-ghost btn-small" style={{ color: '#cbd5e1', paddingLeft: 0 }} onClick={() => { signOut(); nav('/') }}>{t('Sign out')}</button>
        </div>
      </aside>
      <main className="app-main">
        <header className="app-header">
          <h2>{t(title)}</h2>
          <div className="header-actions">
            <LangSwitch />
            <NotificationBell />
            <span className="avatar" title={me.full_name}>{initialsOf(me.full_name)}</span>
            <span className={`security-chip ${mins !== null && mins <= 5 ? 'warn' : ''}`} title="Access tokens expire after 30 minutes">
              Secure session · {roleLabel(me.role)}{mins !== null ? ` · ${mins} min left` : ''}
            </span>
          </div>
        </header>
        <div className="app-content">{me.role !== 'admin' && <StatusBanner />}<Outlet /></div>
      </main>
    </div>
  )
}
