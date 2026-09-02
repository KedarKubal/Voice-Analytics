import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../api/apiClient'
import './Login.css'

function EyeIcon({ open }) {
  return open ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  )
}

export default function Login() {
  const [email,        setEmail]        = useState('')
  const [password,     setPassword]     = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error,        setError]        = useState('')
  const [loading,      setLoading]      = useState(false)

  const { login, user, ready } = useAuth()
  const navigate  = useNavigate()

  // If already logged in, redirect to correct dashboard immediately
  useEffect(() => {
    if (ready && user) {
      navigate(user.role === 'heya_admin' ? '/admin' : '/dashboard', { replace: true })
    }
  }, [ready, user, navigate])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await api.post('/auth/login', { email, password })
      const { access_token, role, name } = res.data

      login(access_token, { name })

      // Role-based redirect
      if (role === 'heya_admin') {
        navigate('/admin')
      } else {
        navigate('/dashboard')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">

        {/* Logo */}
        <div className="login-logo">
          <div className="login-logo-mark">🎙</div>
          <div>
            <div className="login-logo-text">Heya AI</div>
            <div className="login-logo-sub">Voice Analytics Platform</div>
          </div>
        </div>

        <h1 className="login-title">Sign in</h1>
        <p className="login-desc">Access your call intelligence dashboard</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoFocus
            />
          </div>

          <div className="login-field">
            <label>Password</label>
            <div className="login-password-wrap">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
              <button
                type="button"
                className="login-eye-btn"
                onClick={() => setShowPassword(v => !v)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                <EyeIcon open={showPassword} />
              </button>
            </div>
          </div>

          {error && <div className="login-error">{error}</div>}

          <button className="login-btn" type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in →'}
          </button>
        </form>

        {/* Demo credentials hint */}
        <div className="login-hint">
          <div className="login-hint-title">Demo accounts</div>
          <div className="login-hint-row">
            <span className="hint-role admin">Admin</span>
            <span>admin@heya.au / heya_admin_2026</span>
          </div>
          <div className="login-hint-row">
            <span className="hint-role client">Client</span>
            <span>admin@artel.com / artel_2026</span>
          </div>
          <div className="login-hint-row">
            <span className="hint-role client">Client</span>
            <span>admin@mvaallegal.com / mvaa_2026</span>
          </div>
        </div>
      </div>
    </div>
  )
}
