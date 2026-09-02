/**
 * auth_context.test.jsx — AuthContext unit tests
 *
 * Covers:
 *  • AuthProvider mounts without crash, exposes expected context shape
 *  • login() stores token in localStorage and sets user from JWT payload
 *  • logout() clears localStorage and nulls user/token
 *  • Expired token on mount → cleared automatically, user stays null
 *  • Malformed token → cleared, user stays null
 *  • ready flag is true after initial effect runs
 *  • login() then logout() leaves clean state
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../context/AuthContext'

// ── JWT helpers ────────────────────────────────────────────────────────────────
function makeToken(payload) {
  const header  = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body    = btoa(JSON.stringify(payload))
  return `${header}.${body}.fakesig`
}

function futureToken() {
  return makeToken({
    sub:       'user_test_001',
    email:     'test@heya.au',
    role:      'client',
    client_id: 'client_heya_001',
    exp:       Math.floor(Date.now() / 1000) + 3600,
    iat:       Math.floor(Date.now() / 1000),
  })
}

function expiredToken() {
  return makeToken({
    sub:       'user_expired_001',
    email:     'expired@heya.au',
    role:      'client',
    client_id: 'client_heya_001',
    exp:       Math.floor(Date.now() / 1000) - 3600,
    iat:       Math.floor(Date.now() / 1000) - 7200,
  })
}

// ── Consumer component for testing ────────────────────────────────────────────
function TestConsumer() {
  const { user, token, login, logout, ready } = useAuth()
  return (
    <div>
      <div data-testid="ready">{String(ready)}</div>
      <div data-testid="user">{user ? JSON.stringify(user) : 'null'}</div>
      <div data-testid="token">{token || 'null'}</div>
      <button onClick={() => login(futureToken())}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

// ── Setup ─────────────────────────────────────────────────────────────────────
beforeEach(() => {
  localStorage.clear()
})
afterEach(() => {
  localStorage.clear()
})


describe('AuthContext', () => {
  it('renders without crashing', () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )
    expect(screen.getByTestId('ready')).toBeInTheDocument()
  })

  it('starts with null user and null token when localStorage is empty', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'))
    expect(screen.getByTestId('user').textContent).toBe('null')
    expect(screen.getByTestId('token').textContent).toBe('null')
  })

  it('ready flag becomes true after mount effect', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => {
      expect(screen.getByTestId('ready').textContent).toBe('true')
    })
  })

  it('login() stores token in localStorage', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => screen.getByTestId('ready'))

    act(() => { screen.getByText('login').click() })

    await waitFor(() => {
      expect(localStorage.getItem('heya_token')).not.toBeNull()
    })
  })

  it('login() sets user with payload fields', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => screen.getByTestId('ready'))

    act(() => { screen.getByText('login').click() })

    await waitFor(() => {
      const userText = screen.getByTestId('user').textContent
      expect(userText).not.toBe('null')
      const u = JSON.parse(userText)
      expect(u.email).toBe('test@heya.au')
      expect(u.role).toBe('client')
      expect(u.client_id).toBe('client_heya_001')
    })
  })

  it('logout() clears localStorage and nulls user', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => screen.getByTestId('ready'))

    act(() => { screen.getByText('login').click() })
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).not.toBe('null')
    })

    act(() => { screen.getByText('logout').click() })
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null')
      expect(screen.getByTestId('token').textContent).toBe('null')
      expect(localStorage.getItem('heya_token')).toBeNull()
    })
  })

  it('expired token in localStorage is cleared on mount — user stays null', async () => {
    localStorage.setItem('heya_token', expiredToken())

    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => {
      expect(screen.getByTestId('ready').textContent).toBe('true')
    })

    expect(screen.getByTestId('user').textContent).toBe('null')
    expect(localStorage.getItem('heya_token')).toBeNull()
  })

  it('malformed token in localStorage is cleared gracefully', async () => {
    localStorage.setItem('heya_token', 'this.isnot.avalidjwt!!!')

    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => {
      expect(screen.getByTestId('ready').textContent).toBe('true')
    })

    expect(screen.getByTestId('user').textContent).toBe('null')
    expect(localStorage.getItem('heya_token')).toBeNull()
  })

  it('valid token in localStorage on mount hydrates user automatically', async () => {
    localStorage.setItem('heya_token', futureToken())

    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => {
      const userText = screen.getByTestId('user').textContent
      expect(userText).not.toBe('null')
    })

    const u = JSON.parse(screen.getByTestId('user').textContent)
    expect(u.email).toBe('test@heya.au')
  })

  it('login() then immediate logout() produces clean state', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>)
    await waitFor(() => screen.getByTestId('ready'))

    act(() => { screen.getByText('login').click() })
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).not.toBe('null')
    })

    act(() => { screen.getByText('logout').click() })
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null')
      expect(screen.getByTestId('token').textContent).toBe('null')
    })
    expect(localStorage.getItem('heya_token')).toBeNull()
  })
})
