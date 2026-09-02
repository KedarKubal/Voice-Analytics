import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import api from '../api/apiClient'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend, ReferenceLine,
  LineChart, Line, AreaChart, Area,
  PieChart, Pie, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'
import AudioPlayer from '../components/AudioPlayer'
import '../App.css'
import './AdminApp.css'

// ── Motion presets ────────────────────────────────────────────────────────────
const E = [0.22, 1, 0.36, 1]
const fadeUp    = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: E } } }
const fadeIn    = { hidden: { opacity: 0 },         show: { opacity: 1, transition: { duration: 0.3 } } }
const kpiStagger = { hidden: {}, show: { transition: { staggerChildren: 0.07 } } }
const rowStagger = { hidden: {}, show: { transition: { staggerChildren: 0.04 } } }

const TT = {
  contentStyle: { background: 'var(--tooltip-bg)', border: '1px solid var(--border2)', borderRadius: 6, fontFamily: "'DM Mono'" },
  labelStyle:   { color: 'var(--tooltip-text)', fontSize: 11 },
  itemStyle:    { color: 'var(--tooltip-item)', fontSize: 11 },
}

const GRADE_COLORS  = { A: '#22c55e', B: '#6ee7b7', C: '#fbbf24', D: '#fb923c', F: '#ef4444' }
const EMOTION_COLORS = {
  happy: '#22c55e', sad: '#60a5fa', angry: '#ef4444',
  neutral: '#94a3b8', fearful: '#fb923c', disgusted: '#a3e635', surprised: '#c084fc',
}
const healthColor = { healthy: '#22c55e', warning: '#fbbf24', critical: '#ef4444', inactive: '#475569' }

function clientHealth(c) {
  if (!c.total_calls) return 'inactive'
  if (c.pending_queue > 10 || c.success_rate < 40) return 'critical'
  if (c.pending_queue > 3  || c.success_rate < 65) return 'warning'
  return 'healthy'
}

function meanOf(arr, key) {
  const vals = arr.map(r => parseFloat(r[key]) || 0).filter(v => v > 0)
  return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0
}

function modeOf(arr, key) {
  const counts = {}
  arr.forEach(r => { if (r[key]) counts[r[key]] = (counts[r[key]] || 0) + 1 })
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || '—'
}

function IcoMic() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ width: '100%', height: '100%' }}>
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" x2="12" y1="19" y2="22"/>
    </svg>
  )
}

function QualityBadge({ score, grade }) {
  if (score == null) return <span style={{ color: 'var(--muted)' }}>—</span>
  const color = GRADE_COLORS[grade] || '#64748b'
  return <span style={{ color, fontWeight: 700, fontFamily: "'DM Mono'" }}>{grade}<span style={{ opacity: 0.6, fontWeight: 400, marginLeft: 3 }}>{score}</span></span>
}

function EmotionBadge({ emotion, score }) {
  const color = EMOTION_COLORS[emotion]
  if (!color) return null
  return (
    <span className="emotion-badge" style={{ borderColor: color + '40', color }}>
      {emotion}
      {score != null && <span style={{ opacity: 0.6, fontSize: 9, marginLeft: 3 }}>{Math.round(score * 100)}%</span>}
    </span>
  )
}

const REFRESH_SEC = 30

const ADMIN_ALERT_TYPES = [
  { id: 'high_silence',             label: 'High Silence Ratio',        desc: 'Fires when >10% of calls exceed 30% dead air' },
  { id: 'poor_conversation_flow',   label: 'Poor Conversation Flow',     desc: 'Fires when >40% of calls are classified as poor flow' },
  { id: 'low_success_rate',         label: 'Low Call Success Rate',      desc: 'Fires when success rate falls below 80%' },
  { id: 'low_engagement',           label: 'Low Engagement Score',       desc: 'Fires when average engagement drops below 65/100' },
  { id: 'deteriorating_trajectory', label: 'Deteriorating Trajectories', desc: 'Fires when >35% of calls show declining caller energy' },
  { id: 'high_interruptions',       label: 'High Interruption Rate',     desc: 'Fires when average interruptions exceed 3 per call' },
  { id: 'negative_sentiment',       label: 'High Negative Sentiment',    desc: 'Fires when >25% of callers end with negative sentiment' },
  { id: 'weekly_digest',            label: 'Weekly Performance Digest',  desc: 'Summary email every week with KPIs and top recommendations' },
]

const ALERT_STATUS_META = {
  sent:     { color: '#22c55e', label: 'Sent'    },
  failed:   { color: '#ef4444', label: 'Failed'  },
  cooldown: { color: '#64748b', label: 'Cooldown' },
}

