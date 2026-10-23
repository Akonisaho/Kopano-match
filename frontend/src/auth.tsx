import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api, getToken, isProvider, setToken, type Me, type Role } from './api'

interface AuthState {
  me: Me | null
  loading: boolean
  signIn: (token: string) => Promise<Me>
  signOut: () => void
  refresh: () => Promise<void>
  signedOut: boolean
}

const Ctx = createContext<AuthState>(null as unknown as AuthState)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(!!getToken())
  const [signedOut, setSignedOut] = useState(false)

  useEffect(() => {
    if (!getToken()) return
    api.me().then(setMe).catch(() => setToken(null)).finally(() => setLoading(false))
  }, [])

  const signIn = async (token: string) => {
    setToken(token)
    setSignedOut(false)
    const m = await api.me()
    setMe(m)
    return m
  }
  const refresh = async () => { setMe(await api.me()) }
  const signOut = () => {
    setToken(null)
    setSignedOut(true)
    setMe(null)
  }
  return <Ctx.Provider value={{ me, loading, signIn, signOut, refresh, signedOut }}>{children}</Ctx.Provider>
}

export const homeFor = (role: Role) => (role === 'admin' ? '/app/queue' : '/app')
export const roleLabel = (r: Role) =>
  ({ sme: 'SME', corporate: 'Corporate buyer', funder: 'Funder / investor', support: 'Business support', admin: 'Platform reviewer' })[r]

/** UI gate only. The API enforces the same rules, so this is convenience, not security. */
export function RequireRole({ roles, children }: { roles: Role[] | 'provider'; children: ReactNode }) {
  const { me, loading, signedOut } = useAuth()
  if (loading) return <p className="empty">Loading…</p>
  if (!me) return <Navigate to={signedOut ? '/' : '/login'} replace />
  const allowed = roles === 'provider' ? isProvider(me.role) : roles.includes(me.role)
  if (!allowed) return <Navigate to={homeFor(me.role)} replace />
  return <>{children}</>
}
