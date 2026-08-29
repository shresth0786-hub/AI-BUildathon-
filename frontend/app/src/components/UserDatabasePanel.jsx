import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const DEC = { approve: 'var(--green)', review: 'var(--amber)', block: 'var(--red)' }

function matches(rows, q) {
  if (!q) return rows
  const s = q.toLowerCase()
  return rows.filter((r) =>
    [r.user_id, r.name, r.phone, r.merchant, r.decision, r.fraud_vector, r.card_last4]
      .some((v) => v && String(v).toLowerCase().includes(s)))
}

function sortRows(rows, key, dir) {
  if (!key) return rows
  return [...rows].sort((a, b) => {
    const av = a[key]; const bv = b[key]
    if (av == null) return 1
    if (bv == null) return -1
    const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
    return dir === 'asc' ? cmp : -cmp
  })
}

function Th({ label, k, sortKey, sortDir, onSort }) {
  return (
    <th className="sortable" onClick={() => onSort(k)}>
      {label}
      {sortKey === k && <span className="sort-arrow">{sortDir === 'asc' ? '▲' : '▼'}</span>}
    </th>
  )
}

export default function UserDatabasePanel() {
  const [data, setData] = useState({ users: [], stats: {} })
  const [risk, setRisk] = useState('')
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState('')
  const [sortDir, setSortDir] = useState('asc')
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

  const onSort = (k) => {
    if (sortKey === k) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(k); setSortDir('asc') }
  }

  const rows = useMemo(() => {
    let r = risk ? data.users.filter((u) => u.decision === risk) : data.users
    r = matches(r, q)
    return sortRows(r, sortKey, sortDir)
  }, [data.users, risk, q, sortKey, sortDir])

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
      <div className="table-toolbar">
        <select value={risk} onChange={(e) => setRisk(e.target.value)} style={{ width: 180 }}>
          <option value="">All decisions</option>
          <option value="approve">Approved</option>
          <option value="review">Review</option>
          <option value="block">Blocked</option>
        </select>
        <input className="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search users, names, cards, merchants…" />
      </div>
      <p className="muted" style={{ fontSize: 12, margin: '0 0 8px' }}>
        Click a column header to sort.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <Th label="User" k="user_id" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Name" k="name" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th>Contact</th>
              <Th label="Merchant" k="merchant" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Amount" k="amount_inr" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Decision" k="decision" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th>Vector</th>
              <Th label="Seen" k="updated_at" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="muted">Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={8} className="muted">No users match. Run a live investigation to populate the database.</td></tr>}
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