export default function AdminApp() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()

  const [tab,           setTab]           = useState('overview')
  const [feedCalls,     setFeedCalls]     = useState([])
  const [feedLoad,      setFeedLoad]      = useState(false)
  const [feedFetched,   setFeedFetched]   = useState(false)
  const [feedNewIds,    setFeedNewIds]    = useState(new Set())
  const [feedSync,      setFeedSync]      = useState(null)
  const [feedCountdown, setFeedCountdown] = useState(5)
  const feedSeenRef   = useRef(new Set())
  const feedFiltersRef = useRef({})

  // Feed filter state
  const [feedFilterClient,   setFeedFilterClient]   = useState('')
  const [feedFilterAgent,    setFeedFilterAgent]    = useState('')
  const [feedFilterDateFrom, setFeedFilterDateFrom] = useState('')
  const [feedFilterDateTo,   setFeedFilterDateTo]   = useState('')
  const [feedFilterDir,      setFeedFilterDir]      = useState('')
  const [feedFilterFlow,     setFeedFilterFlow]     = useState('')
  const [feedFilterTraj,     setFeedFilterTraj]     = useState('')
  const [feedFilterSent,     setFeedFilterSent]     = useState('')
  const [feedFilterTopic,    setFeedFilterTopic]    = useState('')
  const [feedAgents,         setFeedAgents]         = useState([])
  const [overview,      setOverview]      = useState(null)
  const [loading,       setLoading]       = useState(true)
  const [countdown,     setCountdown]     = useState(REFRESH_SEC)
  const [lastSync,      setLastSync]      = useState(null)
  const [selected,      setSelected]      = useState(null)
  const [clientStats,   setClientStats]   = useState(null)
  const [clientInsights,setClientInsights]= useState([])
  const [clientRecs,    setClientRecs]    = useState([])
  const [drillLoad,     setDrillLoad]     = useState(false)
  const [recsExpanded,  setRecsExpanded]  = useState(null)
  const [callRow,       setCallRow]       = useState(null)
  const [callDetail,    setCallDetail]    = useState(null)
  const [callDetailLoad,setCallDetailLoad]= useState(false)
  const [users,         setUsers]         = useState([])
  const [usersLoad,     setUsersLoad]     = useState(false)
  const [usersFetched,  setUsersFetched]  = useState(false)
  const [createForm,    setCreateForm]    = useState({ email: '', password: '', role: 'client', client_id: '' })
  const [createMsg,     setCreateMsg]     = useState({ err: '', ok: '' })
  const [creating,      setCreating]      = useState(false)
  const [deleting,      setDeleting]      = useState(null)

  // Alerts tab state
  const [alertClientId, setAlertClientId] = useState('')
  const [alertConfigs,  setAlertConfigs]  = useState({})
  const [alertHistory,  setAlertHistory]  = useState([])
  const [alertDrafts,   setAlertDrafts]   = useState({})
  const [alertLoading,  setAlertLoading]  = useState(false)
  const [alertSaving,   setAlertSaving]   = useState(null)
  const [alertTesting,  setAlertTesting]  = useState(null)
  const [alertRunning,  setAlertRunning]  = useState(false)
  const [alertToast,    setAlertToast]    = useState(null)

  const [analyticsClientId, setAnalyticsClientId] = useState('')
  const [analyticsStats,    setAnalyticsStats]    = useState(null)
  const [analyticsInsights, setAnalyticsInsights] = useState([])
  const [analyticsLoad,     setAnalyticsLoad]     = useState(false)
  const [analyticsRefresh,  setAnalyticsRefresh]  = useState(0)

  // Intelligence tab
  const [intelStats,    setIntelStats]    = useState(null)
  const [intelLoad,     setIntelLoad]     = useState(false)
  const [intelClientId, setIntelClientId] = useState('')
  const [intelDays,     setIntelDays]     = useState(30)
  const [intelRefresh,  setIntelRefresh]  = useState(0)
  const [chatClientId,  setChatClientId]  = useState('')
  const [chatMessages,  setChatMessages]  = useState([{ role: 'system', text: 'Select a client above and ask anything about their call data — every answer is grounded in real call records.' }])
  const [chatInput,     setChatInput]     = useState('')
  const [chatLoading,   setChatLoading]   = useState(false)
  const chatBottomRef = useRef(null)

  function showAlertToast(msg, ok = true) {
    setAlertToast({ msg, ok })
    setTimeout(() => setAlertToast(null), 3500)
  }

  function fetchAlerts(cid) {
    if (!cid) return
    setAlertLoading(true)
    Promise.all([api.get(`/alerts/config/${cid}`), api.get(`/alerts/history/${cid}`)])
      .then(([cfg, hist]) => {
        const cfgMap = {}
        ;(cfg.data.configs || []).forEach(c => { cfgMap[c.alert_type] = c })
        setAlertConfigs(cfgMap)
        setAlertHistory(hist.data.logs || [])
        const d = {}
        ADMIN_ALERT_TYPES.forEach(({ id }) => {
          d[id] = { enabled: cfgMap[id]?.enabled ?? false, email: cfgMap[id]?.email ?? '', min_priority: cfgMap[id]?.min_priority ?? 'warning' }
        })
        setAlertDrafts(d)
      })
      .catch(() => showAlertToast('Failed to load alert settings', false))
      .finally(() => setAlertLoading(false))
  }

  async function saveAlertConfig(type) {
    const draft = alertDrafts[type]
    if (!draft?.email?.includes('@')) { showAlertToast('Enter a valid email address', false); return }
    setAlertSaving(type)
    try {
      await api.post(`/alerts/config/${alertClientId}`, { alert_type: type, enabled: draft.enabled, email: draft.email, min_priority: draft.min_priority })
      showAlertToast(`Saved — ${type.replace(/_/g, ' ')}`)
      const r = await api.get(`/alerts/config/${alertClientId}`)
      const cfgMap = {}
      ;(r.data.configs || []).forEach(c => { cfgMap[c.alert_type] = c })
      setAlertConfigs(cfgMap)
    } catch { showAlertToast('Save failed', false) }
    finally { setAlertSaving(null) }
  }

  async function sendAlertTest(type) {
    const draft = alertDrafts[type]
    if (!draft?.email?.includes('@')) { showAlertToast('Enter a valid email address', false); return }
    setAlertTesting(type)
    try {
      const r = await api.post(`/alerts/test/${alertClientId}`, { alert_type: type, enabled: true, email: draft.email, min_priority: draft.min_priority })
      showAlertToast(r.data.status === 'sent' ? `Test sent to ${draft.email}` : `Failed: ${r.data.message}`, r.data.status === 'sent')
    } catch { showAlertToast('Test failed — check SMTP settings', false) }
    finally { setAlertTesting(null) }
  }

  async function runAlertChecks() {
    setAlertRunning(true)
    try {
      await api.post(`/alerts/check/${alertClientId}`)
      showAlertToast('Alert checks running in background')
      setTimeout(async () => {
        const r = await api.get(`/alerts/history/${alertClientId}`)
        setAlertHistory(r.data.logs || [])
      }, 3000)
    } catch { showAlertToast('Failed to trigger checks', false) }
    finally { setAlertRunning(false) }
  }

  function updateAlertDraft(type, field, value) {
    setAlertDrafts(d => ({ ...d, [type]: { ...d[type], [field]: value } }))
  }

  function fetchOverview(silent = false) {
    if (!silent) setLoading(true)
    api.get('/admin/clients/overview')
      .then(r => { setOverview(r.data); setLastSync(new Date()); setCountdown(REFRESH_SEC) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchOverview() }, [])
  useEffect(() => {
    const tick = setInterval(() => {
      setCountdown(c => { if (c <= 1) { fetchOverview(true); return REFRESH_SEC } return c - 1 })
    }, 1000)
    return () => clearInterval(tick)
  }, [])

  useEffect(() => {
    if (!callRow) { setCallDetail(null); return }
    setCallDetailLoad(true)
    api.get(`/call/${callRow.call_id}`)
      .then(r => setCallDetail(r.data))
      .catch(() => setCallDetail(null))
      .finally(() => setCallDetailLoad(false))
  }, [callRow])

  const fetchAdminFeed = useCallback((silent = false, filters = {}) => {
    if (!silent) setFeedLoad(true)
    const p = new URLSearchParams({ limit: 500 })
    if (filters.client_id)  p.set('client_id',  filters.client_id)
    if (filters.agent_id)   p.set('agent_id',   filters.agent_id)
    if (filters.date_from)  p.set('date_from',  filters.date_from)
    if (filters.date_to)    p.set('date_to',    filters.date_to)
    if (filters.direction)  p.set('direction',  filters.direction)
    if (filters.flow)       p.set('flow',       filters.flow)
    if (filters.trajectory) p.set('trajectory', filters.trajectory)
    if (filters.sentiment)  p.set('sentiment',  filters.sentiment)
    if (filters.topic)      p.set('topic',      filters.topic)
    api.get(`/admin/calls?${p}`)
      .then(r => {
        const fresh = r.data.calls || []
        const freshNew = new Set()
        fresh.forEach(c => {
          if (!feedSeenRef.current.has(c.call_id)) {
            freshNew.add(c.call_id)
            feedSeenRef.current.add(c.call_id)
          }
        })
        setFeedCalls(fresh)
        if (freshNew.size > 0) {
          setFeedNewIds(freshNew)
          setTimeout(() => setFeedNewIds(new Set()), 3500)
        }
        setFeedSync(new Date())
        setFeedCountdown(5)
        setFeedFetched(true)
      })
      .catch(console.error)
      .finally(() => setFeedLoad(false))
  }, [])

  // Keep filters ref in sync so auto-refresh timer always uses latest filters
  useEffect(() => {
    feedFiltersRef.current = {
      client_id:  feedFilterClient   || null,
      agent_id:   feedFilterAgent    || null,
      date_from:  feedFilterDateFrom ? new Date(feedFilterDateFrom).getTime()           : null,
      date_to:    feedFilterDateTo   ? new Date(feedFilterDateTo + 'T23:59:59').getTime(): null,
      direction:  feedFilterDir  || null,
      flow:       feedFilterFlow || null,
      trajectory: feedFilterTraj || null,
      sentiment:  feedFilterSent || null,
      topic:      feedFilterTopic|| null,
    }
  }, [feedFilterClient, feedFilterAgent, feedFilterDateFrom, feedFilterDateTo,
      feedFilterDir, feedFilterFlow, feedFilterTraj, feedFilterSent, feedFilterTopic])

  // Fetch agents when client filter changes; reset agent selection
  useEffect(() => {
    setFeedFilterAgent('')
    if (!feedFilterClient) { setFeedAgents([]); return }
    api.get(`/admin/agents?client_id=${feedFilterClient}`)
      .then(r => setFeedAgents(r.data.agents || []))
      .catch(() => setFeedAgents([]))
  }, [feedFilterClient])

  // Re-fetch when tab opens or any filter changes
  useEffect(() => {
    if (tab !== 'feed') return
    const f = feedFiltersRef.current
    fetchAdminFeed(false, f)
  }, [tab, feedFilterClient, feedFilterAgent, feedFilterDateFrom, feedFilterDateTo,
      feedFilterDir, feedFilterFlow, feedFilterTraj, feedFilterSent, feedFilterTopic])

  // Auto-refresh timer — passes latest filters via ref
  useEffect(() => {
    if (tab !== 'feed') return
    const tick = setInterval(() => {
      setFeedCountdown(c => { if (c <= 1) { fetchAdminFeed(true, feedFiltersRef.current); return 5 } return c - 1 })
    }, 1000)
    return () => clearInterval(tick)
  }, [tab, fetchAdminFeed])

  useEffect(() => {
    if (tab === 'users' && !usersFetched) {
      setUsersLoad(true)
      api.get('/admin/users')
        .then(r => { setUsers(r.data.users || []); setUsersFetched(true) })
        .catch(console.error)
        .finally(() => setUsersLoad(false))
    }
  }, [tab, usersFetched])

  useEffect(() => {
    const c = overview?.clients
    if (tab === 'alerts' && !alertClientId && c?.length > 0) {
      setAlertClientId(c[0].client_id)
    }
  }, [tab, alertClientId, overview])

  useEffect(() => {
    if (tab === 'alerts' && alertClientId) fetchAlerts(alertClientId)
  }, [tab, alertClientId])

  useEffect(() => {
    const c = overview?.clients
    if (tab === 'analytics' && !analyticsClientId && c?.length > 0) {
      setAnalyticsClientId(c[0].client_id)
    }
  }, [tab, analyticsClientId, overview])

  useEffect(() => {
    if (tab !== 'analytics' || !analyticsClientId) return
    setAnalyticsLoad(true)
    Promise.all([api.get(`/stats/${analyticsClientId}`), api.get(`/insights/${analyticsClientId}`)])
      .then(([s, i]) => { setAnalyticsStats(s.data); setAnalyticsInsights(i.data.insights || []) })
      .catch(console.error)
      .finally(() => setAnalyticsLoad(false))
  }, [tab, analyticsClientId, analyticsRefresh])

  // Intelligence — auto-select first client for chat
  useEffect(() => {
    const c = overview?.clients
    if (tab === 'intelligence' && !chatClientId && c?.length > 0) setChatClientId(c[0].client_id)
  }, [tab, chatClientId, overview])

  // Intelligence — fetch query analytics
  useEffect(() => {
    if (tab !== 'intelligence') return
    setIntelLoad(true)
    const p = new URLSearchParams({ days: intelDays })
    if (intelClientId) p.set('client_id', intelClientId)
    api.get(`/admin/query-analytics?${p}`)
      .then(r => setIntelStats(r.data))
      .catch(console.error)
      .finally(() => setIntelLoad(false))
  }, [tab, intelClientId, intelDays, intelRefresh])

  // Intelligence — scroll chat to bottom
  useEffect(() => { chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMessages])

  async function sendAdminChat(q) {
    const question = (q || chatInput).trim()
    if (!question || chatLoading || !chatClientId) return
    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', text: question }])
    setChatLoading(true)

    const history = chatMessages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-12)
      .map(m => ({ role: m.role, content: m.text }))

    try {
      const res = await api.post('/query', { question, client_id: chatClientId, history })
      setChatMessages(prev => [...prev, { role: 'assistant', text: res.data.answer, route: res.data.route, confidence: res.data.confidence }])
    } catch (e) {
      setChatMessages(prev => [...prev, { role: 'assistant', text: e.response?.data?.detail || 'Query failed.', route: 'error' }])
    } finally {
      setChatLoading(false)
    }
  }

  function clearFeedFilters() {
    setFeedFilterClient(''); setFeedFilterAgent('');   setFeedFilterDateFrom('')
    setFeedFilterDateTo(''); setFeedFilterDir('');     setFeedFilterFlow('')
    setFeedFilterTraj('');   setFeedFilterSent('');    setFeedFilterTopic('')
  }

  function exportFeedCSV() {
    if (!feedCalls.length) return
    const headers = [
      'Call ID','Client','Agent','Agent Role','Direction','Date','Time','Duration (s)',
      'Processing Status','Quality Grade','Quality Score','Engagement /100',
      'Silence %','Interruptions','Hesitations','Flow','Trajectory',
      'Sentiment','Emotion','Topic','Agent Talk (s)','Customer Talk (s)','Outcome',
    ]
    const rows = feedCalls.map(c => [
      c.call_id,
      c.client_name || c.client_id || '',
      c.agent_name  || '',
      (c.agent_role || '').replace(/_/g,' '),
      c.direction   || '',
      c.start_timestamp ? new Date(c.start_timestamp).toLocaleDateString('en-AU') : '',
      c.start_timestamp ? new Date(c.start_timestamp).toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit'}) : '',
      c.duration_ms ? Math.round(c.duration_ms/1000) : '',
      c.processing_status || '',
      c.quality_grade  || '',
      c.quality_score  ?? '',
      c.engagement_score  != null ? parseFloat(c.engagement_score).toFixed(1)  : '',
      c.silence_ratio     != null ? (c.silence_ratio*100).toFixed(1)            : '',
      c.interruption_count ?? '',
      c.hesitation_count   ?? '',
      c.conversation_flow   || '',
      c.sentiment_trajectory|| '',
      c.user_sentiment      || '',
      c.dominant_emotion    || '',
      c.topic               || '',
      c.agent_talk_time_sec    != null ? parseFloat(c.agent_talk_time_sec).toFixed(1)    : '',
      c.customer_talk_time_sec != null ? parseFloat(c.customer_talk_time_sec).toFixed(1) : '',
      c.call_successful === true ? 'Success' : c.call_successful === false ? 'Failed' : 'Unknown',
    ])
    const csv = [headers,...rows].map(r=>r.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\n')
    const blob = new Blob(['﻿'+csv],{type:'text/csv;charset=utf-8'})
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = `heya_calls_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function drillInto(client) {
    setSelected(client); setDrillLoad(true); setClientRecs([]); setRecsExpanded(null)
    try {
      const [s, i, r] = await Promise.all([
        api.get(`/stats/${client.client_id}`),
        api.get(`/insights/${client.client_id}`),
        api.get(`/recommendations/${client.client_id}`),
      ])
      setClientStats(s.data)
      setClientInsights(i.data.insights || [])
      setClientRecs(r.data.recommendations || [])
    } catch (e) { console.error(e) }
    finally { setDrillLoad(false) }
  }

  async function handleCreateUser(e) {
    e.preventDefault(); setCreateMsg({ err: '', ok: '' }); setCreating(true)
    try {
      await api.post('/admin/users', {
        email: createForm.email, password: createForm.password, role: createForm.role,
        client_id: createForm.role === 'client' ? createForm.client_id : null,
      })
      setCreateMsg({ err: '', ok: `User ${createForm.email} created.` })
      setCreateForm({ email: '', password: '', role: 'client', client_id: '' })
      const r = await api.get('/admin/users'); setUsers(r.data.users || [])
    } catch (err) {
      setCreateMsg({ ok: '', err: err.response?.data?.detail || 'Failed to create user' })
    } finally { setCreating(false) }
  }

  async function handleDeleteUser(uid, email) {
    if (!window.confirm(`Delete ${email}?`)) return
    setDeleting(uid)
    try {
      await api.delete(`/admin/users/${uid}`)
      setUsers(p => p.filter(u => u.user_id !== uid))
    } catch (err) { alert(err.response?.data?.detail || 'Delete failed') }
    finally { setDeleting(null) }
  }

  const clients      = overview?.clients || []
  const totalCalls   = clients.reduce((s, c) => s + c.total_calls,     0)
  const totalProc    = clients.reduce((s, c) => s + c.processed_calls, 0)
  const totalPending = overview?.total_pending ?? 0
  const procPct      = totalCalls ? ((totalProc / totalCalls) * 100).toFixed(1) : '0.0'
  const avgEng       = clients.length ? (clients.reduce((s, c) => s + (c.avg_engagement || 0), 0) / clients.length).toFixed(1) : '—'
  const queueStatus  = totalPending === 0 ? 'healthy' : totalPending < 10 ? 'warning' : 'critical'

  const comparisonData = clients.map(c => ({
    name:       c.name.length > 10 ? c.name.slice(0, 10) + '…' : c.name,
    success:    c.success_rate,
    engagement: c.avg_engagement || 0,
    efficiency: c.total_calls ? Math.round(c.processed_calls / c.total_calls * 100) : 0,
    silence:    c.silence_ratio ? Math.round(c.silence_ratio * 1000) / 10 : 0,
  }))

  const KPIS = [
    { label: 'TOTAL CLIENTS',   value: clients.length,             sub: 'tenants on platform',    color: 'var(--accent2)' },
    { label: 'TOTAL CALLS',     value: totalCalls,                 sub: `${totalProc} processed`, color: 'var(--accent)' },
    { label: 'PROCESSING RATE', value: procPct + '%',              sub: 'calls with insights',    color: '#6ee7b7' },
    { label: 'QUEUE DEPTH',     value: totalPending,               sub: 'pending pipeline',       color: totalPending > 0 ? '#fbbf24' : '#22c55e' },
    { label: 'PLATFORM USERS',  value: overview?.total_users ?? '—', sub: 'across all clients',  color: '#c084fc' },
    { label: 'AVG ENGAGEMENT',  value: avgEng,                     sub: 'platform-wide',         color: 'var(--accent3)' },
  ]

  return (
    <div className="shell">

      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: E }}
      >
        <div className="logo">
          <div className="logo-mark" style={{ color: '#fff' }}><IcoMic /></div>
          <div>
            <div className="logo-text">Heya AI</div>
            <div className="logo-sub">God View · Platform Operations</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="admin-tabs">
            {['overview', 'analytics', 'intelligence', 'feed', 'users', 'alerts'].map(t => (
              <motion.button
                key={t}
                className={`admin-tab ${tab === t ? 'admin-tab-active' : ''}`}
                onClick={() => setTab(t)}
                whileHover={{ opacity: 0.85 }}
                whileTap={{ scale: 0.96 }}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </motion.button>
            ))}
          </div>
          <span className="admin-badge">HEYA_ADMIN</span>
          <motion.button
            className="logout-btn"
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            whileHover={{ borderColor: 'var(--accent2)', color: 'var(--accent2)' }}
            whileTap={{ scale: 0.96 }}
            style={{ minWidth: 36 }}
          >
            {theme === 'dark' ? '☀' : '🌙'}
          </motion.button>
          <motion.button
            className="logout-btn"
            onClick={() => { logout(); navigate('/login') }}
            whileHover={{ borderColor: 'var(--warn)', color: 'var(--warn)' }}
            whileTap={{ scale: 0.96 }}
          >
            Sign out
          </motion.button>
        </div>
      </motion.header>

      {/* ── System status bar ────────────────────────────────────────────────── */}
      <motion.div
        className="sys-bar"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2, duration: 0.4 }}
      >
        {[
          { label: 'API ONLINE',           status: 'online' },
          { label: 'DB CONNECTED',         status: 'online' },
          { label: `QUEUE: ${totalPending} PENDING`, status: queueStatus },
          { label: `${clients.length} CLIENTS ACTIVE`, status: 'online' },
        ].map(s => (
          <div key={s.label} className={`sys-indicator sys-${s.status}`}>
            <span className="sys-dot" />
            {s.label}
          </div>
        ))}
        <div style={{ flex: 1 }} />
        <div className="sys-meta">
          AUTO-REFRESH <span style={{ color: 'var(--accent2)', marginLeft: 4 }}>{countdown}s</span>
        </div>
        {lastSync && (
          <div className="sys-meta">
            LAST SYNC <span style={{ color: 'var(--muted2)', marginLeft: 4 }}>
              {lastSync.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>
        )}
      </motion.div>

      {loading && <div className="loading-bar" />}

      {/* ── Tab Content ──────────────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.28, ease: E }}
        >

          {/* ════════════════════ OVERVIEW ════════════════════ */}
          {tab === 'overview' && (
            <>
              <div className="section-label">PLATFORM METRICS</div>

              {/* KPI Grid */}
              <motion.div
                className="god-kpi-grid"
                variants={kpiStagger}
                initial="hidden"
                animate="show"
              >
                {KPIS.map(k => (
                  <motion.div key={k.label} className="god-kpi" variants={fadeUp} whileHover={{ y: -2, transition: { duration: 0.15 } }}>
                    <div className="god-kpi-label">{k.label}</div>
                    <div className="god-kpi-value" style={{ color: k.color }}>{k.value}</div>
                    <div className="god-kpi-sub">{k.sub}</div>
                  </motion.div>
                ))}
              </motion.div>

              {/* Client Matrix */}
              <div className="section-label" style={{ marginTop: 8 }}>CLIENT MATRIX</div>
              <motion.div
                className="card"
                style={{ padding: 0, overflow: 'clip', marginBottom: 24 }}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.45, ease: E }}
              >
                <div className="table-wrap" style={{ margin: 0 }}>
                  <table className="god-table">
                    <thead>
                      <tr>
                        <th style={{ width: 28 }}></th>
                        <th>CLIENT</th>
                        <th>CALLS</th>
                        <th>PROCESSED</th>
                        <th>QUEUE</th>
                        <th>SUCCESS</th>
                        <th>AVG ENG</th>
                        <th>USERS</th>
                        <th>LAST ACTIVE</th>
                      </tr>
                    </thead>
                    <motion.tbody variants={rowStagger} initial="hidden" animate="show">
                      {clients.length === 0 ? (
                        <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: 'var(--muted)', fontFamily: "'DM Mono'", fontSize: 12 }}>
                          {loading ? 'Loading…' : 'No clients found'}
                        </td></tr>
                      ) : clients.map(c => {
                        const health = clientHealth(c)
                        const effPct = c.total_calls ? Math.round(c.processed_calls / c.total_calls * 100) : 0
                        return (
                          <motion.tr
                            key={c.client_id}
                            variants={fadeUp}
                            className={`god-row ${selected?.client_id === c.client_id ? 'god-row-active' : ''}`}
                            onClick={() => drillInto(c)}
                            whileHover={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
                          >
                            <td><span className="health-dot" style={{ background: healthColor[health], boxShadow: `0 0 6px ${healthColor[health]}80` }} /></td>
                            <td>
                              <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: '-0.01em' }}>{c.name}</div>
                              <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>{c.client_id}</div>
                            </td>
                            <td style={{ fontFamily: "'DM Mono'", fontSize: 14, fontWeight: 700 }}>{c.total_calls}</td>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div style={{ width: 52, height: 4, background: 'var(--track-bg)', borderRadius: 2, overflow: 'hidden' }}>
                                  <div style={{ width: `${effPct}%`, height: '100%', background: effPct === 100 ? '#22c55e' : '#818cf8', borderRadius: 2 }} />
                                </div>
                                <span style={{ fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted2)' }}>{c.processed_calls}/{c.total_calls}</span>
                              </div>
                            </td>
                            <td>
                              <span style={{
                                fontFamily: "'DM Mono'", fontSize: 13, fontWeight: 700,
                                color: c.pending_queue > 5 ? '#ef4444' : c.pending_queue > 0 ? '#fbbf24' : '#22c55e',
                              }}>{c.pending_queue}</span>
                            </td>
                            <td>
                              <span style={{
                                fontFamily: "'DM Mono'", fontSize: 13, fontWeight: 700,
                                color: c.success_rate >= 70 ? '#22c55e' : c.success_rate >= 50 ? '#fbbf24' : '#ef4444',
                              }}>{c.success_rate}%</span>
                            </td>
                            <td style={{ fontFamily: "'DM Mono'", fontSize: 12, color: 'var(--muted2)' }}>{c.avg_engagement ?? '—'}</td>
                            <td style={{ fontFamily: "'DM Mono'", fontSize: 12, color: 'var(--muted2)' }}>{c.user_count}</td>
                            <td style={{ fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted)' }}>
                              {c.last_call_at
                                ? new Date(c.last_call_at).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' })
                                : 'No calls yet'}
                            </td>
                          </motion.tr>
                        )
                      })}
                    </motion.tbody>
                  </table>
                </div>
              </motion.div>

              {/* Comparison Charts */}
              {comparisonData.length > 0 && (
                <>
                  <div className="section-label">CROSS-CLIENT ANALYTICS</div>
                  <div className="chart-grid">
                    {[
                      {
                        title: 'Success Rate vs Engagement', desc: 'side-by-side per client', tag: 'COMPARISON', tagClass: 'tag-purple',
                        chart: (
                          <BarChart data={comparisonData} margin={{ top: 5, right: 16, left: -10, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                            <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} domain={[0, 100]} />
                            <Tooltip {...TT} formatter={(v, n) => [`${v.toFixed(1)}${n === 'success' ? '%' : '/100'}`, n === 'success' ? 'Success Rate' : 'Avg Engagement']} />
                            <Legend iconSize={8} formatter={v => <span style={{ color: '#94a3b8', fontSize: 10 }}>{v === 'success' ? 'SUCCESS %' : 'ENGAGEMENT'}</span>} />
                            <Bar dataKey="success"    fill="#6ee7b7" radius={[3,3,0,0]} maxBarSize={40} />
                            <Bar dataKey="engagement" fill="#818cf8" radius={[3,3,0,0]} maxBarSize={40} />
                          </BarChart>
                        ),
                      },
                      {
                        title: 'Processing Efficiency', desc: '% of calls with full audio insights processed', tag: 'PIPELINE', tagClass: 'tag-green',
                        chart: (
                          <BarChart data={comparisonData} margin={{ top: 5, right: 16, left: -10, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                            <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} domain={[0, 100]} unit="%" />
                            <Tooltip {...TT} formatter={v => [`${v}%`, 'Processed']} />
                            <Bar dataKey="efficiency" radius={[3,3,0,0]} maxBarSize={60}>
                              {comparisonData.map((d, i) => (
                                <Cell key={i} fill={d.efficiency === 100 ? '#22c55e' : d.efficiency >= 70 ? '#818cf8' : '#fbbf24'} />
                              ))}
                            </Bar>
                          </BarChart>
                        ),
                      },
                      {
                        title: 'Silence Ratio Comparison', desc: 'avg silence per client — >15% is elevated, >40% hurts success rate', tag: 'SILENCE', tagClass: 'tag-purple',
                        chart: (
                          <BarChart data={comparisonData} margin={{ top: 5, right: 16, left: -10, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                            <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} unit="%" domain={[0, 60]} />
                            <Tooltip {...TT} formatter={v => [`${v}%`, 'Silence Ratio']} />
                            <ReferenceLine y={15} stroke="#fbbf24" strokeDasharray="4 3" label={{ value: 'Warning 15%', fill: '#fbbf24', fontSize: 9 }} />
                            <Bar dataKey="silence" radius={[3,3,0,0]} maxBarSize={60}>
                              {comparisonData.map((d, i) => (
                                <Cell key={i} fill={d.silence > 40 ? '#ef4444' : d.silence > 15 ? '#fbbf24' : '#22c55e'} />
                              ))}
                            </Bar>
                          </BarChart>
                        ),
                      },
                      {
                        title: 'Engagement vs Industry Baseline', desc: 'client avg engagement score vs 62.0 Voice AI baseline', tag: 'BENCHMARK', tagClass: 'tag-green',
                        chart: (
                          <BarChart data={comparisonData} margin={{ top: 5, right: 16, left: -10, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                            <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} domain={[0, 100]} />
                            <Tooltip {...TT} formatter={v => [`${v.toFixed(1)}/100`, 'Engagement']} />
                            <ReferenceLine y={62} stroke="#818cf8" strokeDasharray="4 3" label={{ value: 'Baseline 62.0', fill: '#818cf8', fontSize: 9 }} />
                            <Bar dataKey="engagement" radius={[3,3,0,0]} maxBarSize={60}>
                              {comparisonData.map((d, i) => (
                                <Cell key={i} fill={d.engagement >= 62 ? '#22c55e' : d.engagement >= 45 ? '#fbbf24' : '#ef4444'} />
                              ))}
                            </Bar>
                          </BarChart>
                        ),
                      },
                    ].map((c, i) => (
                      <motion.div
                        key={c.title}
                        className="card"
                        initial={{ opacity: 0, y: 16 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.45 + i * 0.1, duration: 0.45, ease: E }}
                      >
                        <div className="card-header">
                          <div>
                            <div className="card-title">{c.title}</div>
                            <div className="card-desc">{c.desc}</div>
                          </div>
                          <span className={`tag ${c.tagClass}`}>{c.tag}</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={200}>{c.chart}</ResponsiveContainer>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </>
              )}

              {/* Cross-client correlation callout — dynamically generated from real stats */}
              {clients.length >= 2 && (() => {
                const sorted = [...clients].sort((a, b) => (b.silence_ratio || 0) - (a.silence_ratio || 0))
                const hi = sorted[0]
                const lo = sorted[sorted.length - 1]
                if (!hi?.silence_ratio || !lo?.silence_ratio || hi.client_id === lo.client_id) return null
                const diff = ((hi.silence_ratio - lo.silence_ratio) * 100).toFixed(1)
                if (parseFloat(diff) < 2) return null
                return (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5, duration: 0.38 }}
                    style={{
                      margin: '0 0 20px 0', padding: '14px 18px',
                      background: 'rgba(129, 140, 248, 0.05)',
                      border: '1px solid rgba(129, 140, 248, 0.2)',
                      borderRadius: 10, display: 'flex', alignItems: 'flex-start', gap: 12,
                    }}>
                    <span style={{ fontSize: 16, marginTop: 1 }}>💡</span>
                    <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.7 }}>
                      <strong style={{ color: 'var(--accent2)' }}>Insight:</strong>{' '}
                      <strong style={{ color: 'var(--text)' }}>{hi.name}</strong> has {diff}% higher silence ratio than{' '}
                      <strong style={{ color: 'var(--text)' }}>{lo.name}</strong>.
                      Calls with silence &gt; 40% show lower success rates — consider reviewing{' '}
                      {hi.name}&apos;s agent pacing and response timing.
                    </div>
                  </motion.div>
                )
              })()}

              {/* Drill-down Panel */}
              <AnimatePresence>
                {selected && (
                  <motion.div
                    className="god-drill"
                    initial={{ opacity: 0, y: 20, scaleY: 0.95 }}
                    animate={{ opacity: 1, y: 0, scaleY: 1 }}
                    exit={{ opacity: 0, y: -12, scaleY: 0.97 }}
                    transition={{ duration: 0.38, ease: E }}
                    style={{ transformOrigin: 'top' }}
                  >
                    <div className="section-label" style={{ marginBottom: 16 }}>
                      DRILL-DOWN: <span style={{ color: 'var(--accent2)' }}>{selected.name}</span>
                      <span style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', marginLeft: 8 }}>{selected.client_id}</span>
                      <button className="clear-btn" onClick={() => { setSelected(null); setClientStats(null); setClientInsights([]); setClientRecs([]) }}>✕ close</button>
                    </div>

                    {drillLoad && <div className="loading-bar" />}

                    {clientStats && (
                      <motion.div
                        className="god-kpi-grid"
                        style={{ marginBottom: 20 }}
                        variants={kpiStagger} initial="hidden" animate="show"
                      >
                        {[
                          { label: 'TOTAL CALLS',  value: clientStats.total_calls,          sub: `${clientStats.audio_processed} with insights`, color: 'var(--accent)' },
                          { label: 'SUCCESS RATE', value: clientStats.success_rate + '%',   sub: 'calls resolved', color: clientStats.success_rate >= 70 ? '#22c55e' : '#fbbf24' },
                          { label: 'AVG DURATION', value: clientStats.avg_duration_sec + 's', sub: 'per call',   color: 'var(--accent2)' },
                          { label: 'PENDING',      value: clientStats.pending_audio,        sub: 'awaiting pipeline', color: clientStats.pending_audio > 0 ? '#fbbf24' : '#22c55e' },
                        ].map(k => (
                          <motion.div key={k.label} className="god-kpi" variants={fadeUp}>
                            <div className="god-kpi-label">{k.label}</div>
                            <div className="god-kpi-value" style={{ color: k.color }}>{k.value}</div>
                            <div className="god-kpi-sub">{k.sub}</div>
                          </motion.div>
                        ))}
                      </motion.div>
                    )}

                    {clientInsights.length > 0 && (() => {
                      const ci = clientInsights
                      const trajC = { improving: 0, stable: 0, deteriorating: 0 }
                      ci.forEach(r => { if (r.sentiment_trajectory) trajC[r.sentiment_trajectory] = (trajC[r.sentiment_trajectory] || 0) + 1 })
                      const trajTotal = (trajC.improving + trajC.stable + trajC.deteriorating) || 1
                      const agentPitches = ci.map(r => parseFloat(r.agent_avg_pitch_hz)).filter(v => v > 0)
                      const agentPitchMean = agentPitches.length ? agentPitches.reduce((s, v) => s + v, 0) / agentPitches.length : 0
                      const agentPitchStd  = agentPitches.length > 1 ? Math.sqrt(agentPitches.reduce((s, v) => s + Math.pow(v - agentPitchMean, 2), 0) / agentPitches.length) : 0
                      const consistencyScore = agentPitchMean > 0 ? Math.max(0, Math.round(100 - (agentPitchStd / agentPitchMean * 100))) : null
                      const avgCustP = meanOf(ci, 'customer_avg_pitch_hz')
                      const stressCount = ci.filter(r => parseFloat(r.customer_avg_pitch_hz) > avgCustP * 1.2).length

                      const SEVEN = [
                        { label: 'ENGAGEMENT',        value: meanOf(ci, 'engagement_score').toFixed(1) + '/100', color: 'var(--accent2)' },
                        { label: 'DOMINANT EMOTION',  value: modeOf(ci, 'dominant_emotion'),                    color: EMOTION_COLORS[modeOf(ci, 'dominant_emotion')] || 'var(--muted2)' },
                        { label: 'TRAJECTORY',        value: `${((trajC.improving / trajTotal) * 100).toFixed(0)}% improving`, color: '#22c55e' },
                        { label: 'SILENCE RATIO',     value: (meanOf(ci, 'silence_ratio') * 100).toFixed(1) + '%',             color: 'var(--accent3)' },
                        { label: 'AVG INTERRUPTS',    value: meanOf(ci, 'interruption_count').toFixed(1),                      color: 'var(--warn)' },
                        { label: 'AVG HESITATIONS',   value: meanOf(ci, 'hesitation_count').toFixed(1),                        color: meanOf(ci, 'hesitation_count') > 5 ? 'var(--warn)' : 'var(--accent)' },
                        { label: 'AGENT CONSISTENCY', value: consistencyScore != null ? consistencyScore + '/100' : '—',       color: consistencyScore != null && consistencyScore >= 80 ? '#22c55e' : consistencyScore != null && consistencyScore >= 60 ? '#fbbf24' : '#ef4444' },
                      ]
                      return (
                        <>
                          <div className="section-label" style={{ marginBottom: 10, marginTop: 4, fontSize: 10 }}>7 ANALYTICS METRICS</div>
                          <motion.div
                            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginBottom: 20 }}
                            variants={kpiStagger} initial="hidden" animate="show"
                          >
                            {SEVEN.map(k => (
                              <motion.div key={k.label} variants={fadeUp}
                                style={{ background: 'var(--surface)', border: '1px solid var(--border2)', borderRadius: 8, padding: '10px 12px' }}>
                                <div style={{ fontFamily: "'DM Mono'", fontSize: 9, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 6 }}>{k.label}</div>
                                <div style={{ fontFamily: "'DM Mono'", fontSize: 13, fontWeight: 700, color: k.color }}>{k.value}</div>
                              </motion.div>
                            ))}
                          </motion.div>

                          <motion.div
                            className="card"
                            style={{ padding: 0, overflow: 'clip' }}
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2, duration: 0.4, ease: E }}
                          >
                            <div className="table-wrap" style={{ margin: 0 }}>
                              <table className="god-table">
                                <thead>
                                  <tr>
                                    <th>CALL ID</th><th>DATE</th><th>QUALITY</th><th>FLOW</th>
                                    <th>ENGAGEMENT</th><th>SILENCE</th><th>INTERRUPTS</th>
                                    <th>TRAJECTORY</th><th>EMOTION</th><th>OUTCOME</th>
                                  </tr>
                                </thead>
                            <motion.tbody variants={rowStagger} initial="hidden" animate="show">
                              {clientInsights.slice(0, 50).map(r => (
                                <motion.tr key={r.call_id} className="god-row" variants={fadeUp} onClick={() => setCallRow(r)}>
                                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{r.call_id}</td>
                                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11, whiteSpace: 'nowrap', color: 'var(--muted2)' }}>
                                    {r.start_timestamp ? new Date(r.start_timestamp).toLocaleDateString('en-AU', { day:'2-digit', month:'short', year:'numeric' }) : '—'}
                                  </td>
                                  <td><QualityBadge score={r.quality_score} grade={r.quality_grade} /></td>
                                  <td><span className={`flow-chip chip-${r.conversation_flow}`}>{r.conversation_flow || '—'}</span></td>
                                  <td style={{ fontFamily: "'DM Mono'", fontSize: 12 }}>{parseFloat(r.engagement_score || 0).toFixed(2)}</td>
                                  <td style={{ fontFamily: "'DM Mono'", fontSize: 12, color: 'var(--muted2)' }}>{(parseFloat(r.silence_ratio || 0) * 100).toFixed(1)}%</td>
                                  <td style={{ fontFamily: "'DM Mono'", fontSize: 12, color: 'var(--muted2)' }}>{r.interruption_count ?? '—'}</td>
                                  <td>
                                    {r.sentiment_trajectory
                                      ? <span className={`traj traj-${r.sentiment_trajectory}`} style={{ fontSize: 11 }}>
                                          {r.sentiment_trajectory === 'improving' ? '↑' : r.sentiment_trajectory === 'deteriorating' ? '↓' : '→'} {r.sentiment_trajectory}
                                        </span>
                                      : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                                  </td>
                                  <td>
                                    {r.dominant_emotion && EMOTION_COLORS[r.dominant_emotion]
                                      ? <span style={{ fontFamily: "'DM Mono'", fontSize: 11, color: EMOTION_COLORS[r.dominant_emotion] }}>{r.dominant_emotion}</span>
                                      : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                                  </td>
                                  <td>
                                    {r.call_successful === true  && <span className="tag tag-success" style={{ fontSize: 10 }}>OK</span>}
                                    {r.call_successful === false && <span className="tag tag-fail"    style={{ fontSize: 10 }}>FAIL</span>}
                                    {r.call_successful == null   && <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                                  </td>
                                </motion.tr>
                              ))}
                            </motion.tbody>
                          </table>
                        </div>
                      </motion.div>
                        </>
                      )
                    })()}

                    {/* Recommendations */}
                    {clientRecs.length > 0 && (
                      <motion.div initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.3, duration:0.35 }}>
                        <div className="section-label" style={{ marginTop:24, marginBottom:12, fontSize:10 }}>
                          PORTFOLIO RECOMMENDATIONS
                          {clientRecs.filter(r => r.priority === 'critical').length > 0 && (
                            <span className="rec-critical-badge" style={{ marginLeft:8 }}>
                              {clientRecs.filter(r => r.priority === 'critical').length} critical
                            </span>
                          )}
                        </div>
                        <div className="rec-list">
                          {clientRecs.map(rec => {
                            const PMETA = { critical:{color:'#ef4444',border:'#ef444430',bg:'#ef444408',label:'CRITICAL'}, warning:{color:'#fb923c',border:'#fb923c30',bg:'#fb923c08',label:'WARNING'}, info:{color:'#fbbf24',border:'#fbbf2430',bg:'#fbbf2408',label:'INFO'} }
                            const meta = PMETA[rec.priority] || PMETA.info
                            const isOpen = recsExpanded === rec.id
                            return (
                              <div key={rec.id} className="rec-card" style={{ borderColor: meta.border, background: meta.bg }}>
                                <div className="rec-header">
                                  <div className="rec-header-left">
                                    <span className="rec-priority-tag" style={{ color: meta.color, borderColor: meta.border }}>{meta.label}</span>
                                    <span className="rec-title">{rec.title}</span>
                                  </div>
                                  <div className="rec-header-right">
                                    {rec.affected_calls > 0 && <span className="rec-count" style={{ color: meta.color }}>{rec.affected_calls} calls</span>}
                                    <span className="rec-trend" style={{ color: rec.trend === 'worsening' ? '#ef4444' : rec.trend === 'improving' ? '#22c55e' : 'var(--muted)' }}>
                                      {rec.trend === 'worsening' ? '↓' : rec.trend === 'improving' ? '↑' : '→'} {rec.trend}
                                    </span>
                                  </div>
                                </div>
                                <p className="rec-insight">{rec.insight}</p>
                                <div className="rec-metric" style={{ borderColor: meta.border, color: meta.color }}>{rec.metric}</div>
                                <button className="rec-action-toggle" style={{ color: meta.color }} onClick={() => setRecsExpanded(isOpen ? null : rec.id)}>
                                  {isOpen ? '▲ Hide action' : '▼ Recommended action'}
                                </button>
                                <AnimatePresence>
                                  {isOpen && (
                                    <motion.div className="rec-action" style={{ borderColor: meta.border, overflow:'hidden' }}
                                      initial={{ height:0, opacity:0 }} animate={{ height:'auto', opacity:1 }} exit={{ height:0, opacity:0 }}
                                      transition={{ duration:0.22, ease:'easeOut' }}>
                                      {rec.action}
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                              </div>
                            )
                          })}
                        </div>
                      </motion.div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          )}

          {/* ════════════════════ ANALYTICS ════════════════════ */}
          {tab === 'analytics' && (
            <>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20 }}>
                <div className="section-label" style={{ marginBottom:0 }}>AUDIO ANALYTICS DASHBOARD</div>
                <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                  <select
                    value={analyticsClientId}
                    onChange={e => { setAnalyticsClientId(e.target.value); setAnalyticsStats(null); setAnalyticsInsights([]) }}
                    style={{ fontFamily:"'DM Mono'", fontSize:12, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 12px', cursor:'pointer' }}>
                    {clients.map(c => <option key={c.client_id} value={c.client_id}>{c.name}</option>)}
                  </select>
                  <motion.button
                    onClick={() => setAnalyticsRefresh(r => r + 1)}
                    style={{ fontFamily:"'DM Mono'", fontSize:11, padding:'6px 14px', borderRadius:6, border:'1px solid var(--border2)', background:'transparent', color:'var(--muted2)', cursor:'pointer', letterSpacing:'0.04em' }}
                    whileHover={{ borderColor:'var(--accent2)', color:'var(--accent2)' }}
                    whileTap={{ scale:0.96 }}>
                    ↺ Refresh
                  </motion.button>
                </div>
              </div>

              {analyticsLoad && <div className="loading-bar" />}

              {analyticsStats && analyticsInsights.length > 0 && (() => {
                const ai = analyticsInsights
                const trajC = { improving: 0, stable: 0, deteriorating: 0 }
                ai.forEach(r => { if (r.sentiment_trajectory) trajC[r.sentiment_trajectory] = (trajC[r.sentiment_trajectory] || 0) + 1 })
                const trajTotal = (trajC.improving + trajC.stable + trajC.deteriorating) || 1
                const agentPitches = ai.map(r => parseFloat(r.agent_avg_pitch_hz)).filter(v => v > 0)
                const agentPitchMean = agentPitches.length ? agentPitches.reduce((s, v) => s + v, 0) / agentPitches.length : 0
                const agentPitchStd  = agentPitches.length > 1 ? Math.sqrt(agentPitches.reduce((s, v) => s + Math.pow(v - agentPitchMean, 2), 0) / agentPitches.length) : 0
                const consistencyScore = agentPitchMean > 0 ? Math.max(0, Math.round(100 - (agentPitchStd / agentPitchMean * 100))) : null
                const avgCustP = meanOf(ai, 'customer_avg_pitch_hz')

                const emotionDist = Object.entries(
                  ai.reduce((acc, r) => { if (r.dominant_emotion) acc[r.dominant_emotion] = (acc[r.dominant_emotion]||0)+1; return acc }, {})
                ).map(([emotion, count]) => ({ emotion, count })).sort((a, b) => b.count - a.count)

                const engBuckets = [
                  { range: '0–25',  count: ai.filter(r => (parseFloat(r.engagement_score)||0) < 25).length, fill: '#ef4444' },
                  { range: '25–50', count: ai.filter(r => { const v=parseFloat(r.engagement_score)||0; return v>=25&&v<50 }).length, fill: '#fbbf24' },
                  { range: '50–75', count: ai.filter(r => { const v=parseFloat(r.engagement_score)||0; return v>=50&&v<75 }).length, fill: '#818cf8' },
                  { range: '75+',   count: ai.filter(r => (parseFloat(r.engagement_score)||0) >= 75).length, fill: '#22c55e' },
                ]
                const trajChartData = [
                  { name: 'Improving',     count: trajC.improving,     fill: '#22c55e' },
                  { name: 'Stable',        count: trajC.stable,        fill: '#818cf8' },
                  { name: 'Deteriorating', count: trajC.deteriorating, fill: '#ef4444' },
                ]
                const silBuckets = [
                  { range: '<10%',   count: ai.filter(r => (parseFloat(r.silence_ratio)||0) < 0.10).length, fill: '#22c55e' },
                  { range: '10–25%', count: ai.filter(r => { const v=parseFloat(r.silence_ratio)||0; return v>=0.10&&v<0.25 }).length, fill: '#6ee7b7' },
                  { range: '25–40%', count: ai.filter(r => { const v=parseFloat(r.silence_ratio)||0; return v>=0.25&&v<0.40 }).length, fill: '#fbbf24' },
                  { range: '40–65%', count: ai.filter(r => { const v=parseFloat(r.silence_ratio)||0; return v>=0.40&&v<0.65 }).length, fill: '#fb923c' },
                  { range: '>65%',   count: ai.filter(r => (parseFloat(r.silence_ratio)||0) >= 0.65).length, fill: '#ef4444' },
                ]
                const intBuckets = [
                  { range: '0',   count: ai.filter(r => (r.interruption_count||0) === 0).length, fill: '#22c55e' },
                  { range: '1–3', count: ai.filter(r => { const v=r.interruption_count||0; return v>=1&&v<=3 }).length, fill: '#818cf8' },
                  { range: '4–7', count: ai.filter(r => { const v=r.interruption_count||0; return v>=4&&v<=7 }).length, fill: '#fbbf24' },
                  { range: '8+',  count: ai.filter(r => (r.interruption_count||0) >= 8).length, fill: '#ef4444' },
                ]
                const hesBuckets = [
                  { range: '0–2',  count: ai.filter(r => (r.hesitation_count||0) <= 2).length, fill: '#22c55e' },
                  { range: '3–5',  count: ai.filter(r => { const v=r.hesitation_count||0; return v>=3&&v<=5 }).length, fill: '#818cf8' },
                  { range: '6–10', count: ai.filter(r => { const v=r.hesitation_count||0; return v>=6&&v<=10 }).length, fill: '#fbbf24' },
                  { range: '11+',  count: ai.filter(r => (r.hesitation_count||0) > 10).length, fill: '#ef4444' },
                ]
                const acStressData = [
                  { label: 'Normal',      count: ai.filter(r => { const p=parseFloat(r.customer_avg_pitch_hz)||0; return p>0&&p<=avgCustP*1.2 }).length, fill: '#22c55e' },
                  { label: 'Elevated',    count: ai.filter(r => { const p=parseFloat(r.customer_avg_pitch_hz)||0; return p>avgCustP*1.2&&p<=avgCustP*1.5 }).length, fill: '#fbbf24' },
                  { label: 'High Stress', count: ai.filter(r => (parseFloat(r.customer_avg_pitch_hz)||0) > avgCustP*1.5).length, fill: '#ef4444' },
                ]
                const agentVarData = agentPitchMean > 0 ? [
                  { label: 'Consistent', count: ai.filter(r => { const p=parseFloat(r.agent_avg_pitch_hz)||0; return p>0&&Math.abs(p-agentPitchMean)/agentPitchMean<0.10 }).length, fill: '#22c55e' },
                  { label: 'Moderate',   count: ai.filter(r => { const p=parseFloat(r.agent_avg_pitch_hz)||0; const d=Math.abs(p-agentPitchMean)/agentPitchMean; return p>0&&d>=0.10&&d<0.20 }).length, fill: '#fbbf24' },
                  { label: 'High Var.',  count: ai.filter(r => { const p=parseFloat(r.agent_avg_pitch_hz)||0; return p>0&&Math.abs(p-agentPitchMean)/agentPitchMean>=0.20 }).length, fill: '#ef4444' },
                ] : []

                const radarData = [
                  { metric: 'Engagement',   value: parseFloat(meanOf(ai, 'engagement_score').toFixed(1)) },
                  { metric: 'Trajectory',   value: parseFloat(((trajC.improving / trajTotal) * 100).toFixed(1)) },
                  { metric: 'Low Silence',  value: parseFloat(Math.max(0, 100 - meanOf(ai, 'silence_ratio') * 200).toFixed(1)) },
                  { metric: 'Low Friction', value: parseFloat(Math.max(0, 100 - meanOf(ai, 'interruption_count') * 12).toFixed(1)) },
                  { metric: 'Consistency',  value: consistencyScore || 0 },
                ]

                return (
                  <>
                    {/* Snapshot KPIs */}
                    <motion.div
                      className="god-kpi-grid"
                      style={{ marginBottom: 28 }}
                      variants={kpiStagger} initial="hidden" animate="show"
                    >
                      {[
                        { label: 'CALLS ANALYSED',    value: ai.length,                                                       sub: 'with audio insights',   color: 'var(--accent)' },
                        { label: 'AVG ENGAGEMENT',    value: meanOf(ai, 'engagement_score').toFixed(1) + '/100',              sub: 'composite vocal score',  color: 'var(--accent2)' },
                        { label: 'IMPROVING TRAJ',    value: `${((trajC.improving / trajTotal) * 100).toFixed(0)}%`,          sub: 'calls with +ve energy',  color: '#22c55e' },
                        { label: 'AGENT CONSISTENCY', value: consistencyScore != null ? consistencyScore + '/100' : '—',      sub: 'pitch variance score',   color: consistencyScore != null && consistencyScore >= 80 ? '#22c55e' : '#fbbf24' },
                      ].map(k => (
                        <motion.div key={k.label} className="god-kpi" variants={fadeUp}>
                          <div className="god-kpi-label">{k.label}</div>
                          <div className="god-kpi-value" style={{ color: k.color }}>{k.value}</div>
                          <div className="god-kpi-sub">{k.sub}</div>
                        </motion.div>
                      ))}
                    </motion.div>

                    {/* ── Section 1: Emotion & Engagement ── */}
                    <div className="section-label" style={{ marginBottom: 8 }}>EMOTION &amp; ENGAGEMENT</div>
                    <div style={{ marginBottom: 16, fontSize: 12, color: 'var(--muted2)', fontFamily: 'Inter, sans-serif', lineHeight: 1.6 }}>
                      Emotion detection is derived from vocal pitch and energy — not NLP text analysis. Engagement is a composite of speaking rate, response latency, and vocal energy (0–100 scale, industry baseline 62.0).
                    </div>
                    <div className="chart-grid" style={{ marginBottom: 32 }}>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.05, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Emotion Detection</div><div className="card-desc">dominant emotion per call — vocal pitch &amp; energy signal</div></div>
                          <span className="tag tag-purple">PER-CALL</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={270}>
                            <PieChart>
                              <Pie data={emotionDist} dataKey="count" nameKey="emotion" cx="50%" cy="42%" innerRadius={50} outerRadius={85} paddingAngle={3}>
                                {emotionDist.map((d, i) => <Cell key={i} fill={EMOTION_COLORS[d.emotion] || '#818cf8'} />)}
                              </Pie>
                              <Tooltip {...TT} formatter={(v, n) => [v + ' calls', n]} />
                              <Legend iconSize={8} iconType="circle" formatter={v => <span style={{ color:'#94a3b8', fontSize:10 }}>{v}</span>} />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.10, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Engagement Scoring</div><div className="card-desc">score distribution — 75+ high, 50–75 mid, below 50 low</div></div>
                          <span className="tag tag-green">DISTRIBUTION</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={engBuckets} margin={{ top:8, right:12, left:-10, bottom:5 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                              <XAxis dataKey="range" tick={{ fill:'#64748b', fontSize:11 }} />
                              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
                              <Tooltip {...TT} formatter={v => [v, 'Calls']} />
                              <Bar dataKey="count" radius={[4,4,0,0]} maxBarSize={60}>
                                {engBuckets.map((d, i) => <Cell key={i} fill={d.fill} />)}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                    </div>

                    {/* ── Section 2: Sentiment & Silence ── */}
                    <div className="section-label" style={{ marginBottom: 8 }}>SENTIMENT &amp; SILENCE</div>
                    <div style={{ marginBottom: 16, fontSize: 12, color: 'var(--muted2)', fontFamily: 'Inter, sans-serif', lineHeight: 1.6 }}>
                      Sentiment trajectory tracks the caller's emotional arc from call open to close. Silence ratio flags disengagement — calls above 40% dead air show measurably lower resolution rates.
                    </div>
                    <div className="chart-grid" style={{ marginBottom: 32 }}>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.05, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Sentiment Trajectory</div><div className="card-desc">how caller emotional state evolves from open to close</div></div>
                          <span className="tag tag-green">TRAJECTORY</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={270}>
                            <PieChart>
                              <Pie data={trajChartData} dataKey="count" nameKey="name" cx="50%" cy="42%" innerRadius={50} outerRadius={85} paddingAngle={4}>
                                {trajChartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                              </Pie>
                              <Tooltip {...TT} formatter={(v, n) => [v + ' calls', n]} />
                              <Legend iconSize={8} iconType="circle" formatter={v => <span style={{ color:'#94a3b8', fontSize:10 }}>{v}</span>} />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.10, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Silence Analysis</div><div className="card-desc">extended pauses indicating confusion, disengagement or friction</div></div>
                          <span className="tag tag-purple">SILENCE</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={240}>
                            <AreaChart data={silBuckets} margin={{ top:8, right:12, left:-10, bottom:5 }}>
                              <defs>
                                <linearGradient id="silGrad" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.3} />
                                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                              <XAxis dataKey="range" tick={{ fill:'#64748b', fontSize:11 }} />
                              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
                              <Tooltip {...TT} formatter={v => [v, 'Calls']} />
                              <Area type="monotone" dataKey="count" stroke="#818cf8" fill="url(#silGrad)" strokeWidth={2.5} dot={{ fill:'#818cf8', r:4, strokeWidth:0 }} activeDot={{ r:6 }} />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                    </div>

                    {/* ── Section 3: Friction & Hesitation ── */}
                    <div className="section-label" style={{ marginBottom: 8 }}>FRICTION &amp; HESITATION</div>
                    <div style={{ marginBottom: 16, fontSize: 12, color: 'var(--muted2)', fontFamily: 'Inter, sans-serif', lineHeight: 1.6 }}>
                      Interruptions signal urgency, frustration, or overlapping conversation flow. Hesitation markers indicate caller uncertainty or agent pacing problems.
                    </div>
                    <div className="chart-grid" style={{ marginBottom: 32 }}>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.05, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Interruption Analysis</div><div className="card-desc">overlapping speech events per call — urgency &amp; poor flow signal</div></div>
                          <span className="tag tag-fail">FRICTION</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={intBuckets} margin={{ top:8, right:12, left:-10, bottom:5 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                              <XAxis dataKey="range" tick={{ fill:'#64748b', fontSize:11 }} />
                              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
                              <Tooltip {...TT} formatter={v => [v, 'Calls']} />
                              <Bar dataKey="count" radius={[4,4,0,0]} maxBarSize={60}>
                                {intBuckets.map((d, i) => <Cell key={i} fill={d.fill} />)}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.10, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Speaking Rate &amp; Hesitation</div><div className="card-desc">hesitation markers signalling uncertainty or discomfort</div></div>
                          <span className="tag tag-purple">HESITATION</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={240}>
                            <LineChart data={hesBuckets} margin={{ top:8, right:12, left:-10, bottom:5 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                              <XAxis dataKey="range" tick={{ fill:'#64748b', fontSize:11 }} />
                              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
                              <Tooltip {...TT} formatter={v => [v, 'Calls']} />
                              <Line type="monotone" dataKey="count" stroke="#c084fc" strokeWidth={2.5} dot={{ fill:'#c084fc', r:5, strokeWidth:2, stroke:'#0d0d14' }} activeDot={{ r:7, fill:'#c084fc' }} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                    </div>

                    {/* ── Section 4: Acoustic Signals ── */}
                    <div className="section-label" style={{ marginBottom: 8 }}>ACOUSTIC SIGNALS</div>
                    <div style={{ marginBottom: 16, fontSize: 12, color: 'var(--muted2)', fontFamily: 'Inter, sans-serif', lineHeight: 1.6 }}>
                      Customer pitch elevation above the per-client baseline flags acoustic stress. Agent consistency tracks pitch deviation across calls — high variance indicates inconsistent delivery tone.
                    </div>
                    <div className="chart-grid" style={{ marginBottom: 32 }}>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.05, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Acoustic Stress Indicators</div><div className="card-desc">customer pitch elevation above per-client baseline</div></div>
                          <span className="tag tag-fail">STRESS</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={270}>
                            <PieChart>
                              <Pie data={acStressData} dataKey="count" nameKey="label" cx="50%" cy="42%" innerRadius={50} outerRadius={85} paddingAngle={4}>
                                {acStressData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                              </Pie>
                              <Tooltip {...TT} formatter={(v, n) => [v + ' calls', n]} />
                              <Legend iconSize={8} iconType="circle" formatter={v => <span style={{ color:'#94a3b8', fontSize:10 }}>{v}</span>} />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.10, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Client Quality Radar</div><div className="card-desc">engagement · trajectory · silence · friction · agent consistency (0–100)</div></div>
                          <span className="tag tag-green">RADAR</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={240}>
                            <RadarChart cx="50%" cy="50%" outerRadius={85} data={radarData}>
                              <PolarGrid stroke="#ffffff12" />
                              <PolarAngleAxis dataKey="metric" tick={{ fill:'#64748b', fontSize:10 }} />
                              <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill:'#475569', fontSize:9 }} tickCount={4} />
                              <Radar dataKey="value" stroke="#818cf8" fill="#818cf8" fillOpacity={0.18} strokeWidth={2} dot={{ fill:'#818cf8', r:3, strokeWidth:0 }} />
                              <Tooltip {...TT} formatter={v => [v.toFixed(1) + '/100', 'Score']} />
                            </RadarChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                    </div>
                  </>
                )
              })()}

              {!analyticsLoad && analyticsStats && analyticsInsights.length === 0 && (
                <div style={{ padding:'60px 0', textAlign:'center', color:'var(--muted)', fontFamily:"'DM Mono'", fontSize:12 }}>
                  No audio insights processed yet for this client
                </div>
              )}

              {!analyticsLoad && !analyticsStats && analyticsClientId && (
                <div style={{ padding:'60px 0', textAlign:'center', color:'var(--muted)', fontFamily:"'DM Mono'", fontSize:12 }}>
                  Loading data…
                </div>
              )}
            </>
          )}

          {/* ════════════════════ INTELLIGENCE ════════════════════ */}
          {tab === 'intelligence' && (() => {
            const ROUTE_COLORS = {
              text_to_sql:'#22c55e', sql_direct:'#22c55e', sql_aggregation:'#22c55e',
              semantic:'#818cf8', semantic_search:'#818cf8',
              rag:'#6ee7b7', llm_stats:'#6ee7b7',
              'llm_stats+semantic':'#818cf8',
              'followup+llm_stats':'#6ee7b7',
              'followup+llm_stats+semantic':'#818cf8',
              admin_platform:'#c084fc',
              'admin_platform+semantic':'#c084fc',
              'followup+admin_platform':'#c084fc',
              'followup+admin_platform+semantic':'#c084fc',
              agent_react:'#c084fc',
              error:'#ef4444', Error:'#ef4444',
              unknown:'#64748b',
            }
            const routeLabel = {
              text_to_sql:'Text→SQL', sql_direct:'SQL Direct', sql_aggregation:'SQL Agg',
              semantic:'Semantic', semantic_search:'Semantic',
              rag:'RAG', llm_stats:'LLM Stats',
              'llm_stats+semantic':'LLM+Semantic',
              'followup+llm_stats':'RAG Follow-up',
              'followup+llm_stats+semantic':'RAG+Semantic',
              admin_platform:'Platform RAG',
              'admin_platform+semantic':'Platform+Semantic',
              'followup+admin_platform':'Platform Follow-up',
              'followup+admin_platform+semantic':'Platform+Semantic',
              agent_react:'ReAct Agent',
              error:'Error', Error:'Error',
              unknown:'Unknown',
            }
            const fmtMs = ms => ms == null ? '—' : ms >= 1000 ? `${(ms/1000).toFixed(1)}s` : `${ms}ms`
            const totals       = intelStats?.totals
            const topRoute     = intelStats?.route_distribution?.[0]?.route

            return (
              <>
                {/* Header controls */}
                <div className="card" style={{ padding:'14px 20px', marginBottom:20, display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:10 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div className="section-label" style={{ marginBottom:0 }}>QUERY INTELLIGENCE</div>
                    <span className="tag tag-purple" style={{ fontSize:9 }}>RAG Analytics</span>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <select value={intelClientId} onChange={e => setIntelClientId(e.target.value)}
                      style={{ fontFamily:"'DM Mono'", fontSize:11, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 12px', cursor:'pointer', outline:'none' }}>
                      <option value="">All clients</option>
                      {clients.map(c => <option key={c.client_id} value={c.client_id}>{c.name}</option>)}
                    </select>
                    <select value={intelDays} onChange={e => setIntelDays(Number(e.target.value))}
                      style={{ fontFamily:"'DM Mono'", fontSize:11, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 12px', cursor:'pointer', outline:'none' }}>
                      {[7,14,30,60,90].map(d => <option key={d} value={d}>Last {d} days</option>)}
                    </select>
                    <motion.button onClick={() => setIntelRefresh(r => r+1)}
                      style={{ fontFamily:"'DM Mono'", fontSize:11, padding:'6px 14px', borderRadius:6, border:'1px solid var(--border2)', background:'transparent', color:'var(--muted2)', cursor:'pointer' }}
                      whileHover={{ borderColor:'var(--accent2)', color:'var(--accent2)' }} whileTap={{ scale:0.96 }}>
                      ↺ Refresh
                    </motion.button>
                  </div>
                </div>

                {intelLoad && <div className="loading-bar" />}

                {/* KPI strip — single horizontal stat card */}
                {(() => {
                  const avgMs = totals?.avg_response_ms
                  const fmtMs = avgMs ? (avgMs >= 1000 ? `${(avgMs/1000).toFixed(1)}s` : `${avgMs}ms`) : '—'
                  const kpis = [
                    { label:'TOTAL QUERIES',  value: totals?.total_queries  ?? '—', sub:`last ${intelDays} days`,    color:'var(--accent2)' },
                    { label:'ACTIVE CLIENTS', value: totals?.active_clients ?? '—', sub:'clients with queries',      color:'var(--accent)' },
                    { label:'AVG RESPONSE',   value: fmtMs,                          sub:'median query latency',     color:'#6ee7b7' },
                    { label:'TOP ROUTE',      value: topRoute ? (routeLabel[topRoute] || topRoute) : '—', sub:'most-used path', color: ROUTE_COLORS[topRoute] || 'var(--muted2)' },
                  ]
                  return (
                    <motion.div className="card" style={{ padding:0, display:'flex', marginBottom:24, overflow:'hidden' }}
                      variants={kpiStagger} initial="hidden" animate="show">
                      {kpis.map((k, i) => (
                        <motion.div key={k.label} variants={fadeUp} style={{
                          flex:1, minWidth:0,
                          padding:'18px 22px',
                          borderRight: i < kpis.length - 1 ? '1px solid var(--border2)' : 'none',
                        }}>
                          <div style={{ fontFamily:"'DM Mono'", fontSize:9, letterSpacing:'0.1em', color:'var(--muted)', textTransform:'uppercase', marginBottom:10 }}>{k.label}</div>
                          <div style={{ fontFamily:"'Syne', system-ui", fontSize:26, fontWeight:800, letterSpacing:'-0.03em', lineHeight:1.1, color:k.color, marginBottom:6, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{k.value}</div>
                          <div style={{ fontFamily:"'DM Mono'", fontSize:9, color:'var(--muted)', letterSpacing:'0.04em' }}>{k.sub}</div>
                        </motion.div>
                      ))}
                    </motion.div>
                  )
                })()}

                {intelStats && (
                  <>
                    {/* Charts row */}
                    <div className="chart-grid" style={{ marginBottom:24 }}>
                      {/* Route distribution */}
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.05, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Route Distribution</div><div className="card-desc">how queries are resolved — SQL, semantic, or ReAct agent</div></div>
                          <span className="tag tag-green">ROUTING</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={Math.max(180, intelStats.route_distribution.length * 36 + 20)}>
                            <BarChart
                              data={intelStats.route_distribution.map(r => ({ ...r, label: routeLabel[r.route] || r.route }))}
                              layout="vertical"
                              margin={{ top:4, right:24, left:4, bottom:4 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" horizontal={false} />
                              <XAxis type="number" tick={{ fill:'#64748b', fontSize:11 }} axisLine={false} tickLine={false} />
                              <YAxis type="category" dataKey="label" tick={{ fill:'#94a3b8', fontSize:11 }} width={110} axisLine={false} tickLine={false} />
                              <Tooltip {...TT} formatter={v => [v, 'Queries']} />
                              <Bar dataKey="count" radius={[0,4,4,0]} maxBarSize={22}>
                                {intelStats.route_distribution.map((d, i) => <Cell key={i} fill={ROUTE_COLORS[d.route] || '#818cf8'} />)}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>

                      {/* Daily volume */}
                      <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.1, duration:0.38, ease:E }}>
                        <div className="card-header">
                          <div><div className="card-title">Query Volume</div><div className="card-desc">daily query count across all clients</div></div>
                          <span className="tag tag-purple">TREND</span>
                        </div>
                        <div className="chart-wrap">
                          <ResponsiveContainer width="100%" height={200}>
                            <AreaChart data={intelStats.daily_volume} margin={{ top:8, right:12, left:-10, bottom:5 }}>
                              <defs>
                                <linearGradient id="qGrad" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.35} />
                                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                              <XAxis dataKey="day" tick={{ fill:'#64748b', fontSize:9 }} interval="preserveStartEnd" />
                              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
                              <Tooltip {...TT} formatter={v => [v, 'Queries']} />
                              <Area type="monotone" dataKey="queries" stroke="#818cf8" fill="url(#qGrad)" strokeWidth={2.5} dot={{ fill:'#818cf8', r:3, strokeWidth:0 }} activeDot={{ r:5 }} />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      </motion.div>
                    </div>

                    {/* Bottom tables row — minmax(0,1fr) forces true 50/50 regardless of content */}
                    <div style={{ display:'grid', gridTemplateColumns:'minmax(0,1fr) minmax(0,1fr)', gap:16, alignItems:'start', marginBottom:32 }}>

                      {/* Top questions */}
                      <motion.div className="card" style={{ padding:0, overflow:'clip' }} initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.15, duration:0.38, ease:E }}>
                        <div style={{ padding:'16px 18px 10px', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                          <div className="card-title">Top Questions</div>
                          <span className="tag tag-purple">FREQ</span>
                        </div>
                        <div style={{ overflowX:'auto' }}>
                          <table className="god-table" style={{ minWidth:380 }}>
                            <thead>
                              <tr>
                                <th>Question</th>
                                <th style={{ width:36, textAlign:'center' }}>×</th>
                                <th style={{ width:110 }}>Route</th>
                                <th style={{ width:72 }}>Avg</th>
                              </tr>
                            </thead>
                            <tbody>
                              {intelStats.top_questions.length === 0 ? (
                                <tr><td colSpan={4} style={{ textAlign:'center', padding:24, color:'var(--muted)', fontSize:12 }}>No queries logged yet</td></tr>
                              ) : intelStats.top_questions.map((q, i) => (
                                <tr key={i} className="god-row">
                                  <td style={{ fontFamily:'Inter,sans-serif', fontSize:12, maxWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={q.query}>{q.query}</td>
                                  <td style={{ fontFamily:"'DM Mono'", fontSize:12, fontWeight:700, color:'var(--accent2)', textAlign:'center' }}>{q.frequency}</td>
                                  <td>
                                    <span style={{ fontFamily:"'DM Mono'", fontSize:9, color:ROUTE_COLORS[q.route]||'var(--muted)', background:(ROUTE_COLORS[q.route]||'#64748b')+'18', border:`1px solid ${(ROUTE_COLORS[q.route]||'#64748b')}40`, borderRadius:4, padding:'2px 7px' }}>
                                      {routeLabel[q.route]||q.route||'—'}
                                    </span>
                                  </td>
                                  <td style={{ fontFamily:"'DM Mono'", fontSize:11, color:'var(--muted2)', whiteSpace:'nowrap' }}>{fmtMs(q.avg_ms)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>

                      {/* Per-client breakdown */}
                      <motion.div className="card" style={{ padding:0, overflow:'clip' }} initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.2, duration:0.38, ease:E }}>
                        <div style={{ padding:'16px 18px 10px', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                          <div className="card-title">Per-Client Activity</div>
                          <span className="tag tag-green">CLIENTS</span>
                        </div>
                        <div style={{ overflowX:'auto' }}>
                          <table className="god-table" style={{ minWidth:340 }}>
                            <thead>
                              <tr>
                                <th>Client</th>
                                <th style={{ width:64 }}>Queries</th>
                                <th style={{ width:110 }}>Top Route</th>
                                <th style={{ width:80 }}>Last Query</th>
                              </tr>
                            </thead>
                            <tbody>
                              {intelStats.per_client.length === 0 ? (
                                <tr><td colSpan={4} style={{ textAlign:'center', padding:24, color:'var(--muted)', fontSize:12 }}>No data yet</td></tr>
                              ) : intelStats.per_client.map((c, i) => (
                                <tr key={i} className="god-row">
                                  <td style={{ fontSize:12, fontWeight:700, maxWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{c.client_name}</td>
                                  <td style={{ fontFamily:"'DM Mono'", fontSize:12, fontWeight:700, color:'var(--accent2)' }}>{c.total_queries}</td>
                                  <td>
                                    <span style={{ fontFamily:"'DM Mono'", fontSize:9, color:ROUTE_COLORS[c.top_route]||'var(--muted)', background:(ROUTE_COLORS[c.top_route]||'#64748b')+'18', border:`1px solid ${(ROUTE_COLORS[c.top_route]||'#64748b')}40`, borderRadius:4, padding:'2px 7px' }}>
                                      {routeLabel[c.top_route]||c.top_route||'—'}
                                    </span>
                                  </td>
                                  <td style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted)', whiteSpace:'nowrap' }}>
                                    {c.last_query_at ? new Date(c.last_query_at).toLocaleDateString('en-AU',{day:'2-digit',month:'short'}) : '—'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>

                    </div>
                  </>
                )}

                {/* ── Admin RAG Chat ── */}
                <div className="section-label" style={{ marginBottom:12 }}>ADMIN DATA CHAT</div>
                <motion.div className="card" initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.25, duration:0.38, ease:E }}>
                  {/* Client selector */}
                  {(() => {
                    const SYSTEM_MSG_CLIENT = 'Select a client above and ask anything about their call data — every answer is grounded in real call records.'
                    const SYSTEM_MSG_ADMIN  = 'Platform mode — ask cross-client questions like "which client has more successful calls?" or "compare Artel vs MVAA engagement". Every answer comes from real data.'
                    function onChatClientChange(val) {
                      setChatClientId(val)
                      setChatMessages([{ role: 'system', text: val === 'heya_admin' ? SYSTEM_MSG_ADMIN : SYSTEM_MSG_CLIENT }])
                    }
                    return (
                      <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:16, paddingBottom:14, borderBottom:'1px solid var(--border)' }}>
                        <span style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted)', letterSpacing:'0.08em' }}>QUERYING</span>
                        <select value={chatClientId} onChange={e => onChatClientChange(e.target.value)}
                          style={{ fontFamily:"'DM Mono'", fontSize:12, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 12px', cursor:'pointer' }}>
                          <option value="">— pick a client —</option>
                          <option value="heya_admin">Platform Overview (All Clients)</option>
                          {clients.map(c => <option key={c.client_id} value={c.client_id}>{c.name}</option>)}
                        </select>
                        {chatClientId === 'heya_admin' && (
                          <span style={{ fontFamily:"'DM Mono'", fontSize:9, color:'#c084fc', background:'#c084fc12', border:'1px solid #c084fc30', borderRadius:5, padding:'2px 8px' }}>
                            CROSS-CLIENT
                          </span>
                        )}
                        <div style={{ flex:1 }} />
                        <span className="tag tag-purple" style={{ fontSize:9 }}>RAG</span>
                        <span className="tag tag-green"  style={{ fontSize:9 }}>Live DB</span>
                        <motion.button onClick={() => setChatMessages([{ role:'system', text: chatClientId === 'heya_admin' ? SYSTEM_MSG_ADMIN : SYSTEM_MSG_CLIENT }])}
                          className="export-btn" style={{ fontSize:10, padding:'4px 10px' }}
                          whileHover={{ scale:1.04 }} whileTap={{ scale:0.95 }}>
                          Clear
                        </motion.button>
                      </div>
                    )
                  })()}

                  {/* Messages */}
                  <div style={{ maxHeight:380, overflowY:'auto', display:'flex', flexDirection:'column', gap:12, marginBottom:14 }}>
                    {chatMessages.map((m, i) => (
                      <div key={i} style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                        <div style={{ flexShrink:0, width:30, height:30, borderRadius:'50%', display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, fontWeight:700, fontFamily:"'DM Mono'",
                          background: m.role==='user' ? '#818cf820' : m.role==='system' ? '#6ee7b715' : '#22c55e18',
                          color:      m.role==='user' ? 'var(--accent2)' : m.role==='system' ? '#6ee7b7' : '#22c55e',
                          border:     `1px solid ${m.role==='user' ? '#818cf830' : m.role==='system' ? '#6ee7b730' : '#22c55e30'}`,
                        }}>
                          {m.role==='user' ? 'You' : m.role==='system' ? 'H' : 'AI'}
                        </div>
                        <div style={{ flex:1, background:'var(--surface)', border:'1px solid var(--border)', borderRadius:10, padding:'10px 14px', fontSize:13, lineHeight:1.65, whiteSpace:'pre-wrap', color:'var(--text)' }}>
                          {m.text}
                          {m.route && m.route !== 'error' && (
                            <div style={{ marginTop:8 }}>
                              <span style={{ fontFamily:"'DM Mono'", fontSize:9, color: ROUTE_COLORS[m.route]||'var(--muted)', background:(ROUTE_COLORS[m.route]||'#64748b')+'18', border:`1px solid ${(ROUTE_COLORS[m.route]||'#64748b')}40`, borderRadius:4, padding:'1px 7px' }}>
                                {routeLabel[m.route]||m.route}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                    {chatLoading && (
                      <div style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                        <div style={{ width:30, height:30, borderRadius:'50%', background:'#22c55e18', border:'1px solid #22c55e30', display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, color:'#22c55e', fontFamily:"'DM Mono'" }}>AI</div>
                        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:10, padding:'12px 16px' }}>
                          <div className="chat-typing"><span/><span/><span/></div>
                        </div>
                      </div>
                    )}
                    <div ref={chatBottomRef} />
                  </div>

                  {/* Suggestion pills */}
                  <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:10 }}>
                    {(chatClientId === 'heya_admin'
                      ? [
                          'Which client has a higher success rate?',
                          'Compare engagement scores across all clients',
                          'Which client has more silence in calls?',
                          'How are all agents performing?',
                          'Which client has better conversation flow?',
                          'Compare call volumes across clients',
                        ]
                      : [
                          'How many calls do I have?',
                          'What is the success rate?',
                          'Which agent is performing worst?',
                          'What topics are most common?',
                          'Show me the worst calls',
                        ]
                    ).map(p => (
                      <motion.span key={p}
                        onClick={() => sendAdminChat(p)}
                        whileHover={{ scale:1.04, y:-1 }} whileTap={{ scale:0.95 }}
                        style={{ fontFamily:"'DM Mono'", fontSize:10, color: chatClientId === 'heya_admin' ? '#c084fc' : 'var(--accent2)', background: chatClientId === 'heya_admin' ? '#c084fc10' : '#818cf810', border:`1px solid ${chatClientId === 'heya_admin' ? '#c084fc28' : '#818cf828'}`, borderRadius:20, padding:'4px 11px', cursor: chatClientId ? 'pointer' : 'not-allowed', opacity: chatClientId ? 1 : 0.4 }}>
                        {p}
                      </motion.span>
                    ))}
                  </div>

                  {/* Input */}
                  <div style={{ display:'flex', gap:8 }}>
                    <input
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      onKeyDown={e => e.key==='Enter' && sendAdminChat()}
                      placeholder={
                        !chatClientId ? 'Select a client or platform above…' :
                        chatClientId === 'heya_admin' ? 'Ask a cross-client question — compare clients, rank agents, platform totals…' :
                        `Ask about ${clients.find(c=>c.client_id===chatClientId)?.name||'this client'}…`
                      }
                      disabled={chatLoading || !chatClientId}
                      style={{ flex:1, fontFamily:"'DM Mono'", fontSize:12, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:8, padding:'9px 14px', outline:'none' }}
                    />
                    <motion.button onClick={() => sendAdminChat()} disabled={chatLoading || !chatInput.trim() || !chatClientId}
                      style={{ fontFamily:"'DM Mono'", fontSize:12, padding:'9px 20px', borderRadius:8, border:'none', background:'var(--accent2)', color:'#0d0d14', fontWeight:700, cursor:'pointer', opacity: (!chatInput.trim()||!chatClientId) ? 0.4 : 1 }}
                      whileHover={{ scale:1.04 }} whileTap={{ scale:0.95 }}>
                      Send →
                    </motion.button>
                  </div>
                </motion.div>
              </>
            )
          })()}

          {/* ════════════════════ FEED ════════════════════ */}
          {tab === 'feed' && (() => {
            const hasFilters = feedFilterClient||feedFilterAgent||feedFilterDateFrom||feedFilterDateTo||feedFilterDir||feedFilterFlow||feedFilterTraj||feedFilterSent||feedFilterTopic
            const selStyle   = { fontFamily:"'DM Mono'", fontSize:11, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'5px 10px', cursor:'pointer', outline:'none' }
            const inpStyle   = { ...selStyle, cursor:'text', width:120 }
            const lblStyle   = { fontFamily:"'DM Mono'", fontSize:9, color:'var(--muted)', letterSpacing:'0.08em', marginBottom:3 }

            const TRAJ_META  = { improving:{ color:'#22c55e', symbol:'↑' }, stable:{ color:'var(--muted2)', symbol:'→' }, deteriorating:{ color:'#ef4444', symbol:'↓' } }
            const SENT_META  = { positive:{ color:'#22c55e' }, negative:{ color:'#ef4444' }, neutral:{ color:'var(--muted2)' } }
            const TOPIC_COLORS_L = { booking:'#6ee7b7', cancellation:'#fb923c', complaint:'#f87171', payment:'#34d399', enquiry:'#818cf8', technical_support:'#22d3ee', emergency:'#ef4444', follow_up:'#a78bfa', general:'#64748b', at_fault:'#fbbf24', welcome_pack:'#c084fc' }

            return (
              <>
                {/* ── Header row ── */}
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14, flexWrap:'wrap', gap:10 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                    <div className="section-label" style={{ marginBottom:0 }}>CALLS &amp; LIVE FEED</div>
                    <AnimatePresence>
                      {feedNewIds.size > 0 && (
                        <motion.span initial={{ opacity:0, scale:0.8 }} animate={{ opacity:1, scale:1 }} exit={{ opacity:0, scale:0.8 }}
                          style={{ fontFamily:"'DM Mono'", fontSize:11, color:'#22c55e', background:'#22c55e15', border:'1px solid #22c55e40', borderRadius:6, padding:'3px 10px' }}>
                          +{feedNewIds.size} new
                        </motion.span>
                      )}
                    </AnimatePresence>
                    <div style={{ display:'flex', alignItems:'center', gap:7, fontFamily:"'DM Mono'", fontSize:10, letterSpacing:'0.06em' }}>
                      <span style={{ width:7, height:7, borderRadius:'50%', background:'#22c55e', boxShadow:'0 0 6px #22c55e', display:'inline-block', animation:'pulse-green 2s infinite' }} />
                      <span style={{ color:'#22c55e' }}>LIVE</span>
                      <span style={{ color:'var(--muted)', marginLeft:6 }}>refresh in {feedCountdown}s</span>
                      {feedSync && <span style={{ color:'var(--muted)' }}>· {feedSync.toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</span>}
                    </div>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    {feedCalls.length > 0 && (
                      <span style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted)', background:'var(--surface2)', border:'1px solid var(--border2)', borderRadius:5, padding:'3px 9px' }}>
                        {feedCalls.length} calls
                      </span>
                    )}
                    <motion.button onClick={exportFeedCSV} disabled={!feedCalls.length}
                      className="export-btn" style={{ fontSize:11, padding:'5px 14px', opacity: feedCalls.length ? 1 : 0.4 }}
                      whileHover={{ scale:1.04 }} whileTap={{ scale:0.95 }}>
                      ↓ Export CSV
                    </motion.button>
                  </div>
                </div>

                {/* ── Filter bar ── */}
                <motion.div className="card" style={{ padding:'12px 16px', marginBottom:14 }}
                  initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.28, ease:E }}>
                  <div style={{ display:'flex', flexWrap:'wrap', gap:12, alignItems:'flex-end' }}>

                    {/* Client */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>CLIENT</span>
                      <select value={feedFilterClient} onChange={e => setFeedFilterClient(e.target.value)} style={selStyle}>
                        <option value="">All Clients</option>
                        {clients.map(c => <option key={c.client_id} value={c.client_id}>{c.name}</option>)}
                      </select>
                    </div>

                    {/* Agent — enabled only when a client is selected */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={{ ...lblStyle, color: feedFilterClient ? 'var(--muted)' : 'var(--border2)' }}>AGENT</span>
                      <select value={feedFilterAgent} onChange={e => setFeedFilterAgent(e.target.value)}
                        disabled={!feedFilterClient}
                        style={{ ...selStyle, opacity: feedFilterClient ? 1 : 0.45, cursor: feedFilterClient ? 'pointer' : 'not-allowed' }}>
                        <option value="">{feedFilterClient ? 'All Agents' : 'Select client first'}</option>
                        {feedAgents.map(a => <option key={a.id} value={a.id}>{a.persona_name}</option>)}
                      </select>
                    </div>

                    {/* Date From */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>FROM</span>
                      <input type="date" value={feedFilterDateFrom} onChange={e => setFeedFilterDateFrom(e.target.value)} style={inpStyle} />
                    </div>

                    {/* Date To */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>TO</span>
                      <input type="date" value={feedFilterDateTo} onChange={e => setFeedFilterDateTo(e.target.value)} style={inpStyle} />
                    </div>

                    {/* Direction */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>DIRECTION</span>
                      <select value={feedFilterDir} onChange={e => setFeedFilterDir(e.target.value)} style={selStyle}>
                        <option value="">All</option>
                        <option value="inbound">Inbound</option>
                        <option value="outbound">Outbound</option>
                      </select>
                    </div>

                    {/* Flow */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>FLOW</span>
                      <select value={feedFilterFlow} onChange={e => setFeedFilterFlow(e.target.value)} style={selStyle}>
                        <option value="">All</option>
                        <option value="smooth">Smooth</option>
                        <option value="moderate">Moderate</option>
                        <option value="poor">Poor</option>
                      </select>
                    </div>

                    {/* Trajectory */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>TRAJECTORY</span>
                      <select value={feedFilterTraj} onChange={e => setFeedFilterTraj(e.target.value)} style={selStyle}>
                        <option value="">All</option>
                        <option value="improving">↑ Improving</option>
                        <option value="stable">→ Stable</option>
                        <option value="deteriorating">↓ Deteriorating</option>
                      </select>
                    </div>

                    {/* Sentiment */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>SENTIMENT</span>
                      <select value={feedFilterSent} onChange={e => setFeedFilterSent(e.target.value)} style={selStyle}>
                        <option value="">All</option>
                        <option value="positive">Positive</option>
                        <option value="neutral">Neutral</option>
                        <option value="negative">Negative</option>
                      </select>
                    </div>

                    {/* Topic */}
                    <div style={{ display:'flex', flexDirection:'column' }}>
                      <span style={lblStyle}>TOPIC</span>
                      <select value={feedFilterTopic} onChange={e => setFeedFilterTopic(e.target.value)} style={selStyle}>
                        <option value="">All</option>
                        {['booking','cancellation','complaint','payment','enquiry','technical_support','emergency','follow_up','general'].map(t => (
                          <option key={t} value={t}>{t.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())}</option>
                        ))}
                      </select>
                    </div>

                    {/* Clear button */}
                    {hasFilters && (
                      <motion.button onClick={clearFeedFilters}
                        style={{ fontFamily:"'DM Mono'", fontSize:11, padding:'5px 12px', background:'none', border:'1px solid var(--border2)', borderRadius:6, color:'var(--accent3)', cursor:'pointer', alignSelf:'flex-end' }}
                        whileHover={{ borderColor:'var(--accent3)' }} whileTap={{ scale:0.95 }}>
                        × Clear
                      </motion.button>
                    )}
                  </div>
                </motion.div>

                {feedLoad && <div className="loading-bar" />}

                {/* ── Full metrics table ── */}
                <motion.div className="card" style={{ padding:0, overflow:'clip' }}
                  initial={{ opacity:0, y:16 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.4, ease:E }}>
                  <div className="table-wrap" style={{ margin:0 }}>
                    <table className="god-table">
                      <thead>
                        <tr>
                          <th style={{ width:14 }}></th>
                          <th>STATUS</th><th>CLIENT</th><th>CALL ID</th><th>AGENT</th>
                          <th>DIR</th><th>DATE &amp; TIME</th><th>DUR</th>
                          <th>QUALITY</th><th>ENG</th><th>SILENCE</th><th>INTS</th>
                          <th>FLOW</th><th>TRAJECTORY</th><th>SENTIMENT</th>
                          <th>EMOTION</th><th>TOPIC</th><th>OUTCOME</th>
                        </tr>
                      </thead>
                      <motion.tbody variants={rowStagger} initial="hidden" animate="show">
                        {feedCalls.length === 0 ? (
                          <tr><td colSpan={18} style={{ textAlign:'center', padding:40, color:'var(--muted)', fontFamily:"'DM Mono'", fontSize:12 }}>
                            {feedLoad ? 'Loading…' : hasFilters ? 'No calls match these filters' : 'No calls yet'}
                          </td></tr>
                        ) : feedCalls.map(c => {
                          const isProcessing = c.processing_status === 'pending_audio'
                          const isFailed     = c.processing_status === 'failed'
                          const statusColor  = isFailed ? '#ef4444' : isProcessing ? '#fbbf24' : c.quality_score != null ? '#22c55e' : '#818cf8'
                          const statusLabel  = isFailed ? 'FAILED' : isProcessing ? 'PROCESSING' : c.quality_score != null ? 'COMPLETE' : 'INGESTED'
                          const isNew        = feedNewIds.has(c.call_id)
                          const gc           = GRADE_COLORS[c.quality_grade] || '#64748b'
                          const ec           = EMOTION_COLORS[c.dominant_emotion] || '#64748b'
                          const dt           = c.start_timestamp ? new Date(c.start_timestamp) : null
                          const dtStr        = dt ? dt.toLocaleDateString('en-AU',{day:'2-digit',month:'short',year:'numeric'}) + ' ' + dt.toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit'}) : '—'
                          const trajMeta     = TRAJ_META[c.sentiment_trajectory]
                          const sentMeta     = SENT_META[c.user_sentiment?.toLowerCase()]
                          const topicColor   = TOPIC_COLORS_L[c.topic] || '#64748b'
                          const eng          = c.engagement_score != null ? parseFloat(c.engagement_score) : null
                          return (
                            <motion.tr key={c.call_id} className="god-row" variants={fadeUp}
                              onClick={() => setCallRow(c)}
                              style={{ background: isNew ? '#22c55e06' : 'transparent', borderLeft: isNew ? '2px solid #22c55e40' : '2px solid transparent', transition:'background 1s ease,border-color 1s ease' }}>
                              <td style={{ paddingLeft:10 }}>
                                <span style={{ display:'inline-block', width:7, height:7, borderRadius:'50%', background:statusColor, boxShadow:`0 0 5px ${statusColor}80`, animation:isProcessing?'pulse-green 1.2s infinite':'none' }} />
                              </td>
                              <td><span style={{ fontFamily:"'DM Mono'", fontSize:9, color:statusColor, letterSpacing:'0.06em' }}>{statusLabel}</span></td>
                              <td style={{ fontSize:11, fontWeight:700 }}>{c.client_name || c.client_id}</td>
                              <td style={{ fontFamily:"'DM Mono'", fontSize:10, maxWidth:110, overflow:'hidden', textOverflow:'ellipsis' }}>{c.call_id}</td>
                              <td style={{ fontSize:11 }}>
                                {c.agent_name
                                  ? <span style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--accent2)', background:'#818cf812', border:'1px solid #818cf830', borderRadius:4, padding:'1px 6px' }}>{c.agent_name}</span>
                                  : <span style={{ color:'var(--muted)' }}>—</span>}
                              </td>
                              <td>
                                {c.direction
                                  ? <span className={`tag ${c.direction==='inbound'?'tag-green':'tag-purple'}`} style={{fontSize:9}}>{c.direction}</span>
                                  : <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                              <td style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted2)', whiteSpace:'nowrap' }}>{dtStr}</td>
                              <td style={{ fontFamily:"'DM Mono'", fontSize:11, color:'var(--muted2)' }}>{c.duration_ms ? `${Math.round(c.duration_ms/1000)}s` : '—'}</td>
                              <td>
                                {c.quality_score != null
                                  ? <span style={{ fontFamily:"'DM Mono'", fontSize:11, fontWeight:700, color:gc }}>{c.quality_grade} <span style={{opacity:0.6,fontWeight:400}}>{c.quality_score}</span></span>
                                  : <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                              <td>
                                {eng != null ? (
                                  <div style={{ display:'flex', alignItems:'center', gap:5 }}>
                                    <div style={{ width:36, height:3, background:'var(--track-bg)', borderRadius:2, overflow:'hidden' }}>
                                      <div style={{ width:`${eng}%`, height:'100%', background: eng>=70?'#22c55e':eng>=45?'#818cf8':'#ef4444', borderRadius:2 }} />
                                    </div>
                                    <span style={{ fontFamily:"'DM Mono'", fontSize:10 }}>{eng.toFixed(0)}</span>
                                  </div>
                                ) : <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                              <td style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted2)' }}>
                                {c.silence_ratio != null ? `${(c.silence_ratio*100).toFixed(1)}%` : '—'}
                              </td>
                              <td style={{ fontFamily:"'DM Mono'", fontSize:11, color:'var(--muted2)', textAlign:'center' }}>{c.interruption_count ?? '—'}</td>
                              <td>{c.conversation_flow ? <span className={`flow-chip chip-${c.conversation_flow}`}>{c.conversation_flow}</span> : <span style={{color:'var(--muted)'}}>—</span>}</td>
                              <td>
                                {trajMeta
                                  ? <span style={{ fontFamily:"'DM Mono'", fontSize:10, fontWeight:700, color:trajMeta.color }}>{trajMeta.symbol} {c.sentiment_trajectory}</span>
                                  : <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                              <td>
                                {c.user_sentiment
                                  ? <span style={{ fontFamily:"'DM Mono'", fontSize:10, color: sentMeta?.color || 'var(--muted2)' }}>{c.user_sentiment}</span>
                                  : <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                              <td>{c.dominant_emotion && EMOTION_COLORS[c.dominant_emotion] ? <span style={{fontFamily:"'DM Mono'",fontSize:10,color:ec}}>{c.dominant_emotion}</span> : <span style={{color:'var(--muted)'}}>—</span>}</td>
                              <td>
                                {c.topic
                                  ? <span style={{ fontFamily:"'DM Mono'", fontSize:9, color:topicColor, background:topicColor+'18', border:`1px solid ${topicColor}40`, borderRadius:4, padding:'1px 6px', textTransform:'capitalize', whiteSpace:'nowrap' }}>{c.topic.replace(/_/g,' ')}</span>
                                  : <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                              <td>
                                {c.call_successful===true  && <span className="tag tag-success" style={{fontSize:9}}>OK</span>}
                                {c.call_successful===false && <span className="tag tag-fail"    style={{fontSize:9}}>FAIL</span>}
                                {c.call_successful==null   && <span style={{color:'var(--muted)'}}>—</span>}
                              </td>
                            </motion.tr>
                          )
                        })}
                      </motion.tbody>
                    </table>
                  </div>
                </motion.div>
              </>
            )
          })()}

          {/* ════════════════════ USERS ════════════════════ */}
          {tab === 'users' && (
            <>
              <div className="section-label">USER MANAGEMENT</div>

              <motion.div
                className="card"
                style={{ marginBottom: 20 }}
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: E }}
              >
                <div className="card-header">
                  <div>
                    <div className="card-title">Provision New User</div>
                    <div className="card-desc">create a client login or a new admin account</div>
                  </div>
                  <span className="tag tag-purple">PROVISION</span>
                </div>
                <form onSubmit={handleCreateUser} style={{ marginTop: 16 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12, marginBottom: 12 }}>
                    <div>
                      <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Email</div>
                      <input className="filter-search" type="email" placeholder="user@example.com" style={{ width: '100%' }}
                        value={createForm.email} onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))} required />
                    </div>
                    <div>
                      <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Password</div>
                      <input className="filter-search" type="password" placeholder="••••••••" style={{ width: '100%' }}
                        value={createForm.password} onChange={e => setCreateForm(f => ({ ...f, password: e.target.value }))} required />
                    </div>
                    <div>
                      <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Role</div>
                      <select className="filter-select" style={{ width: '100%' }} value={createForm.role}
                        onChange={e => setCreateForm(f => ({ ...f, role: e.target.value, client_id: '' }))}>
                        <option value="client">Client user</option>
                        <option value="heya_admin">Platform admin</option>
                      </select>
                    </div>
                  </div>
                  {createForm.role === 'client' && (
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Assign Client</div>
                      <select className="filter-select" style={{ width: '100%', maxWidth: 340 }} value={createForm.client_id}
                        onChange={e => setCreateForm(f => ({ ...f, client_id: e.target.value }))} required>
                        <option value="">Select client…</option>
                        {clients.map(c => <option key={c.client_id} value={c.client_id}>{c.name}</option>)}
                      </select>
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <motion.button
                      type="submit"
                      className="export-btn export-btn-primary"
                      disabled={creating}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.97 }}
                      style={{ minWidth: 140, fontWeight: 700 }}
                    >
                      {creating ? 'Provisioning…' : 'Create User →'}
                    </motion.button>
                    {createMsg.err && <span style={{ fontFamily:"'DM Mono'", fontSize:12, color:'var(--warn)' }}>{createMsg.err}</span>}
                    {createMsg.ok  && <span style={{ fontFamily:"'DM Mono'", fontSize:12, color:'var(--accent)' }}>{createMsg.ok}</span>}
                  </div>
                </form>
              </motion.div>

              {usersLoad && <div className="loading-bar" />}

              <motion.div
                className="card"
                style={{ padding: 0, overflow: 'clip' }}
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15, duration: 0.4, ease: E }}
              >
                <div className="table-wrap" style={{ margin: 0 }}>
                  <table className="god-table">
                    <thead>
                      <tr><th>EMAIL</th><th>ROLE</th><th>CLIENT</th><th>USER ID</th><th>CREATED</th><th></th></tr>
                    </thead>
                    <motion.tbody variants={rowStagger} initial="hidden" animate="show">
                      {users.length === 0 ? (
                        <tr><td colSpan={6} style={{ textAlign: 'center', padding: 28, color: 'var(--muted)', fontFamily: "'DM Mono'", fontSize: 12 }}>
                          {usersLoad ? 'Loading…' : 'No users found'}
                        </td></tr>
                      ) : users.map(u => (
                        <motion.tr key={u.user_id} className="god-row" variants={fadeUp}>
                          <td style={{ fontFamily: "'DM Mono'", fontSize: 12 }}>{u.email}</td>
                          <td>
                            <span className={`tag ${u.role === 'heya_admin' ? 'tag-purple' : 'tag-green'}`} style={{ fontSize: 10 }}>
                              {u.role === 'heya_admin' ? 'ADMIN' : 'CLIENT'}
                            </span>
                          </td>
                          <td style={{ fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted2)' }}>{u.client_name || u.client_id || '—'}</td>
                          <td style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.user_id}</td>
                          <td style={{ fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted)' }}>
                            {u.created_at ? new Date(u.created_at).toLocaleDateString('en-AU', { day:'2-digit', month:'short', year:'numeric' }) : '—'}
                          </td>
                          <td>
                            <motion.button
                              className="export-btn"
                              disabled={deleting === u.user_id}
                              whileHover={{ borderColor: '#f87171', color: '#f87171' }}
                              whileTap={{ scale: 0.96 }}
                              style={{ fontSize: 10, padding: '3px 10px' }}
                              onClick={() => handleDeleteUser(u.user_id, u.email)}
                            >
                              {deleting === u.user_id ? '…' : 'Revoke'}
                            </motion.button>
                          </td>
                        </motion.tr>
                      ))}
                    </motion.tbody>
                  </table>
                </div>
              </motion.div>
            </>
          )}

          {/* ════════════════════ ALERTS ════════════════════ */}
          {tab === 'alerts' && (
            <>
              <div className="section-label">CLIENT ALERT CONFIGURATION</div>

              {/* Toast */}
              <AnimatePresence>
                {alertToast && (
                  <motion.div
                    style={{ position:'fixed', top:72, right:24, zIndex:9999, padding:'10px 18px', borderRadius:10, fontSize:13, fontFamily:'Inter,sans-serif', fontWeight:500, background: alertToast.ok ? '#6ee7b720' : '#f8717120', border: `1px solid ${alertToast.ok ? '#6ee7b740' : '#f8717140'}`, color: alertToast.ok ? '#6ee7b7' : '#f87171', backdropFilter:'blur(8px)' }}
                    initial={{ opacity:0, y:-14, scale:0.95 }} animate={{ opacity:1, y:0, scale:1 }} exit={{ opacity:0, y:-10, scale:0.95 }}
                    transition={{ type:'spring', stiffness:340, damping:24 }}>
                    {alertToast.msg}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Client selector */}
              <motion.div className="card" style={{ padding:'16px 20px', marginBottom:16, display:'flex', alignItems:'center', gap:16 }}
                initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.3 }}>
                <span style={{ fontFamily:"'DM Mono'", fontSize:11, color:'var(--muted)', letterSpacing:'0.06em' }}>CLIENT</span>
                <select
                  value={alertClientId}
                  onChange={e => setAlertClientId(e.target.value)}
                  style={{ fontFamily:"'DM Mono'", fontSize:12, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 12px', cursor:'pointer' }}>
                  {clients.map(c => <option key={c.client_id} value={c.client_id}>{c.name} ({c.client_id})</option>)}
                </select>
                <div style={{ flex:1 }} />
                <motion.button
                  onClick={() => { api.post(`/alerts/digest/${alertClientId}`).then(() => showAlertToast('Digest sending')).catch(() => showAlertToast('Failed', false)) }}
                  style={{ fontFamily:"'DM Mono'", fontSize:11, padding:'6px 14px', borderRadius:6, border:'1px solid var(--border2)', background:'transparent', color:'var(--muted2)', cursor:'pointer', letterSpacing:'0.04em' }}
                  whileHover={{ borderColor:'var(--accent2)', color:'var(--accent2)' }} whileTap={{ scale:0.96 }}>
                  Send Digest
                </motion.button>
                <motion.button
                  onClick={runAlertChecks} disabled={alertRunning}
                  style={{ fontFamily:"'DM Mono'", fontSize:11, padding:'6px 14px', borderRadius:6, border:'1px solid var(--accent2)', background:'var(--accent2)', color:'#000', cursor:'pointer', letterSpacing:'0.04em', opacity: alertRunning ? 0.6 : 1 }}
                  whileHover={{ opacity:0.85 }} whileTap={{ scale:0.96 }}>
                  {alertRunning ? 'Checking...' : 'Run Checks'}
                </motion.button>
              </motion.div>

              {alertLoading ? (
                <div className="loading-bar" />
              ) : (
                <>
                  {/* Alert type cards */}
                  <motion.div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(340px,1fr))', gap:12, marginBottom:32 }}
                    initial="hidden" animate="show"
                    variants={{ hidden:{}, show:{ transition:{ staggerChildren:0.06 } } }}>
                    {ADMIN_ALERT_TYPES.map(({ id, label, desc }) => {
                      const draft    = alertDrafts[id] || { enabled:false, email:'', min_priority:'warning' }
                      const saved    = alertConfigs[id]
                      const isSaving = alertSaving === id
                      const isTesting = alertTesting === id
                      const isDirty  = JSON.stringify(draft) !== JSON.stringify({ enabled: saved?.enabled ?? false, email: saved?.email ?? '', min_priority: saved?.min_priority ?? 'warning' })
                      return (
                        <motion.div key={id}
                          variants={{ hidden:{opacity:0,y:16}, show:{opacity:1,y:0,transition:{duration:0.3}} }}
                          style={{ background:'var(--surface)', border:`1px solid ${draft.enabled ? 'var(--accent2)' : 'var(--border)'}`, borderRadius:12, padding:'14px 16px', transition:'border-color 0.2s' }}>
                          <div style={{ display:'flex', alignItems:'flex-start', gap:12 }}>
                            <div style={{ flex:1 }}>
                              <div style={{ fontFamily:'Inter,sans-serif', fontSize:13, fontWeight:600, color:'var(--text)', marginBottom:3 }}>{label}</div>
                              <div style={{ fontFamily:'Inter,sans-serif', fontSize:11, color:'var(--muted)', lineHeight:1.5 }}>{desc}</div>
                            </div>
                            <label style={{ display:'flex', alignItems:'center', cursor:'pointer', flexShrink:0 }}>
                              <input type="checkbox" checked={draft.enabled} onChange={e => updateAlertDraft(id, 'enabled', e.target.checked)} style={{ display:'none' }} />
                              <span style={{ display:'inline-flex', width:36, height:20, borderRadius:10, background: draft.enabled ? 'var(--accent2)' : 'var(--surface3,#2a2a3a)', border:'1px solid var(--border2)', position:'relative', transition:'background 0.2s', cursor:'pointer' }}>
                                <span style={{ position:'absolute', top:2, left: draft.enabled ? 18 : 2, width:14, height:14, borderRadius:'50%', background:'#fff', transition:'left 0.18s', boxShadow:'0 1px 3px #0004' }} />
                              </span>
                            </label>
                          </div>
                          <AnimatePresence initial={false}>
                          {draft.enabled && (
                            <motion.div initial={{height:0,opacity:0}} animate={{height:'auto',opacity:1}} exit={{height:0,opacity:0}} transition={{duration:0.22}} style={{overflow:'hidden'}}>
                              <div style={{ marginTop:12, display:'flex', gap:8, flexWrap:'wrap' }}>
                                <input type="email" value={draft.email} placeholder="Email address"
                                  onChange={e => updateAlertDraft(id, 'email', e.target.value)}
                                  style={{ flex:1, minWidth:180, fontFamily:"'DM Mono'", fontSize:11, background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 10px' }} />
                                {id !== 'weekly_digest' && (
                                  <select value={draft.min_priority} onChange={e => updateAlertDraft(id, 'min_priority', e.target.value)}
                                    style={{ fontFamily:"'DM Mono'", fontSize:11, background:'var(--surface2)', color:'var(--muted2)', border:'1px solid var(--border2)', borderRadius:6, padding:'6px 10px' }}>
                                    <option value="warning">Warning +</option>
                                    <option value="critical">Critical only</option>
                                  </select>
                                )}
                              </div>
                              <div style={{ marginTop:10, display:'flex', alignItems:'center', gap:8 }}>
                                {saved?.last_triggered && (
                                  <span style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted)', flex:1 }}>
                                    Last: {new Date(saved.last_triggered).toLocaleString('en-AU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}
                                  </span>
                                )}
                                <div style={{ flex:1 }} />
                                <motion.button onClick={() => sendAlertTest(id)} disabled={isTesting}
                                  style={{ fontFamily:"'DM Mono'", fontSize:10, padding:'4px 10px', borderRadius:5, border:'1px solid var(--border2)', background:'transparent', color:'var(--muted2)', cursor:'pointer' }}
                                  whileHover={{ borderColor:'var(--accent3)', color:'var(--accent3)' }} whileTap={{ scale:0.95 }}>
                                  {isTesting ? 'Sending...' : 'Test email'}
                                </motion.button>
                                <motion.button onClick={() => saveAlertConfig(id)} disabled={isSaving || !isDirty}
                                  style={{ fontFamily:"'DM Mono'", fontSize:10, padding:'4px 10px', borderRadius:5, border:`1px solid ${isDirty ? 'var(--accent2)' : 'var(--border)'}`, background: isDirty ? 'var(--accent2)' : 'transparent', color: isDirty ? '#000' : 'var(--muted)', cursor: isDirty ? 'pointer' : 'default' }}
                                  whileHover={{ opacity:0.85 }} whileTap={{ scale:0.95 }}>
                                  {isSaving ? 'Saving...' : isDirty ? 'Save' : 'Saved ✓'}
                                </motion.button>
                              </div>
                            </motion.div>
                          )}
                          </AnimatePresence>
                        </motion.div>
                      )
                    })}
                  </motion.div>

                  {/* Alert history */}
                  <div className="section-label">ALERT HISTORY</div>
                  <motion.div className="card" style={{ padding:0, overflow:'clip' }}
                    initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.15, duration:0.3 }}>
                    {alertHistory.length === 0 ? (
                      <div style={{ padding:24, color:'var(--muted)', fontFamily:"'DM Mono'", fontSize:12, textAlign:'center' }}>
                        No alerts sent yet — save a config and click "Run Checks"
                      </div>
                    ) : (
                      <table className="god-table">
                        <thead>
                          <tr>
                            <th>Alert Type</th>
                            <th>Subject</th>
                            <th>Status</th>
                            <th>Sent At</th>
                          </tr>
                        </thead>
                        <tbody>
                          {alertHistory.map((log, i) => {
                            const meta = ALERT_STATUS_META[log.status] || ALERT_STATUS_META.failed
                            return (
                              <motion.tr key={log.id || i}
                                initial={{ opacity:0, x:-10 }} animate={{ opacity:1, x:0 }}
                                transition={{ delay: i * 0.04, duration:0.2 }}>
                                <td style={{ fontFamily:"'DM Mono'", fontSize:11 }}>{log.alert_type?.replace(/_/g,' ') || '—'}</td>
                                <td style={{ fontFamily:"'DM Mono'", fontSize:11, maxWidth:280, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{log.subject || '—'}</td>
                                <td><span style={{ fontFamily:"'DM Mono'", fontSize:10, fontWeight:700, color: meta.color }}>{meta.label}</span></td>
                                <td style={{ fontFamily:"'DM Mono'", fontSize:11, whiteSpace:'nowrap' }}>
                                  {log.sent_at ? new Date(log.sent_at).toLocaleString('en-AU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : '—'}
                                </td>
                              </motion.tr>
                            )
                          })}
                        </tbody>
                      </table>
                    )}
                  </motion.div>
                </>
              )}
            </>
          )}

        </motion.div>
      </AnimatePresence>

      {/* ── Call Detail Drawer ────────────────────────────────────────────────── */}
      <AnimatePresence>
        {callRow && (
          <>
            <motion.div
              className="drawer-overlay"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setCallRow(null)}
            />
            <motion.div
              className="drawer"
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 280 }}
            >
              <div className="drawer-header">
                <div>
                  <div className="drawer-title">Call Detail</div>
                  <div className="drawer-id">{callRow.call_id}</div>
                </div>
                <button className="drawer-close" onClick={() => setCallRow(null)}>✕</button>
              </div>

              <div className="drawer-badges">
                <span className={`tag ${callRow.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`}>{callRow.direction || '—'}</span>
                <span className={`flow-chip chip-${callRow.conversation_flow}`}>{callRow.conversation_flow || '—'} flow</span>
                {callRow.sentiment_trajectory && (
                  <span className={`traj traj-${callRow.sentiment_trajectory}`} style={{ fontSize: 13 }}>
                    {callRow.sentiment_trajectory === 'improving' ? '↑' : callRow.sentiment_trajectory === 'deteriorating' ? '↓' : '→'} {callRow.sentiment_trajectory}
                  </span>
                )}
                {callRow.quality_score != null && (() => {
                  const gc = GRADE_COLORS[callRow.quality_grade] || '#64748b'
                  return <span style={{ fontFamily:"'DM Mono'", fontSize:12, fontWeight:700, color:gc, background:gc+'18', border:`1px solid ${gc}40`, borderRadius:6, padding:'3px 9px' }}>Quality {callRow.quality_grade} · {callRow.quality_score}</span>
                })()}
              </div>

              {/* Audio Player */}
              <div className="drawer-section">
                <div className="drawer-section-label">Recording</div>
                <AudioPlayer callId={callRow.call_id} />
              </div>

              <div className="drawer-section">
                <div className="drawer-section-label">Engagement Score</div>
                <div style={{ display:'flex', alignItems:'center', gap:16 }}>
                  <div style={{ flex:1, background:'var(--surface2)', borderRadius:6, height:10, overflow:'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(parseFloat(callRow.engagement_score)||0,100)}%` }}
                      transition={{ duration: 0.8, ease: E }}
                      style={{ height:'100%', background:'linear-gradient(90deg, var(--accent2), var(--accent))', borderRadius:6 }}
                    />
                  </div>
                  <span style={{ fontFamily:"'DM Mono'", fontSize:22, fontWeight:800, color:'var(--accent)', minWidth:48 }}>
                    {parseFloat(callRow.engagement_score||0).toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="drawer-section">
                <div className="drawer-section-label">Talk Time Split</div>
                {(() => {
                  const a=parseFloat(callRow.agent_talk_time_sec)||0, c=parseFloat(callRow.customer_talk_time_sec)||0, s=parseFloat(callRow.total_silence_sec)||0, t=a+c+s||1
                  return (
                    <div className="talk-bars" style={{ gap:10 }}>
                      {[['Agent',a,'bar-agent','var(--accent2)'],['Customer',c,'bar-customer','var(--accent3)'],['Silence',s,'bar-silence','var(--muted)']].map(([label,sec,cls,color]) => (
                        <div className="talk-row" key={label}>
                          <div className="talk-meta">
                            <span className="talk-role" style={{ color }}>{label}</span>
                            <span className="talk-pct">{(sec/t*100).toFixed(1)}% · {sec.toFixed(1)}s</span>
                          </div>
                          <div className="bar-track">
                            <motion.div className={`bar-fill ${cls}`} initial={{ width: 0 }} animate={{ width: `${sec/t*100}%` }} transition={{ duration: 0.7, ease: E }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                })()}
              </div>

              <div className="drawer-section">
                <div className="drawer-section-label">Acoustic Signals</div>
                <div className="drawer-metrics">
                  {[
                    ['Avg Pitch',      `${parseFloat(callRow.avg_pitch_hz||0).toFixed(1)} Hz`,          'var(--accent2)'],
                    ['Agent Pitch',    `${parseFloat(callRow.agent_avg_pitch_hz||0).toFixed(1)} Hz`,    'var(--accent2)'],
                    ['Customer Pitch', `${parseFloat(callRow.customer_avg_pitch_hz||0).toFixed(1)} Hz`, 'var(--accent3)'],
                    ['Avg Energy',     parseFloat(callRow.avg_energy||0).toFixed(4),                    'var(--accent)'],
                  ].map(([label, value, color]) => (
                    <div className="drawer-metric-row" key={label}>
                      <span className="drawer-metric-label">{label}</span>
                      <span className="drawer-metric-value" style={{ color }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="drawer-section">
                <div className="drawer-section-label">Call Info</div>
                <div className="drawer-metrics">
                  {[
                    ['Date & Time', callRow.start_timestamp ? new Date(callRow.start_timestamp).toLocaleString('en-AU',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—', 'var(--muted2)'],
                    ['Duration',    callRow.duration_ms ? `${Math.round(callRow.duration_ms/1000)}s` : '—', 'var(--muted2)'],
                    ['Outcome',     callRow.call_successful===true ? 'Successful' : callRow.call_successful===false ? 'Unsuccessful' : '—', callRow.call_successful ? 'var(--accent)' : 'var(--warn)'],
                    ['Sentiment',   callRow.user_sentiment || '—', 'var(--muted2)'],
                  ].map(([label, value, color]) => (
                    <div className="drawer-metric-row" key={label}>
                      <span className="drawer-metric-label">{label}</span>
                      <span className="drawer-metric-value" style={{ color, fontSize:11 }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="drawer-section">
                <div className="drawer-section-label">Quality Signals</div>
                <div className="drawer-metrics">
                  {[
                    ['Silence Ratio', `${(parseFloat(callRow.silence_ratio||0)*100).toFixed(1)}%`, 'var(--accent3)'],
                    ['Interruptions', callRow.interruption_count??'—', 'var(--warn)'],
                    ['Hesitations',   callRow.hesitation_count??'—',   'var(--warn)'],
                    ['Total Turns',   callRow.total_turns??'—',         'var(--muted2)'],
                  ].map(([label, value, color]) => (
                    <div className="drawer-metric-row" key={label}>
                      <span className="drawer-metric-label">{label}</span>
                      <span className="drawer-metric-value" style={{ color }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="drawer-section">
                <div className="drawer-section-label">Call Summary</div>
                {callDetailLoad ? <div className="drawer-loading">Loading...</div>
                  : callDetail?.call_summary ? <div className="call-summary-box">{callDetail.call_summary}</div>
                  : <div style={{ color:'var(--muted)', fontSize:12 }}>No summary available</div>}
              </div>

              <div className="drawer-section" style={{ borderBottom:'none' }}>
                <div className="drawer-section-label">Transcript</div>
                {callDetailLoad ? <div className="drawer-loading">Loading transcript...</div>
                  : callDetail?.transcript?.length > 0 ? (
                    <div className="transcript-scroll">
                      {callDetail.transcript.map(t => (
                        <div key={t.index} className={`tx-turn ${t.role==='user' ? 'tx-turn-user' : ''}`}>
                          <span className={`tx-role-tag ${t.role==='agent' ? 'tx-role-agent' : 'tx-role-user'}`}>{t.role==='agent' ? 'Agent' : 'Customer'}</span>
                          <div className="tx-bubble">
                            {t.content}
                            {t.emotion && t.emotion !== 'unknown' && <EmotionBadge emotion={t.emotion} score={t.emotion_score} />}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : <div style={{ color:'var(--muted)', fontSize:12 }}>No transcript available</div>}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
