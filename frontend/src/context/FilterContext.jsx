import { createContext, useContext, useState } from 'react'

const FilterContext = createContext(null)

export function FilterProvider({ children }) {
  const [dateFrom,    setDateFrom]    = useState('')
  const [dateTo,      setDateTo]      = useState('')
  const [filterFlow,  setFilterFlow]  = useState('all')
  const [filterDir,   setFilterDir]   = useState('all')
  const [filterTraj,  setFilterTraj]  = useState('all')
  const [filterTopic, setFilterTopic] = useState('all')
  const [filterAgent, setFilterAgent] = useState('all')

  function clearFilters() {
    setDateFrom(''); setDateTo('')
    setFilterFlow('all'); setFilterDir('all')
    setFilterTraj('all'); setFilterTopic('all')
    setFilterAgent('all')
  }

  const hasActiveFilters = !!(dateFrom || dateTo || filterFlow !== 'all' ||
    filterDir !== 'all' || filterTraj !== 'all' || filterTopic !== 'all' ||
    filterAgent !== 'all')

  function applyTo(insights) {
    if (!hasActiveFilters) return insights
    return insights.filter(r => {
      if (filterFlow  !== 'all' && r.conversation_flow     !== filterFlow)  return false
      if (filterDir   !== 'all' && r.direction             !== filterDir)   return false
      if (filterTraj  !== 'all' && r.sentiment_trajectory  !== filterTraj)  return false
      if (filterTopic !== 'all' && r.topic                 !== filterTopic) return false
      if (filterAgent !== 'all' && r.agent_name            !== filterAgent) return false
      if (dateFrom && r.start_timestamp) {
        const d = new Date(r.start_timestamp)
        const localDate = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
        if (localDate < dateFrom) return false
      }
      if (dateTo && r.start_timestamp) {
        const d = new Date(r.start_timestamp)
        const localDate = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
        if (localDate > dateTo) return false
      }
      return true
    })
  }

  return (
    <FilterContext.Provider value={{
      dateFrom,    setDateFrom,
      dateTo,      setDateTo,
      filterFlow,  setFilterFlow,
      filterDir,   setFilterDir,
      filterTraj,  setFilterTraj,
      filterTopic, setFilterTopic,
      filterAgent, setFilterAgent,
      clearFilters,
      hasActiveFilters,
      applyTo,
    }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilters() {
  return useContext(FilterContext)
}
