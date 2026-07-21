import { useEffect, useState } from 'react'
import { ApiError, decideApproval, getApprovalsInbox, type Approval } from '../client/api'

export function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  function refresh() {
    getApprovalsInbox()
      .then(setApprovals)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  }

  useEffect(refresh, [])

  async function decide(id: string, approve: boolean) {
    setBusyId(id)
    setError(null)
    try {
      await decideApproval(id, approve, approve ? 'approved via Control UI' : 'rejected via Control UI')
      setApprovals((prev) => prev.filter((a) => a.id !== id))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="approvals-page">
      <h1>Approval inbox</h1>
      <p className="hint">
        Real, live pending approvals — governance's own <code>/approval/pending</code>. Not enriched with
        task/conversation links: approval requests don't carry a correlation_id today, a named gap, not a fake link.
      </p>
      {error && <div className="error-banner">{error}</div>}
      {approvals.length === 0 && <div className="empty-state">Nothing pending.</div>}
      <ul className="approval-list">
        {approvals.map((a) => (
          <li key={a.id} className="approval-card">
            <div className="approval-action">{a.action}</div>
            <div className="approval-meta">
              requested by <strong>{a.requested_by}</strong> · risk <span className={`risk-${a.risk_tier}`}>{a.risk_tier}</span>
            </div>
            <div className="approval-actions">
              <button disabled={busyId === a.id} onClick={() => decide(a.id, true)}>
                Approve
              </button>
              <button className="reject" disabled={busyId === a.id} onClick={() => decide(a.id, false)}>
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
