import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'
import { useAuth } from './auth'
import { DICT } from './i18n-dict'

export type Lang = 'en' | 'af' | 'zu' | 'st'

/** isiZulu and Sesotho are drafts until a first-language speaker has checked them. Say so on screen. */
export const LANGS: { code: Lang; label: string; speech: string; reviewed: boolean }[] = [
  { code: 'en', label: 'English', speech: 'en-ZA', reviewed: true },
  { code: 'af', label: 'Afrikaans', speech: 'af-ZA', reviewed: true },
  { code: 'zu', label: 'isiZulu', speech: 'zu-ZA', reviewed: false },
  { code: 'st', label: 'Sesotho', speech: 'st-ZA', reviewed: false },
]
const KEY = 'kopano_lang'
type Vars = Record<string, string | number>
export type T = (s: string, vars?: Vars) => string

interface LangState { lang: Lang; setLang: (l: Lang) => void; t: T }
const Ctx = createContext<LangState>({ lang: 'en', setLang: () => undefined, t: (s) => s })
export const useLang = () => useContext(Ctx)
export const useT = () => useContext(Ctx).t
export const speechCode = (l: Lang) => LANGS.find((x) => x.code === l)?.speech ?? 'en-ZA'

const stored = (): Lang | null => {
  try { const v = localStorage.getItem(KEY); return LANGS.some((l) => l.code === v) ? (v as Lang) : null } catch { return null }
}
const fill = (s: string, vars?: Vars) => (vars ? s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`)) : s)

/** The English sentence is the key. A missing translation falls back to English, never to a blank. */
export function LangProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const [lang, setLangState] = useState<Lang>(() => stored() ?? 'en')

  useEffect(() => { document.documentElement.lang = lang }, [lang])
  // A saved preference follows a person across devices; a choice made on this device wins and is saved
  useEffect(() => {
    if (!me) return
    const local = stored()
    if (local && local !== me.language) api.setLanguage(local).catch(() => undefined)
    else if (!local && me.language && me.language !== lang) setLangState(me.language as Lang)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try { localStorage.setItem(KEY, l) } catch { /* the choice still applies for this visit */ }
    if (me) api.setLanguage(l).catch(() => undefined)
  }, [me])

  const t = useCallback<T>((s, vars) => fill((lang === 'en' ? undefined : DICT[lang]?.[s]) ?? s, vars), [lang])
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function LangSwitch({ dark }: { dark?: boolean }) {
  const { lang, setLang } = useLang()
  return (
    <select className={`lang-select ${dark ? 'dark' : ''}`} value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label="Language">
      {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}{l.reviewed ? '' : ' · beta'}</option>)}
    </select>
  )
}
