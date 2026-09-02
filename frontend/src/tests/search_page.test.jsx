/**
 * search_page.test.jsx — Search page component tests
 *
 * Covers:
 *  • Search bar renders with placeholder text
 *  • Suggestion pills are shown before any search
 *  • Clicking a suggestion pill fills the search input
 *  • Auto-search triggers on input (verified with waitFor — real 350ms debounce)
 *  • Result cards render with call_id and match count
 *  • "No matches found" shown when results.total === 0
 *  • Search meta text shows correct count
 *  • Clear (✕) button resets query and results
 *  • Short query (< 2 chars) does NOT trigger API call
 *  • API error shows empty results gracefully
 *
 * Note: Real timers are used (no fake timers) to avoid interference with
 * React's scheduler. waitFor timeout is set to 1500ms to cover the 350ms debounce.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// ── Mocks ─────────────────────────────────────────────────────────────────────
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { role: 'client', client_id: 'client_heya_001', email: 'test@artel.com' },
    token: 'fake.token.here',
  }),
}))

const mockApiGet = vi.fn()
vi.mock('../api/apiClient', () => ({
  default: { get: (...args) => mockApiGet(...args) },
}))

vi.mock('../components/MotionDrawer', () => ({
  default: ({ open, children }) => open ? <div data-testid="drawer">{children()}</div> : null,
}))

import Search from '../pages/client/Search'

// ── Helpers ───────────────────────────────────────────────────────────────────
const WAIT_OPTS = { timeout: 1500 }  // debounce is 350ms — well within 1500ms

function makeResults(n = 2, query = 'appointment') {
  return {
    query,
    total:   n,
    results: Array.from({ length: n }, (_, i) => ({
      call_id:          `call_${i + 1}`,
      match_count:      i + 1,
      rank:             0.9 - i * 0.1,
      snippets:         [`snippet text with <mark>${query}</mark> here`],
      direction:        'inbound',
      user_sentiment:   'positive',
      call_successful:  true,
      start_timestamp:  1700000000000,
      duration_ms:      60000,
      call_summary:     `Customer called about ${query}.`,
      engagement_score: 72.5,
      conversation_flow: 'smooth',
    })),
  }
}

function renderSearch() {
  render(<MemoryRouter><Search /></MemoryRouter>)
  return screen.getByPlaceholderText(/cancellation/i)
}

beforeEach(() => {
  mockApiGet.mockClear()
  mockNavigate.mockClear()
})
afterEach(() => {
  vi.clearAllMocks()
})


describe('Search page', () => {
  it('renders the search bar', () => {
    renderSearch()
    expect(screen.getByPlaceholderText(/cancellation/i)).toBeInTheDocument()
  })

  it('shows suggestion pills before any search', () => {
    renderSearch()
    expect(screen.getByText('cancellation')).toBeInTheDocument()
    expect(screen.getByText('appointment')).toBeInTheDocument()
    expect(screen.getByText('booking')).toBeInTheDocument()
  })

  it('clicking a suggestion pill fills the input', async () => {
    const input = renderSearch()
    fireEvent.click(screen.getByText('cancellation'))
    expect(input.value).toBe('cancellation')
  })

  it('short query (< 2 chars) does NOT call the API after debounce', async () => {
    renderSearch()
    const input = screen.getByPlaceholderText(/cancellation/i)
    act(() => { fireEvent.change(input, { target: { value: 'a' } }) })
    // Wait longer than debounce period — API must still not have been called
    await new Promise(r => setTimeout(r, 500))
    expect(mockApiGet).not.toHaveBeenCalled()
  })

  it('query ≥ 2 chars triggers API call after debounce delay', async () => {
    mockApiGet.mockResolvedValueOnce({ data: makeResults(3, 'ap') })
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'ap' } }) })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/search', {
        params: { q: 'ap', limit: 20 },
      })
    }, WAIT_OPTS)
  })

  it('result cards render with call_id', async () => {
    mockApiGet.mockResolvedValueOnce({ data: makeResults(2) })
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'appointment' } }) })

    await waitFor(() => {
      expect(screen.getByText('call_1')).toBeInTheDocument()
    }, WAIT_OPTS)
    expect(screen.getByText('call_2')).toBeInTheDocument()
  })

  it('search meta shows correct match count', async () => {
    mockApiGet.mockResolvedValueOnce({ data: makeResults(5) })
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'appointment' } }) })

    await waitFor(() => {
      expect(screen.getByText(/5 calls matched/i)).toBeInTheDocument()
    }, WAIT_OPTS)
  })

  it('shows "No matches found" when results are empty', async () => {
    mockApiGet.mockResolvedValueOnce({
      data: { query: 'xyzzyquux', total: 0, results: [] }
    })
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'xyzzyquux' } }) })

    await waitFor(() => {
      expect(screen.getByText(/no matches found/i)).toBeInTheDocument()
    }, WAIT_OPTS)
  })

  it('clear button resets query and hides results', async () => {
    mockApiGet.mockResolvedValueOnce({ data: makeResults(2) })
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'appointment' } }) })
    await waitFor(() => screen.getByText('call_1'), WAIT_OPTS)

    act(() => { fireEvent.click(screen.getByText('✕')) })

    await waitFor(() => {
      expect(screen.queryByText('call_1')).not.toBeInTheDocument()
    })
    expect(input.value).toBe('')
  })

  it('API error results in empty state gracefully (no crash)', async () => {
    mockApiGet.mockRejectedValueOnce(new Error('Network error'))
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'appointment' } }) })

    await waitFor(() => {
      expect(screen.getByText(/no calls matched/i)).toBeInTheDocument()
    }, WAIT_OPTS)
  })

  it('renders single match count correctly (no plural "s")', async () => {
    mockApiGet.mockResolvedValueOnce({ data: makeResults(1) })
    const input = renderSearch()
    act(() => { fireEvent.change(input, { target: { value: 'appointment' } }) })

    await waitFor(() => {
      // "1 call matched" not "1 calls matched"
      expect(screen.getByText(/1 call matched/i)).toBeInTheDocument()
    }, WAIT_OPTS)
  })
})
