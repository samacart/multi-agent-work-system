import { useCallback, useEffect, useState } from 'react'

export type Polled<T> = {
  data: T | null
  error: string | null
  loading: boolean
  refresh: () => void
}

/** Fetch on mount and every `intervalMs`. Keeps the last good value on error. */
export function usePolled<T>(fetcher: () => Promise<T>, intervalMs = 5000): Polled<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  const refresh = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      try {
        const result = await fetcher()
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void run()
    const id = setInterval(run, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // `fetcher` is a stable module-level function in every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick])

  return { data, error, loading, refresh }
}
