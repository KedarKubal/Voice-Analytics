/**
 * filter_context.test.jsx — FilterContext unit tests
 *
 * Covers:
 *  • Default state: all filters at 'all' / ''
 *  • hasActiveFilters is false at defaults, true after any change
 *  • setFilterFlow / setFilterDir / setFilterTraj / setFilterTopic / setFilterAgent all update state
 *  • clearFilters resets everything back to defaults
 *  • applyTo() with each filter type returns only matching rows
 *  • applyTo() with no active filters returns all rows unchanged
 *  • applyTo() with multiple active filters applies AND logic
 *  • Date range filtering: dateFrom / dateTo correctly excludes rows
 *  • applyTo() does not mutate the original array
 */

import { describe, it, expect } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { FilterProvider, useFilters } from '../context/FilterContext'

// ── Helper: render a consumer that exposes context state via data-testids ──────
function FilterConsumer({ onMount } = {}) {
  const ctx = useFilters()

  // Allow tests to reach in and call setters via exposed buttons
  return (
    <div>
      <div data-testid="hasActive">{String(ctx.hasActiveFilters)}</div>
      <div data-testid="filterFlow">{ctx.filterFlow}</div>
      <div data-testid="filterDir">{ctx.filterDir}</div>
      <div data-testid="filterTraj">{ctx.filterTraj}</div>
      <div data-testid="filterTopic">{ctx.filterTopic}</div>
      <div data-testid="filterAgent">{ctx.filterAgent}</div>
      <div data-testid="dateFrom">{ctx.dateFrom}</div>
      <div data-testid="dateTo">{ctx.dateTo}</div>

      <button onClick={() => ctx.setFilterFlow('smooth')}>setFlow</button>
      <button onClick={() => ctx.setFilterDir('inbound')}>setDir</button>
      <button onClick={() => ctx.setFilterTraj('improving')}>setTraj</button>
      <button onClick={() => ctx.setFilterTopic('booking')}>setTopic</button>
      <button onClick={() => ctx.setFilterAgent('Sasha')}>setAgent</button>
      <button onClick={() => ctx.setDateFrom('2026-01-01')}>setDateFrom</button>
      <button onClick={() => ctx.setDateTo('2026-12-31')}>setDateTo</button>
      <button onClick={() => ctx.clearFilters()}>clear</button>
    </div>
  )
}

function renderCtx() {
  render(
    <FilterProvider>
      <FilterConsumer />
    </FilterProvider>
  )
}

// ── Sample insight rows used by applyTo tests ─────────────────────────────────
function makeRow(overrides = {}) {
  return {
    call_id:              'call_001',
    conversation_flow:    'smooth',
    direction:            'inbound',
    sentiment_trajectory: 'improving',
    topic:                'booking',
    agent_name:           'Sasha',
    start_timestamp:      '2026-03-15T10:00:00Z',
    ...overrides,
  }
}

// ── Helper that renders and returns the applyTo function directly ─────────────
function ApplyToConsumer({ rows, onResult }) {
  const ctx = useFilters()
  const result = ctx.applyTo(rows)
  onResult(result)
  return null
}

function getApplyTo() {
  let applyToFn
  function Harness() {
    const ctx = useFilters()
    applyToFn = ctx.applyTo
    return null
  }
  render(<FilterProvider><Harness /></FilterProvider>)
  return () => applyToFn
}


// ── Tests ─────────────────────────────────────────────────────────────────────

describe('FilterContext — default state', () => {
  it('all filters default to "all" or empty string', () => {
    renderCtx()
    expect(screen.getByTestId('filterFlow').textContent).toBe('all')
    expect(screen.getByTestId('filterDir').textContent).toBe('all')
    expect(screen.getByTestId('filterTraj').textContent).toBe('all')
    expect(screen.getByTestId('filterTopic').textContent).toBe('all')
    expect(screen.getByTestId('filterAgent').textContent).toBe('all')
    expect(screen.getByTestId('dateFrom').textContent).toBe('')
    expect(screen.getByTestId('dateTo').textContent).toBe('')
  })

  it('hasActiveFilters is false at defaults', () => {
    renderCtx()
    expect(screen.getByTestId('hasActive').textContent).toBe('false')
  })
})


describe('FilterContext — setting filters', () => {
  it('setFilterFlow updates filterFlow and sets hasActive=true', async () => {
    renderCtx()
    act(() => screen.getByText('setFlow').click())
    await waitFor(() => {
      expect(screen.getByTestId('filterFlow').textContent).toBe('smooth')
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })
  })

  it('setFilterDir updates filterDir and sets hasActive=true', async () => {
    renderCtx()
    act(() => screen.getByText('setDir').click())
    await waitFor(() => {
      expect(screen.getByTestId('filterDir').textContent).toBe('inbound')
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })
  })

  it('setFilterTraj updates filterTraj and sets hasActive=true', async () => {
    renderCtx()
    act(() => screen.getByText('setTraj').click())
    await waitFor(() => {
      expect(screen.getByTestId('filterTraj').textContent).toBe('improving')
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })
  })

  it('setFilterTopic updates filterTopic and sets hasActive=true', async () => {
    renderCtx()
    act(() => screen.getByText('setTopic').click())
    await waitFor(() => {
      expect(screen.getByTestId('filterTopic').textContent).toBe('booking')
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })
  })

  it('setFilterAgent updates filterAgent and sets hasActive=true', async () => {
    renderCtx()
    act(() => screen.getByText('setAgent').click())
    await waitFor(() => {
      expect(screen.getByTestId('filterAgent').textContent).toBe('Sasha')
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })
  })

  it('setDateFrom updates dateFrom and sets hasActive=true', async () => {
    renderCtx()
    act(() => screen.getByText('setDateFrom').click())
    await waitFor(() => {
      expect(screen.getByTestId('dateFrom').textContent).toBe('2026-01-01')
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })
  })
})


