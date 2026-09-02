import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../api/apiClient'

const REFRESH_INTERVAL = 60_000  // 60 seconds

export function useClientData() {
  const { user } = useAuth()
  const clientId = user?.client_id

  const [stats,       setStats]       = useState(null)
  const [insights,    setInsights]    = useState([])
  const [emotions,    setEmotions]    = useState(null)
  const [topics,      setTopics]      = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const fetchData = useCallback((silent = false) => {
    if (!clientId) return
    if (!silent) setLoading(true)

    Promise.allSettled([
      api.get(`/stats/${clientId}`),
      api.get(`/insights/${clientId}`),
      api.get(`/emotions/${clientId}`),
      api.get(`/topics/${clientId}`),
    ])
      .then(([s, i, e, t]) => {
        if (s.status === 'fulfilled') setStats(s.value.data)
        if (i.status === 'fulfilled') setInsights(i.value.data.insights || [])
        if (e.status === 'fulfilled') setEmotions(e.value.data)
        if (t.status === 'fulfilled') setTopics(t.value.data)
        setLastUpdated(new Date())
      })
      .finally(() => setLoading(false))
  }, [clientId])

  // Initial load
  useEffect(() => { fetchData() }, [fetchData])

  // Background auto-refresh — silently polls so the UI doesn't flicker
  useEffect(() => {
    if (!clientId) return
    const id = setInterval(() => fetchData(true), REFRESH_INTERVAL)
    return () => clearInterval(id)
  }, [clientId, fetchData])

  return { stats, insights, emotions, topics, loading, lastUpdated, clientId, refresh: fetchData }
}
