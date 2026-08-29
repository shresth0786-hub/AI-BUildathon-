import { useEffect, useState } from 'react'
import { api } from '../api.js'

// ------------------------------------------------------------------ SENbot (role-scoped)
// SENbot is available to EVERY designation. Capabilities are role-scoped:
//   * admin          -> full integrity: Q&A over runbook + live dataset, and can
//                       SEARCH + DELETE a payer and their data.
//   * employee / care-> read-only: can Q&A, SEARCH the database/events and
//                       register a support query, but have NO delete / integrity.

const RAG_PRESETS = [
  'Why are legitimate payments being blocked?',
  'A fraudulent payment got approved — what do I do?',
  'My Twilio calls are not connecting.',
  'How do I retrain the model?',
  'Why is this payment in the review band?',
]

const CATEGORIES = [
  'payment_fraud', 'chargeback', 'refund', 'kya', 'other',
]

export default function AdminRagPanel({ open, onClose, isAdmin = false, isCare = false }) {
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [kb, setKb] = useState(null)
  const [rag, setRag] = useState(null)

  // read-only search (any designation)
  const [searchQ, setSearchQ] = useState('')
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchRes, setSearchRes] = useState(null)
  const [searchErr, setSearchErr] = useState(null)

  // support-query registration (employee / care focus)
  const [qm, setQm] = useState('')
  const [qcat, setQcat] = useState(CATEGORIES[0])
  const [qcontact, setQcontact] = useState('')
  const [qMsg, setQMsg] = useState(null)
  const [qErr, setQErr] = useState(null)

  // admin integrity
  const [delId, setDelId] = useState(null)

  useEffect(() => {
    if (!open) return
    setSearchRes(null); setResult(null); setQMsg(null)
    api.ragKnowledge().then((d) => setKb(d.issues || [])).catch(() => {})
    api.ragStatus().then(setRag).catch(() => {})
  }, [open])

  const canManage = rag?.can_manage ?? isAdmin

  const ask = async (question) => {
    setQ(question)
    if (!question || !question.trim()) return
    setBusy(true); setError(null)
    try {
      setResult(await api.ragAsk(question))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const doSearch = async (query) => {
    setSearchErr(null)
    if (!query || !query.trim()) return
    setSearchBusy(true)
    try {
      const d = await api.usersSearch(query)
      setSearchRes(d.users || [])
    } catch (e) {
      setSearchErr(e.message); setSearchRes(null)
    } finally {
      setSearchBusy(false)
    }
  }

  const doDelete = async (id) => {
    setDelId(id); setSearchErr(null)
    try {
      const r = await api.usersDelete(id)
      setSearchRes((list) => (list || []).filter((u) => u.user_id !== id))
      setQMsg(`Integrity: deleted ${r.user_id} — removed from user database (${r.removed_from_user_db ? 'yes' : 'no'}), ${r.events_removed} event(s) removed.`)
    } catch (e) {
      setSearchErr(e.message)
    } finally {
      setDelId(null)
    }
  }

  const registerQuery = async () => {
    setQErr(null); setQMsg(null)
    if (!qm.trim()) { setQErr('Please describe the issue.'); return }
    try {
      const r = await api.queryCreate({ author: 'SENbot', contact: qcontact || '', category: qcat, message: qm })
      setQMsg(`Query registered as ${r.query_id}.`)
      setQm('')
    } catch (e) {
      setQErr(e.message)
    }
  }

  const src = rag?.sources || {}
  return (
    <>
      {open && (
        <div className="rag-scrim" onClick={onClose} />
      )}
      <aside className={`rag-drawer ${open ? 'open' : ''}`}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <h3 style={{ margin: 0, textTransform: 'none', letterSpacing: 0 }}>
            🤖 SENbot
            {canManage
              ? <span className="pill online" style={{ marginLeft: 8 }}>admin · full integrity</span>
              : <span className="pill" style={{ marginLeft: 8 }}>read-only</span>}
          </h3>
          <button className="btn ghost" style={{ padding: '6px 10px', fontSize: 12 }} onClick={onClose}>✕</button>
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          {canManage
            ? 'Full access: Q&A over runbook + live data, plus search & personnel/data deletion.'
            : 'Read-only: Q&A, search payers by phone/user, and register a support query — no deletion.'}
        </p>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10, fontSize: 11 }}>
          <span className="pill">users: {src.user_db ?? 0}</span>
          <span className="pill">events: {src.events ?? 0}</span>
          <span className="pill">feedback: {src.feedback_records ?? 0}</span>
          <span className="pill">verifications: {src.verification_sessions ?? 0}</span>
        </div>

        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>Ask the runbook + live data</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {RAG_PRESETS.map((p) => (
            <button key={p} className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => ask(p)}>
              {p}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            style={{ flex: 1, padding: '8px 10px' }}
            placeholder='e.g. "why is merchant X blocked?"'
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask(q)}
          />
          <button className="btn" onClick={() => ask(q)} disabled={busy || !q.trim()}>
            {busy ? '…' : 'Ask'}
          </button>
        </div>
        {error && <div style={{ color: '#e5534b', marginTop: 10, fontSize: 13 }}>{error}</div>}
        {result && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Answer</div>
            {(result.sources || []).map((s) => (
              <span key={s.id} className="pill" style={{ fontSize: 11 }} title={s.id}>
                {s.title} · {Math.round((s.score || 0) * 100)}%
              </span>
            ))}
            <pre style={{
              whiteSpace: 'pre-line', fontSize: 13, lineHeight: 1.5,
              background: 'var(--bg)', padding: 12, borderRadius: 8,
              fontFamily: 'inherit',
            }}>{result.answer}</pre>
          </div>
        )}
        {kb && kb.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
              Runbook topics ({kb.length})
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {kb.map((k) => (
                <span
                  key={k.id}
                  className={`pill ${k.severity === 'critical' ? 'red' : k.severity === 'high' ? 'amber' : ''}`}
                  title={k.id}
                  style={{ cursor: 'pointer', fontSize: 11 }}
                  onClick={() => ask(k.questions[0])}
                >
                  {k.title}
                </span>
              ))}
            </div>
          </div>
        )}

        <div style={{ margin: '16px 0', borderTop: '1px solid var(--border)' }} />

        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
          Search payer data
          {!canManage && <span className="muted" style={{ fontWeight: 400, fontSize: 11, marginLeft: 6 }}>(read-only)</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            style={{ flex: 1, padding: '8px 10px' }}
            placeholder="Phone / user id / name / card…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch(searchQ)}
          />
          <button className="btn" onClick={() => doSearch(searchQ)} disabled={searchBusy || !searchQ.trim()}>
            {searchBusy ? '…' : 'Search'}
          </button>
        </div>
        {searchErr && <div style={{ color: '#e5534b', marginTop: 8, fontSize: 13 }}>{searchErr}</div>}
        {searchRes !== null && (
          <div style={{ marginTop: 10 }}>
            {searchRes.length === 0
              ? <div className="muted" style={{ fontSize: 13 }}>No payer matched.</div>
              : searchRes.map((u) => (
                  <div key={u.user_id} className="search-row" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13 }}><b>{u.user_id}</b> · {u.name || '—'}</div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        ◉ {u.phone || 'no phone'} · {u.payment_method || '—'} ·•{u.card_last4 || '—'} · ₹{u.amount_inr?.toLocaleString('en-IN') || 0} · {u.merchant || '—'}
                      </div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        verdict: <span className={`badge ${u.decision}`}>{String(u.decision || '—').toUpperCase()}</span>
                        {u.fraud_vector && <> · {u.fraud_vector.replace(/_/g, ' ')}</>}
                      </div>
                    </div>
                    {canManage && (
                      <button className="btn danger" style={{ padding: '5px 8px', fontSize: 11 }} disabled={delId === u.user_id}
                        onClick={() => doDelete(u.user_id)} title="Permanently delete this payer + their data">
                        {delId === u.user_id ? '…' : 'Delete'}
                      </button>
                    )}
                  </div>
                ))}
          </div>
        )}
        {!canManage && (
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            Non-admin roles can search read-only. Deletion is reserved for admin.
          </div>
        )}

        <div style={{ margin: '16px 0', borderTop: '1px solid var(--border)' }} />

        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
          Register a support query
          {isCare && <span className="muted" style={{ fontWeight: 400, fontSize: 11, marginLeft: 6 }}>(customer-care can also manage below)</span>}
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
          <input style={{ flex: 1, padding: '7px 9px' }} placeholder="Contact (phone / email)"
            value={qcontact} onChange={(e) => setQcontact(e.target.value)} />
          <select value={qcat} onChange={(e) => setQcat(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <textarea rows={2} style={{ width: '100%', padding: '8px 9px', resize: 'vertical' }}
          placeholder="What do you need help with?"
          value={qm} onChange={(e) => setQm(e.target.value)} />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
          <button className="btn" onClick={registerQuery} disabled={!qm.trim()}>Register query</button>
        </div>
        {qErr && <div style={{ color: '#e5534b', fontSize: 13, marginTop: 6 }}>{qErr}</div>}
        {qMsg && <div className="green" style={{ fontSize: 13, marginTop: 6 }}>{qMsg}</div>}
      </aside>
    </>
  )
}
