const BASE = '/api'

async function get(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.detail || `POST ${path} -> ${res.status}`)
  }
  return res.json()
}

export const api = {
  summary: () => get('/summary'),
  testMetrics: () => get('/test-metrics'),
  events: (risk, limit = 250) =>
    get(`/events${risk ? `?risk=${risk}` : ''}&limit=${limit}`),
  event: (id) => get(`/events/${id}`),
  vectors: () => get('/vectors'),
  rzpStatus: () => get('/rzp/status'),
  demoFraud: () => get('/demo/fraud'),
  demoClean: () => get('/demo/clean'),
  demoBorderline: (phone) => ({
    // a medium-risk payment that triggers the phone-call payment confirmation
    event: {
      user_id: 'usr_rev_demo',
      device_id: 'dev_new_demo',
      card_last4: '4411',
      amount_inr: 6000,
      merchant: 'TechNova Store',
      payment_method: 'card',
      card_bin_country: 'IN',
      ip_geo_match: true,
      is_international: false,
      billing_zip: '400001',
      shipping_zip: '560001',
      typing_seconds: 2.5,
      attempt_count: 2,
      is_new_device: true,
      three_ds_passed: true,
      status: 'captured',
      phone: phone || import.meta.env.VITE_DEMO_PHONE || '+919876543210',
    },
    history: [],
  }),
  investigate: (body) => post('/investigate', body),
  verification: () => get('/verification'),
  verConfirm: (id, otp) => post(`/verification/${id}/confirm`, { otp }),
  verDeny: (id) => post(`/verification/${id}/deny`),
  verResend: (id) => post(`/verification/${id}/resend`),
  feedback: () => get('/feedback'),
  correct: (id, isFraud) => post(`/feedback/${id}/correct`, { is_fraud: isFraud }),
  retrain: () => post('/learning/retrain'),
  ragAsk: (question) => post('/rag/ask', { question }),
  ragKnowledge: () => get('/rag/knowledge'),
  ragStatus: () => get('/rag/status'),
}
