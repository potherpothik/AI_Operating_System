import { useEffect, useState } from 'react'
import { ApiError, getHealthSystem, getMetricsOverview } from '../client/api'

// Phase 24 §5.3: consumes Phase 13's existing JSON APIs unchanged,
// rendered generically since the category shape belongs to
// observability's own aggregator, not something this UI should hardcode
// and risk silently drifting out of sync with.
export function Ops() {
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null)
  const [health, setHealth] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)

  function refresh() {
    Promise.all([getMetricsOverview(), getHealthSystem()])
      .then(([m, h]) => {
        setMetrics(m)
        setHealth(h)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30000) // Phase 24 §5.3: default 30s poll, no websocket layer in v1
    return () => clearInterval(id)
  }, [])

  return (
    <div className="ops-page">
      <h1>Ops</h1>
      {error && <div className="error-banner">{error}</div>}
      <section>
        <h2>Health</h2>
        <pre className="json-panel">{health ? JSON.stringify(health, null, 2) : 'Loading…'}</pre>
      </section>
      <section>
        <h2>Metrics overview</h2>
        <pre className="json-panel">{metrics ? JSON.stringify(metrics, null, 2) : 'Loading…'}</pre>
      </section>
    </div>
  )
}
