import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth'
import { LangSwitch, useT } from '../i18n'
import { Logo } from '../ui'

/** The dark public header shared by the landing page and the open pages. */
export default function LxTop({ onLogin, onSignup }: { onLogin: () => void; onSignup: () => void }) {
  const { me } = useAuth()
  const t = useT()
  const nav = useNavigate()
  const [solid, setSolid] = useState(false)
  useEffect(() => {
    const on = () => setSolid(window.scrollY > 40)
    on(); window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  return (
    <header className={`lx-top ${solid ? 'solid' : ''}`}>
      <Link to="/"><Logo dark /></Link>
      <nav className="lx-nav"><Link to="/opportunities">{t('Opportunities')}</Link><a href="/#how">{t('How it works')}</a><a href="/#edge">{t('Why it wins')}</a><Link to="/responsible-ai">{t('Responsible AI')}</Link></nav>
      <div className="lx-actions">
        <LangSwitch dark />
        {me ? <button className="lx-btn lx-btn-gold" onClick={() => nav(homeFor(me.role))}>{t('Open workspace')}</button> : <>
          <button className="lx-btn lx-btn-ghost" onClick={onLogin}>{t('Log in')}</button>
          <button className="lx-btn lx-btn-gold" onClick={onSignup}>{t('Get started')}</button></>}
      </div>
    </header>
  )
}
