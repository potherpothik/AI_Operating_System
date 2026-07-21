import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'

// Phase 24 §14 honesty note: stub Bearer tokens, same convention as
// Gateway's own tokens.yaml — not real SSO/LDAP.
export function Login() {
  const [value, setValue] = useState('dev-admin-token')
  const { login } = useAuth()

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>AI Operating System — Control UI</h1>
        <p className="hint">
          Local dev auth only — a stub Bearer token, the same convention Gateway's own
          <code> tokens.yaml</code> uses. Not real SSO.
        </p>
        <label htmlFor="token">Bearer token</label>
        <input
          id="token"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && login(value)}
        />
        <button onClick={() => login(value)}>Sign in</button>
      </div>
    </div>
  )
}
