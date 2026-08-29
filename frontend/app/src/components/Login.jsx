import { useEffect, useState } from 'react'
import { api, setToken } from '../api.js'

const ROLES = {
  admin: {
    role: 'admin',
    label: 'Administrator',
    user: 'admin',
    pass: 'admin123',
  },
  employee: {
    role: 'employee',
    label: 'Risk Employee',
    user: 'employee',
    pass: 'employee123',
  },
  customer_care: {
    role: 'customer_care',
    label: 'Customer Care',
    user: 'care',
    pass: 'care123',
  },
}

export default function Login({ onSuccess }) {
  const [roles, setRoles] = useState(null)
  const [designation, setDesignation] = useState(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.authRoles().then(setRoles).catch(() => {})
  }, [])

  const choose = (key) => {
    const r = ROLES[key]
    setDesignation(r)
    setUsername(r.user)
    setPassword(r.pass)
    setErr(null)
  }

  const back = () => {
    setDesignation(null)
    setUsername('')
    setPassword('')
    setErr(null)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const s = await api.login(username.trim(), password)
      setToken(s.token)
      const me = await api.me()
      onSuccess({ token: s.token, ...me })
    } catch (ex) {
      setErr(ex.message || 'login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wrap" style={{ maxWidth: 480, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: '90vh' }}>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 6 }}>
          <div className="logo">🛡</div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20 }}>Sentinel AI</h1>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>Razorpay Fraud Guardian</p>
          </div>
        </div>

        {!designation ? (
          <>
            <h3 style={{ margin: '18px 0 6px', textTransform: 'none', color: 'var(--text)', letterSpacing: 0 }}>
              Select your designation
            </h3>
            <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
              Choose your role. We will take you to the sign-in portal for that designation.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
              {Object.entries(ROLES).map(([key, r]) => (
                <button key={key} type="button" className="btn ghost"
                  style={{ display: 'block', textAlign: 'left', padding: '12px 14px', height: 'auto', whiteSpace: 'normal', fontSize: 14 }}
                  onClick={() => choose(key)}>
                  <b>{r.label}</b>
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
              <button type="button" className="btn ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={back}>
                ← Change designation
              </button>
              <span className="pill">{designation.label}</span>
            </div>
            <h3 style={{ margin: '18px 0 6px', textTransform: 'none', color: 'var(--text)', letterSpacing: 0 }}>Sign in</h3>
            <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
              Enter the credentials for this designation. Prefilled with the demo account for {designation.label}.
            </p>
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
          </>
        )}

        {roles && (
          <div className="muted" style={{ fontSize: 12, marginTop: 16 }}>
            Demo accounts: {roles.accounts.map((a) => `${a.username} (${roles.role_labels ? roles.role_labels[a.role] : a.role})`).join(' · ')}
          </div>
        )}
      </div>
    </div>
  )
}
