import { useEffect, useState } from 'react'
import { api } from '../api.js'

// ------------------------------------------------------------------ admin RAG Q&A
const RAG_PRESETS = [
  'Why are legitimate payments being blocked?',
  'A fraudulent payment got approved — what do I do?',
  'My Twilio calls are not connecting.',
  'How do I retrain the model?',
  'Why is this payment in the review band?',
]

export default function AdminRagPanel() {
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [kb, setKb] = useState(null)
  const [rag, setRag] = useState(null)
  const [users, setUsers] = useState(null)

  useEffect(() => {
    api.ragKnowledge().then((d) => setKb(d.issues || [])).catch(() => {})
    api.ragStatus().then(setRag).catch(() => {})
    api.users().then(setUsers).catch(() => {})
  }, [])

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

  const src = rag?.sources || {}
  return (
    <div className="card">
      <h3>Admin Q&amp;A — RAG assistant</h3>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Ask what the issue is and what to do about it. The assistant answers from the
        runbook ({rag?.entries ?? 0} issues) <b>and learns from the live dataset</b>
        ({rag?.live_chunks ?? 0} live chunks) — real transactions, mined insights,
        confirmed feedback and stored users. Fully offline
        ({rag?.offline ? ' local TF-IDF · no API key' : ''}).
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10,
                    fontSize: 12 }}>
        <span className="pill">users in DB: {users?.stats?.total_users ?? 0}</span>
        <span className="pill">live events: {src.events ?? 0}</span>
        <span className="pill">feedback: {src.feedback_records ?? 0}</span>
        <span className="pill">phone calls: {src.verification_sessions ?? 0}</span>
        {rag?.pipeline && <span className="pill">pipeline: {rag.pipeline}</span>}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        {RAG_PRESETS.map((p) => (
          <button key={p} className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => ask(p)}>
            {p}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          style={{ flex: 1, padding: '8px 10px' }}
          placeholder='e.g. "why is merchant X blocked?" or "tell me about user usr_abc"'
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask(q)}
        />
        <button className="btn" onClick={() => ask(q)} disabled={busy || !q.trim()}>
          {busy ? 'Asking…' : 'Ask'}
        </button>
      </div>
      {error && <div style={{ color: '#e5534b', marginTop: 10, fontSize: 13 }}>{error}</div>}
      {result && (
        <div style={{ marginTop: 14, position: 'relative' }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Answer</div>
          {(result.sources || []).map((s) => (
            <span key={s.id} className="pill" title={s.id}>
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
                style={{ cursor: 'pointer' }}
                onClick={() => ask(k.questions[0])}
              >
                {k.title}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
