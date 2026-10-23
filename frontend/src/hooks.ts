import { useCallback, useEffect, useRef, useState } from 'react'

/** Load data on mount (and on demand). Keeps the first error and exposes reload. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const ref = useRef(fn)
  ref.current = fn
  const reload = useCallback(() => {
    setLoading(true)
    return ref.current()
      .then((d) => { setData(d); setError(null) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload() }, deps)
  return { data, error, loading, reload, setData }
}
