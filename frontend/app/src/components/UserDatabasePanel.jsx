import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const DEC = { approve: 'var(--green)', review: 'var(--amber)', block: 'var(--red)' }

export default function UserDatabasePanel() {
  const [data, setData] = useState({ users: [], stats: {} })
  const [risk, setRisk] = useState('')
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    api.users().then(setData).catch((e) => setErr(e.message)).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 8000)
    return () => clearInterval(t)
  }, [load])

  const rows = risk ? data.users.filter((u) => u.decision === risk) : data.users

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>User database ({data.stats.total_users ?? 0})</h3>
        <button className="btn ghost" onClick={load}>Refresh</button>
      </div>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Stored in <b>users.json</b> (database/db — separate from payment data). Admin only.
      </p>
      {err && <p style={{ color: 'var(--red)', fontSize: 13 }}>{err}</p>}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0' }}>
        {Object.entries(data.stats.by_decision || {}).map(([k, v]) => (
          <span key={k} className="pill">{k}: {v}</span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <select value={risk} onChange={(e) => setRisk(e.target.value)} style={{ width: 180 }}>
          <option value="">All decisions</option>
          <option value="approve">Approved</option>
          <option value="review">Review</option>
          <option value="block">Blocked</option>
        </select>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr><th>User</th><th>Name</th><th>Contact</th><th>Merchant</th><th>Amount</th><th>Decision</th><th>Vector</th><th>Seen</th></tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="muted">Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={8} className="muted">No users stored yet. Run a live investigation to populate the database.</td></tr>}
            {rows.map((u) => (
              <tr key={u.user_id}>
                <td className="mono">{u.user_id}</td>
                <td>{u.name || '—'}</td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {u.phone || '—'}{u.card_last4 ? ` · ••${u.card_last4}` : ''}
                </td>
                <td>{u.merchant || '—'}</td>
                <td>{u.amount_inr ? `₹${u.amount_inr.toLocaleString('en-IN')}` : '—'}</td>
                <td>
                  {u.decision
                    ? <span className="badge" style={{ background: 'transparent', border: '1px solid ' + DEC[u.decision], color: DEC[u.decision] }}>{u.decision.toUpperCase()}</span>
                    : '—'}
                </td>
                <td className="muted" style={{ fontSize: 12 }}>{u.fraud_vector ? u.fraud_vector.replace(/_/g, ' ') : '—'}</td>
                <td className="muted" style={{ fontSize: 12 }}>{u.updated_at ? new Date(u.updated_at * 1000).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
