import { useEffect, useState } from 'react'
import { api } from '../api.js'

const ROLE_IDEAS = {
  admin: { label: 'Administrator', user: 'admin', pass: 'admin123' },
  employee: { label: 'Risk Employee', user: 'employee', pass: 'employee123' },
  customer_care: { label: 'Customer Care', user: 'care', pass: 'care123' },
}

export default function Login({ onSuccess }) {
  const [roles, setRoles] = useState(null)
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.authRoles().then(setRoles).catch(() => {})
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const s = await api.login(username.trim(), password)
      const me = await api.me(s.token)
      onSuccess({ token: s.token, ...me })
    } catch (ex) {
      setErr(ex.message || 'login failed')
    } finally {
      setBusy(false)
    }
  }

  const pick = (r) => {
    const idea = ROLE_IDEAS[r]
    setUsername(idea.user); setPassword(idea.pass)
  }

  return (
    <div className="wrap" style={{ maxWidth: 460, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: '90vh' }}>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 6 }}>
          <div className="logo">🛡</div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20 }}>Sentinel AI</h1>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>Razorpay Fraud Guardian</p>
          </div>
        </div>
        <h3 style={{ margin: '18px 0 6px', textTransform: 'none', color: 'var(--text)', letterSpacing: 0 }}>Sign in</h3>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          Role-based access. Pick a role to prefill demo credentials.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0 14px' }}>
          {Object.entries(ROLE_IDEAS).map(([k, v]) => (
            <button key={k} type="button" className={`btn ghost${username === v.user ? '' : ''}`}
              style={{ fontSize: 12 }} onClick={() => pick(k)}>
              {v.label}
            </button>
          ))}
        </div>
        <form onSubmit={submit}>
          <label htmlFor="u">Username</label>
          <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} />
          <label htmlFor="p">Password</label>
          <input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className="btn" style={{ width: '100%', marginTop: 18 }} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {err && <p style={{ color: 'var(--red)', fontSize: 13, marginTop: 12 }}>{err}</p>}
        {roles && (
          <div className="muted" style={{ fontSize: 12, marginTop: 16 }}>
            Demo accounts: {roles.accounts.map((a) => `${a.username} (${a.role_labels ? roles.role_labels[a.role] : a.role})`).join(' · ')}
          </div>
        )}
      </div>
    </div>
  )
}
