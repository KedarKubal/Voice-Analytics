/**
 * login_page.test.jsx — Login page component tests
 *
 * Covers:
 *  • Form renders: email input, password input, submit button, demo credentials
 *  • Password visibility toggle (eye button changes input type)
 *  • Successful login calls api.post and then login() from AuthContext
 *  • Admin login → navigate('/admin'), client login → navigate('/dashboard')
 *  • Failed login shows error message from response.data.detail
 *  • Network error shows generic fallback error message
 *  • Submit button shows "Signing in..." while loading
 *  • Already logged-in user is redirected without rendering the form
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

// ── Mocks ─────────────────────────────────────────────────────────────────────
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const mockLogin  = vi.fn()
const mockLogout = vi.fn()
let   mockUser   = null
let   mockReady  = true

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, token: null, login: mockLogin, logout: mockLogout, ready: mockReady }),
}))

const mockApiPost = vi.fn()
vi.mock('../api/apiClient', () => ({
  default: { post: (...args) => mockApiPost(...args) },
}))

// ── Import after mocks ─────────────────────────────────────────────────────────
import Login from '../pages/Login'

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

function makeToken(role = 'client') {
  const header  = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(JSON.stringify({
    sub: 'u1', email: 'test@test.com', role,
    client_id: 'client_heya_001',
    exp: Math.floor(Date.now() / 1000) + 3600,
  }))
  return `${header}.${payload}.fakesig`
}

beforeEach(() => {
  mockUser  = null
  mockReady = true
  mockNavigate.mockClear()
  mockLogin.mockClear()
  mockApiPost.mockClear()
})
afterEach(() => {
  vi.clearAllMocks()
})


describe('Login page', () => {
  it('renders without crashing', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('renders email input', () => {
    renderLogin()
    expect(screen.getByPlaceholderText(/you@example.com/i)).toBeInTheDocument()
  })

  it('renders password input (hidden by default)', () => {
    renderLogin()
    const pwd = screen.getByPlaceholderText('••••••••')
    expect(pwd).toHaveAttribute('type', 'password')
  })

  it('renders demo credentials hint section', () => {
    renderLogin()
    expect(screen.getByText(/demo accounts/i)).toBeInTheDocument()
    expect(screen.getByText(/admin@heya\.au/i)).toBeInTheDocument()
  })

  it('password visibility toggle switches input type to text', async () => {
    renderLogin()
    const eyeBtn = screen.getByLabelText(/show password/i)
    const pwdInput = screen.getByPlaceholderText('••••••••')

    fireEvent.click(eyeBtn)
    expect(pwdInput).toHaveAttribute('type', 'text')
  })

  it('password visibility toggle switches back to password type', async () => {
    renderLogin()
    const eyeBtn = screen.getByLabelText(/show password/i)
    const pwdInput = screen.getByPlaceholderText('••••••••')

    fireEvent.click(eyeBtn)
    fireEvent.click(eyeBtn)
    expect(pwdInput).toHaveAttribute('type', 'password')
  })

  it('successful client login calls login() and navigates to /dashboard', async () => {
    const token = makeToken('client')
    mockApiPost.mockResolvedValueOnce({
      data: { access_token: token, role: 'client', name: 'Test User' }
    })

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText(/you@example.com/i), 'test@artel.com')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'artel_2026')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/auth/login', {
        email: 'test@artel.com',
        password: 'artel_2026',
      })
      expect(mockLogin).toHaveBeenCalledWith(token, { name: 'Test User' })
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('successful admin login navigates to /admin', async () => {
    const token = makeToken('heya_admin')
    mockApiPost.mockResolvedValueOnce({
      data: { access_token: token, role: 'heya_admin', name: 'Admin' }
    })

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText(/you@example.com/i), 'admin@heya.au')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'heya_admin_2026')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/admin')
    })
  })

  it('shows API error message on failed login', async () => {
    mockApiPost.mockRejectedValueOnce({
      response: { data: { detail: 'Invalid credentials' } }
    })

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText(/you@example.com/i), 'wrong@email.com')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'wrongpass')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
    })
  })

  it('shows generic fallback error on network failure', async () => {
    mockApiPost.mockRejectedValueOnce(new Error('Network Error'))

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText(/you@example.com/i), 'a@b.com')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'pass')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/login failed/i)).toBeInTheDocument()
    })
  })

  it('button shows "Signing in..." while request is pending', async () => {
    // Never resolve so we can inspect loading state
    mockApiPost.mockImplementationOnce(() => new Promise(() => {}))

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText(/you@example.com/i), 'a@b.com')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'pass')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()
    })
  })

  it('already-logged-in user with admin role is redirected to /admin', async () => {
    mockUser  = { role: 'heya_admin', email: 'admin@heya.au' }
    mockReady = true

    renderLogin()

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/admin', { replace: true })
    })
  })

  it('already-logged-in client user is redirected to /dashboard', async () => {
    mockUser  = { role: 'client', email: 'user@artel.com' }
    mockReady = true

    renderLogin()

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true })
    })
  })
})