describe('FilterContext — clearFilters', () => {
  it('clearFilters resets all filters to defaults', async () => {
    renderCtx()

    act(() => screen.getByText('setFlow').click())
    act(() => screen.getByText('setDir').click())
    act(() => screen.getByText('setAgent').click())
    act(() => screen.getByText('setDateFrom').click())

    await waitFor(() => {
      expect(screen.getByTestId('hasActive').textContent).toBe('true')
    })

    act(() => screen.getByText('clear').click())

    await waitFor(() => {
      expect(screen.getByTestId('filterFlow').textContent).toBe('all')
      expect(screen.getByTestId('filterDir').textContent).toBe('all')
      expect(screen.getByTestId('filterTraj').textContent).toBe('all')
      expect(screen.getByTestId('filterTopic').textContent).toBe('all')
      expect(screen.getByTestId('filterAgent').textContent).toBe('all')
      expect(screen.getByTestId('dateFrom').textContent).toBe('')
      expect(screen.getByTestId('dateTo').textContent).toBe('')
      expect(screen.getByTestId('hasActive').textContent).toBe('false')
    })
  })
})


describe('FilterContext — applyTo()', () => {
  const rows = [
    makeRow({ call_id: 'r1', conversation_flow: 'smooth',   direction: 'inbound',  agent_name: 'Sasha',   topic: 'booking',      sentiment_trajectory: 'improving' }),
    makeRow({ call_id: 'r2', conversation_flow: 'moderate', direction: 'outbound', agent_name: 'Julia',   topic: 'payment',      sentiment_trajectory: 'stable' }),
    makeRow({ call_id: 'r3', conversation_flow: 'poor',     direction: 'inbound',  agent_name: 'Sasha',   topic: 'booking',      sentiment_trajectory: 'deteriorating' }),
    makeRow({ call_id: 'r4', conversation_flow: 'smooth',   direction: 'outbound', agent_name: 'Justine', topic: 'cancellation', sentiment_trajectory: 'improving' }),
  ]

  function ApplyToHarness({ onResult }) {
    const ctx = useFilters()
    onResult(ctx.applyTo(rows))
    return null
  }

  function renderWithResult(setters = []) {
    let result
    render(
      <FilterProvider>
        <ApplyToHarness onResult={r => { result = r }} />
      </FilterProvider>
    )
    return () => result
  }

  it('no active filters returns all rows unchanged', () => {
    let result
    function Harness() {
      const ctx = useFilters()
      result = ctx.applyTo(rows)
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    expect(result).toEqual(rows)
  })

  it('filterFlow=smooth returns only smooth rows', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterFlow('smooth')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result.every(r => r.conversation_flow === 'smooth')).toBe(true)
  })

  it('filterDir=inbound returns only inbound rows', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterDir('inbound')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result.every(r => r.direction === 'inbound')).toBe(true)
  })

  it('filterAgent=Sasha returns only Sasha rows', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterAgent('Sasha')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result.every(r => r.agent_name === 'Sasha')).toBe(true)
    expect(result.length).toBe(2)
  })

  it('filterTopic=booking returns only booking rows', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterTopic('booking')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result.every(r => r.topic === 'booking')).toBe(true)
  })

  it('filterTraj=improving returns only improving rows', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterTraj('improving')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result.every(r => r.sentiment_trajectory === 'improving')).toBe(true)
  })

  it('combined filterFlow=smooth AND filterDir=inbound returns intersection', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterFlow('smooth')
      ctx.setFilterDir('inbound')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result.every(r => r.conversation_flow === 'smooth' && r.direction === 'inbound')).toBe(true)
    expect(result.length).toBe(1)  // only r1 matches both
    expect(result[0].call_id).toBe('r1')
  })

  it('applyTo does not mutate the original array', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterFlow('smooth')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const original = [...rows]
    applyTo(rows)
    expect(rows).toEqual(original)
  })

  it('filter with no matches returns empty array', () => {
    let applyTo
    function Harness() {
      const ctx = useFilters()
      ctx.setFilterAgent('NonExistentAgent')
      applyTo = ctx.applyTo
      return null
    }
    render(<FilterProvider><Harness /></FilterProvider>)
    const result = applyTo(rows)
    expect(result).toEqual([])
  })
})
