import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth'
import { Logo } from '../ui'

/** The dark public header shared by the landing page and the open pages. */
export default function LxTop({ onLogin, onSignup }: { onLogin: () => void; onSignup: () => void }) {
  const { me } = useAuth()
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
      <nav className="lx-nav"><Link to="/opportunities">Opportunities</Link><a href="/#how">How it works</a><a href="/#edge">Why it wins</a><Link to="/responsible-ai">Responsible AI</Link></nav>
      <div className="lx-actions">
        {me ? <button className="lx-btn lx-btn-gold" onClick={() => nav(homeFor(me.role))}>Open workspace</button> : <>
          <button className="lx-btn lx-btn-ghost" onClick={onLogin}>Log in</button>
          <button className="lx-btn lx-btn-gold" onClick={onSignup}>Get started</button></>}
      </div>
    </header>
  )
}
