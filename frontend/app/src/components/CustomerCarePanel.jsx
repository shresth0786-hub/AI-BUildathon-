import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_COLOR = {
  new: 'var(--amber)',
  in_progress: 'var(--blue)',
  resolved: 'var(--green)',
}

export default function CustomerCarePanel() {
  const [data, setData] = useState({ queries: [], stats: {} })
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  const [author, setAuthor] = useState('')
  const [contact, setContact] = useState('')
  const [category, setCategory] = useState('payment')
  const [message, setMessage] = useState('')
  const [posting, setPosting] = useState(false)
  const [posted, setPosted] = useState(null)

  const refresh = useCallback(() => {
    api.queries().then(setData).catch((e) => setErr(e.message)).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 8000)
    return () => clearInterval(t)
  }, [refresh])

  const submit = async () => {
    if (!message.trim()) return
    setPosting(true); setErr(null)
    try {
      const q = await api.queryCreate({ author, contact, category, message })
      setPosted(q)
      setMessage('')
      refresh()
    } catch (e) {
      setErr(e.message)
    } finally {
      setPosting(false)
    }
  }

  const update = async (id, body) => {
    setErr(null)
    try {
      await api.queryUpdate(id, body)
      refresh()
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div className="card">
      <h3>Customer-care queries — queue ({data.stats.total_queries ?? 0})</h3>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Raised into the <b>query database</b> (queries.json — separate from the user
        database and payment data).
      </p>
      {err && <p style={{ color: 'var(--red)', fontSize: 13 }}>{err}</p>}
      {loading && !data.queries.length && <div className="muted" style={{ fontSize: 13 }}>Loading…</div>}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0 14px' }}>
        {Object.entries(data.stats.by_status || {}).map(([k, v]) => (
          <span key={k} className="pill" style={{ color: STATUS_COLOR[k] }}>{k}: {v}</span>
        ))}
      </div>

      <div className="card" style={{ background: 'var(--bg-2)', padding: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Open a new query</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <input placeholder="Customer name" value={author} onChange={(e) => setAuthor(e.target.value)} />
          <input placeholder="Contact (phone/email)" value={contact} onChange={(e) => setContact(e.target.value)} />
        </div>
        <div style={{ marginTop: 10 }}>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="payment">Payment</option>
            <option value="refund">Refund</option>
            <option value="account">Account</option>
            <option value="fraud_report">Fraud report</option>
            <option value="verification">Verification</option>
            <option value="other">Other</option>
          </select>
        </div>
        <textarea style={{ marginTop: 10, minHeight: 70, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', padding: 10, borderRadius: 8, fontSize: 13, width: '100%' }}
          placeholder='Describe the issue, e.g. "My refund of ₹1,200 has not been processed."'
          value={message} onChange={(e) => setMessage(e.target.value)} />
        <button className="btn" style={{ marginTop: 10 }} onClick={submit} disabled={posting || !message.trim()}>
          {posting ? 'Submitting…' : 'Submit query'}
        </button>
        {posted && (
          <div className="green" style={{ fontSize: 13, marginTop: 8 }}>
            Ticket {posted.query_id} created · status: {posted.status}
          </div>
        )}
      </div>

      <div className="spacer" style={{ height: 14 }} />
      {data.queries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.queries.map((q) => (
            <div key={q.query_id} className="phone-box" style={{ marginTop: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <span className="mono" style={{ marginRight: 8 }}>{q.query_id.slice(0, 14)}</span>
                  <b>{q.author}</b>
                  <span className="pill" style={{ marginLeft: 8, color: STATUS_COLOR[q.status] || 'var(--muted)' }}>{q.status}</span>
                  <span className="pill" style={{ marginLeft: 8 }}>{q.category}</span>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {q.created_at ? new Date(q.created_at * 1000).toLocaleString() : ''}
                </div>
              </div>
              <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>{q.message}</div>
              {q.contact && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>contact: {q.contact}</div>}
              {q.assigned_to && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>assigned: {q.assigned_to}</div>}
              {q.resolution && (
                <div className="green" style={{ fontSize: 13, marginTop: 6 }}>resolution: {q.resolution}</div>
              )}
              <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <select value={q.status} onChange={(e) => update(q.query_id, { status: e.target.value })}
                  style={{ width: 150 }}>
                  <option value="new">new</option>
                  <option value="in_progress">in progress</option>
                  <option value="resolved">resolved</option>
                </select>
                <input placeholder="Resolution note" style={{ flex: 1, minWidth: 160 }} value=""
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.target.value.trim()) {
                      update(q.query_id, { resolution: e.target.value.trim(), status: 'resolved' })
                      e.target.value = ''
                    }
                  }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
