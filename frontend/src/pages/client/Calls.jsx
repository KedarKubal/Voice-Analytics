import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { useClientData } from '../../hooks/useClientData'
import { useFilters } from '../../context/FilterContext'
import api from '../../api/apiClient'
import MotionDrawer from '../../components/MotionDrawer'
import AudioPlayer from '../../components/AudioPlayer'
import '../../App.css'

const TOPIC_COLORS = {
  booking:           '#6ee7b7',
  cancellation:      '#fb923c',
  complaint:         '#f87171',
  payment:           '#34d399',
  enquiry:           '#818cf8',
  technical_support: '#22d3ee',
  emergency:         '#ef4444',
  follow_up:         '#a78bfa',
  general:           '#64748b',
}

function TopicBadge({ topic }) {
  const color = TOPIC_COLORS[topic] || '#64748b'
  const label = topic?.replace('_', ' ') || '—'
  return (
    <span style={{
      fontFamily: "'DM Mono'", fontSize: 10, fontWeight: 600,
      color, background: color + '18', border: `1px solid ${color}40`,
      borderRadius: 5, padding: '2px 7px', whiteSpace: 'nowrap',
      textTransform: 'capitalize',
    }}>
      {label}
    </span>
  )
}

const EMOTION_META = {
  happy:      { color: '#22c55e' },
  sad:        { color: '#60a5fa' },
  angry:      { color: '#ef4444' },
  neutral:    { color: '#94a3b8' },
  fearful:    { color: '#fb923c' },
  disgusted:  { color: '#a3e635' },
  surprised:  { color: '#c084fc' },
}

function EmotionBadge({ emotion, score }) {
  const meta = EMOTION_META[emotion]
  if (!meta) return null
  return (
    <span className="emotion-badge" style={{ borderColor: meta.color + '40', color: meta.color }}>
      {emotion}
      {score != null && (
        <span style={{ opacity: 0.6, fontSize: 9, marginLeft: 3 }}>{Math.round(score * 100)}%</span>
      )}
    </span>
  )
}

const GRADE_COLORS = { A: '#22c55e', B: '#6ee7b7', C: '#fbbf24', D: '#fb923c', F: '#ef4444' }

const STATUS_META = {
  processing: { color: '#fbbf24', label: 'PROCESSING', pulse: true  },
  complete:   { color: '#22c55e', label: 'COMPLETE',   pulse: false },
  ingested:   { color: '#818cf8', label: 'INGESTED',   pulse: false },
  failed:     { color: '#ef4444', label: 'FAILED',     pulse: false },
}

function getLiveStatus(c) {
  if (c.processing_status === 'pending_audio') return 'processing'
  if (c.processing_status === 'failed')        return 'failed'
  if (c.quality_score != null)                 return 'complete'
  return 'ingested'
}

function timeAgo(ts) {
  if (!ts) return '—'
  const diff = Date.now() - ts
  if (diff < 30000)    return 'just now'
  if (diff < 3600000)  return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return new Date(ts).toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

const LIVE_POLL_SEC = 5

async function downloadCSV(clientId) {
  const res = await api.get(`/export/csv/${clientId}`, { responseType: 'blob' })
  const url  = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
  const a    = document.createElement('a')
  a.href     = url
  a.download = `heya_calls_${clientId}_${new Date().toISOString().slice(0,10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function openReport(clientId) {
  const res = await api.get(`/export/report/${clientId}`, { responseType: 'blob' })
  const url = URL.createObjectURL(new Blob([res.data], { type: 'text/html' }))
  window.open(url, '_blank')
}

export default function Calls() {
  const { insights, loading, clientId } = useClientData()
  const {
    dateFrom, setDateFrom, dateTo, setDateTo,
    filterFlow, setFilterFlow, filterDir, setFilterDir,
    filterTraj, setFilterTraj, filterTopic, setFilterTopic,
    filterAgent, setFilterAgent,
    clearFilters,
  } = useFilters()

  // Derive unique agent names from the loaded insights (dynamic — works for any client)
  const agentOptions = useMemo(() => (
    [...new Set(insights.map(r => r.agent_name).filter(Boolean))].sort()
  ), [insights])
  const [viewMode,      setViewMode]      = useState('analytics')
  const [search,        setSearch]        = useState('')
  const [selected,      setSelected]      = useState(null)
  const [callDetail,    setCallDetail]    = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Live feed state
  const [liveCalls,     setLiveCalls]     = useState([])
  const [liveNewIds,    setLiveNewIds]    = useState(new Set())
  const [liveLastSync,  setLiveLastSync]  = useState(null)
  const [liveCountdown, setLiveCountdown] = useState(LIVE_POLL_SEC)
  const [liveLoading,   setLiveLoading]   = useState(false)
  const liveSeenRef = useRef(new Set())

  const fetchLive = useCallback((silent = false) => {
    if (!clientId) return
    if (!silent) setLiveLoading(true)
    api.get(`/feed/${clientId}`)
      .then(r => {
        const fresh = r.data.calls || []
        const freshNew = new Set()
        fresh.forEach(c => {
          if (!liveSeenRef.current.has(c.call_id)) {
            freshNew.add(c.call_id)
            liveSeenRef.current.add(c.call_id)
          }
        })
        setLiveCalls(fresh)
        if (freshNew.size > 0) {
          setLiveNewIds(freshNew)
          setTimeout(() => setLiveNewIds(new Set()), 3500)
        }
        setLiveLastSync(new Date())
        setLiveCountdown(LIVE_POLL_SEC)
      })
      .catch(console.error)
      .finally(() => setLiveLoading(false))
  }, [clientId])

  useEffect(() => {
    if (viewMode === 'live') fetchLive()
  }, [viewMode, fetchLive])

  useEffect(() => {
    if (viewMode !== 'live') return
    const tick = setInterval(() => {
      setLiveCountdown(c => {
        if (c <= 1) { fetchLive(true); return LIVE_POLL_SEC }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [viewMode, fetchLive])

  useEffect(() => {
    if (!selected || !clientId) { setCallDetail(null); return }
    setDetailLoading(true)
    api.get(`/call/${selected.call_id}`, { headers: { 'x-client-id': clientId } })
      .then(r => setCallDetail(r.data))
      .catch(() => setCallDetail(null))
      .finally(() => setDetailLoading(false))
  }, [selected, clientId])

  const filtered = insights.filter(r => {
    if (search && !r.call_id.toLowerCase().includes(search.toLowerCase())) return false
    if (filterFlow  !== 'all' && r.conversation_flow     !== filterFlow)  return false
    if (filterDir   !== 'all' && r.direction             !== filterDir)   return false
    if (filterTraj  !== 'all' && r.sentiment_trajectory  !== filterTraj)  return false
    if (filterTopic !== 'all' && r.topic                 !== filterTopic) return false
    if (filterAgent !== 'all' && r.agent_name            !== filterAgent) return false
    if (dateFrom && r.start_timestamp) {
      const d = new Date(r.start_timestamp)
      const ld = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
      if (ld < dateFrom) return false
    }
    if (dateTo && r.start_timestamp) {
      const d = new Date(r.start_timestamp)
      const ld = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
      if (ld > dateTo) return false
    }
    return true
  })

  const sorted = [...filtered].sort((a, b) =>
    (b.start_timestamp || 0) - (a.start_timestamp || 0)
  )

  const filtersActive = search || filterFlow !== 'all' || filterDir !== 'all' ||
    filterTraj !== 'all' || filterTopic !== 'all' || filterAgent !== 'all' || dateFrom || dateTo

  return (
    <div>
      {loading && <div className="loading-bar" />}

      <div className="page-header">
        <div>
          <h2 className="page-title">Calls</h2>
          <div className="page-sub">
            {viewMode === 'live'
              ? `${liveCalls.length} most recent calls · auto-updates every ${LIVE_POLL_SEC}s`
              : `${filtered.length} of ${insights.length} calls shown`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* View mode toggle */}
          <div style={{ display: 'flex', background: 'var(--surface2)', borderRadius: 8, padding: 3, gap: 2 }}>
            {[{ id: 'analytics', label: 'Analytics' }, { id: 'live', label: '● Live' }].map(({ id, label }) => (
              <motion.button key={id} onClick={() => setViewMode(id)}
                style={{
                  fontFamily: "'DM Mono'", fontSize: 11, letterSpacing: '0.04em',
                  padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  background: viewMode === id ? 'var(--surface3, #2a2a3a)' : 'transparent',
                  color: viewMode === id ? (id === 'live' ? '#22c55e' : 'var(--text)') : 'var(--muted)',
                  transition: 'all 0.15s ease',
                }}
                whileTap={{ scale: 0.95 }}>
                {label}
              </motion.button>
            ))}
          </div>
          {viewMode === 'analytics' && <>
            <motion.button className="export-btn" onClick={() => downloadCSV(clientId)}
              whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 400, damping: 20 }}>
              ↓ Export CSV
            </motion.button>
            <motion.button className="export-btn export-btn-primary" onClick={() => openReport(clientId)}
              whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 400, damping: 20 }}>
              ↗ PDF Report
            </motion.button>
          </>}
          {viewMode === 'live' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: "'DM Mono'", fontSize: 10, letterSpacing: '0.06em' }}>
              <AnimatePresence>
                {liveNewIds.size > 0 && (
                  <motion.span
                    initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
                    style={{ color: '#22c55e', background: '#22c55e15', border: '1px solid #22c55e40', borderRadius: 6, padding: '3px 10px' }}>
                    +{liveNewIds.size} new
                  </motion.span>
                )}
              </AnimatePresence>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 6px #22c55e', display: 'inline-block', animation: 'pulse-green 2s infinite' }} />
              <span style={{ color: '#22c55e' }}>LIVE</span>
              <span style={{ color: 'var(--muted)', marginLeft: 6 }}>refresh in {liveCountdown}s</span>
              {liveLastSync && <span style={{ color: 'var(--muted)' }}>· {liveLastSync.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>}
            </div>
          )}
        </div>
      </div>

      {viewMode === 'analytics' && (<>
      {/* Filter bar */}
      <div className="filter-bar">
        <input
          className="filter-search"
          placeholder="Search call ID..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="filter-select" value={filterFlow} onChange={e => setFilterFlow(e.target.value)}>
          <option value="all">All flows</option>
          <option value="smooth">Smooth</option>
          <option value="moderate">Moderate</option>
          <option value="poor">Poor</option>
        </select>
        <select className="filter-select" value={filterDir} onChange={e => setFilterDir(e.target.value)}>
          <option value="all">All directions</option>
          <option value="inbound">Inbound</option>
          <option value="outbound">Outbound</option>
        </select>
        <select className="filter-select" value={filterTraj} onChange={e => setFilterTraj(e.target.value)}>
          <option value="all">All trajectories</option>
          <option value="improving">↑ Improving</option>
          <option value="stable">→ Stable</option>
          <option value="deteriorating">↓ Deteriorating</option>
        </select>
        <select className="filter-select" value={filterTopic} onChange={e => setFilterTopic(e.target.value)}>
          <option value="all">All topics</option>
          <option value="booking">Booking</option>
          <option value="cancellation">Cancellation</option>
          <option value="complaint">Complaint</option>
          <option value="payment">Payment</option>
          <option value="enquiry">Enquiry</option>
          <option value="technical_support">Technical Support</option>
          <option value="emergency">Emergency</option>
          <option value="follow_up">Follow Up</option>
          <option value="general">General</option>
        </select>
        {agentOptions.length > 0 && (
          <select className="filter-select" value={filterAgent} onChange={e => setFilterAgent(e.target.value)}>
            <option value="all">All agents</option>
            {agentOptions.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        )}
        <div className="filter-date-group">
          <label className="filter-date-label">From</label>
          <input
            type="date"
            className="filter-date"
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
          />
        </div>
        <div className="filter-date-group">
          <label className="filter-date-label">To</label>
          <input
            type="date"
            className="filter-date"
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
          />
        </div>
        {(search || filterFlow !== 'all' || filterDir !== 'all' || filterTraj !== 'all' || filterTopic !== 'all' || filterAgent !== 'all' || dateFrom || dateTo) && (
          <motion.button className="filter-clear" onClick={() => { setSearch(''); clearFilters() }}
            whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
            transition={{ type: 'spring', stiffness: 400, damping: 22 }}>
            Clear all
          </motion.button>
        )}
      </div>

      {/* Filter charts — live stats for the filtered subset */}
      <AnimatePresence mode="wait">
        <motion.div
          key={filtered.length + String(filtersActive)}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
        >
          {/* Filter summary strip */}
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: 12 }}>
            <div style={{ fontFamily:"'DM Mono'", fontSize: 11, color: 'var(--muted)', letterSpacing: '0.04em' }}>
              {filtersActive
                ? <><span style={{ color:'var(--accent2)', fontWeight:700 }}>{filtered.length}</span> of {insights.length} calls · filtered view</>
                : <><span style={{ color:'var(--muted2)', fontWeight:700 }}>{filtered.length}</span> calls · all data</>
              }
            </div>
            {filtersActive && (
              <span style={{ fontFamily:"'DM Mono'", fontSize:10, color:'var(--accent3)', background:'#fb923c12', border:'1px solid #fb923c30', borderRadius:5, padding:'2px 9px' }}>
                FILTERED
              </span>
            )}
          </div>

        </motion.div>
      </AnimatePresence>

      {/* Call table */}
      <div className="card" style={{ padding: 0, overflow: 'clip' }}>
        <div className="table-wrap" style={{ margin: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Call ID</th>
                <th>Agent</th>
                <th>Date &amp; Time</th>
                <th>Duration</th>
                <th>Direction</th>
                <th>Flow</th>
                <th>Trajectory</th>
                <th>Topic</th>
                <th>Engagement</th>
                <th>Silence</th>
                <th>Interruptions</th>
                <th>Quality</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 ? (
                <tr><td colSpan={13} style={{ textAlign: 'center', padding: 24, color: 'var(--muted)' }}>
                  {loading ? 'Loading...' : 'No calls match your filters'}
                </td></tr>
              ) : sorted.map(r => {
                const gradeColor = { A: '#22c55e', B: '#6ee7b7', C: '#fbbf24', D: '#fb923c', F: '#ef4444' }[r.quality_grade] || '#64748b'
                return (
                <motion.tr key={r.call_id} onClick={() => setSelected(r)}
                  style={{ cursor: 'pointer' }}
                  whileHover={{ backgroundColor: 'var(--hover-bg)' }}
                  transition={{ duration: 0.12 }}>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{r.call_id}</td>
                  <td>
                    {r.agent_name
                      ? <span style={{
                          fontFamily: "'DM Mono'", fontSize: 11, fontWeight: 600,
                          color: 'var(--accent2)',
                          background: '#818cf812',
                          border: '1px solid #818cf830',
                          borderRadius: 5, padding: '2px 8px', whiteSpace: 'nowrap',
                        }}>{r.agent_name}</span>
                      : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                  </td>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11, whiteSpace: 'nowrap' }}>
                    {r.start_timestamp
                      ? new Date(r.start_timestamp).toLocaleString('en-AU', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' })
                      : '—'}
                  </td>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>
                    {r.duration_ms ? `${Math.round(r.duration_ms / 1000)}s` : '—'}
                  </td>
                  <td>
                    <span className={`tag ${r.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`} style={{ fontSize: 10 }}>
                      {r.direction || '—'}
                    </span>
                  </td>
                  <td><span className={`flow-chip chip-${r.conversation_flow}`}>{r.conversation_flow || '—'}</span></td>
                  <td>
                    <span className={`traj traj-${r.sentiment_trajectory}`}>
                      {r.sentiment_trajectory === 'improving' ? '↑' : r.sentiment_trajectory === 'deteriorating' ? '↓' : r.sentiment_trajectory === 'stable' ? '→' : '—'}
                      {r.sentiment_trajectory ? ` ${r.sentiment_trajectory}` : ''}
                    </span>
                  </td>
                  <td>
                    {r.topic
                      ? <TopicBadge topic={r.topic} />
                      : <span style={{ color:'var(--muted)', fontSize:12 }}>—</span>}
                  </td>
                  <td>
                    <div className="eng-bar">
                      <div className="eng-mini">
                        <div className="eng-mini-fill" style={{ width: `${Math.min(parseFloat(r.engagement_score) || 0, 100)}%` }} />
                      </div>
                      <span style={{ fontFamily: "'DM Mono'", fontSize: 12 }}>{parseFloat(r.engagement_score || 0).toFixed(1)}</span>
                    </div>
                  </td>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 12 }}>{(parseFloat(r.silence_ratio || 0) * 100).toFixed(1)}%</td>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 12 }}>{r.interruption_count ?? '—'}</td>
                  <td>
                    {r.quality_score != null ? (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontFamily: "'DM Mono'", fontSize: 11, fontWeight: 700,
                        color: gradeColor,
                        background: gradeColor + '18',
                        border: `1px solid ${gradeColor}40`,
                        borderRadius: 6, padding: '2px 7px',
                      }}>
                        {r.quality_grade} <span style={{ opacity: 0.7, fontWeight: 400 }}>{r.quality_score}</span>
                      </span>
                    ) : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                  </td>
                  <td>
                    {r.call_successful === true  && <span className="tag tag-success" style={{ fontSize: 10 }}>Successful</span>}
                    {r.call_successful === false && <span className="tag tag-fail"    style={{ fontSize: 10 }}>Unsuccessful</span>}
                    {r.call_successful == null   && <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                  </td>
                </motion.tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      </>)}

      {/* Live Feed view */}
      {viewMode === 'live' && (
        <>
          {liveLoading && <div className="loading-bar" />}
          <motion.div
            style={{ display: 'flex', gap: 20, marginBottom: 16, flexWrap: 'wrap' }}
            initial="hidden" animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
          >
            {Object.entries(STATUS_META).map(([key, meta]) => (
              <motion.div key={key}
                variants={{ hidden: { opacity: 0, x: -8 }, show: { opacity: 1, x: 0, transition: { duration: 0.2 } } }}
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', letterSpacing: '0.06em' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: meta.color, display: 'inline-block' }} />
                {meta.label}
              </motion.div>
            ))}
          </motion.div>
          <div className="card" style={{ padding: 0, overflow: 'clip' }}>
            <div className="table-wrap" style={{ margin: 0 }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 16 }}></th>
                    <th>STATUS</th>
                    <th>CALL ID</th>
                    <th>DIRECTION</th>
                    <th>WHEN</th>
                    <th>DURATION</th>
                    <th>QUALITY</th>
                    <th>EMOTION</th>
                    <th>FLOW</th>
                    <th>OUTCOME</th>
                  </tr>
                </thead>
                <tbody>
                  {liveCalls.length === 0 ? (
                    <tr><td colSpan={10} style={{ textAlign: 'center', padding: 32, color: 'var(--muted)' }}>
                      {liveLoading ? 'Loading...' : 'No calls yet — they will appear here as they arrive'}
                    </td></tr>
                  ) : liveCalls.map(c => {
                    const status = getLiveStatus(c)
                    const sm     = STATUS_META[status]
                    const isNew  = liveNewIds.has(c.call_id)
                    const gc     = GRADE_COLORS[c.quality_grade] || '#64748b'
                    const em     = EMOTION_META[c.dominant_emotion]
                    return (
                      <motion.tr key={c.call_id} onClick={() => setSelected(c)}
                        style={{
                          cursor: 'pointer',
                          background: isNew ? '#22c55e08' : 'transparent',
                          borderLeft: isNew ? '2px solid #22c55e40' : '2px solid transparent',
                          transition: 'background 1s ease, border-color 1s ease',
                        }}
                        whileHover={{ backgroundColor: 'var(--hover-bg)' }}
                        transition={{ duration: 0.12 }}>
                        <td style={{ paddingLeft: 12 }}>
                          <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: sm.color, boxShadow: `0 0 5px ${sm.color}80`, animation: sm.pulse ? 'pulse-green 1.2s infinite' : 'none' }} />
                        </td>
                        <td><span style={{ fontFamily: "'DM Mono'", fontSize: 10, letterSpacing: '0.06em', color: sm.color }}>{sm.label}</span></td>
                        <td style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{c.call_id}</td>
                        <td>
                          {c.direction
                            ? <span className={`tag ${c.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`} style={{ fontSize: 10 }}>{c.direction}</span>
                            : <span style={{ color: 'var(--muted)' }}>—</span>}
                        </td>
                        <td style={{ fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted2)', whiteSpace: 'nowrap' }}>{timeAgo(c.start_timestamp)}</td>
                        <td style={{ fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted2)' }}>{c.duration_ms ? `${Math.round(c.duration_ms / 1000)}s` : '—'}</td>
                        <td>
                          {c.quality_score != null
                            ? <span style={{ fontFamily: "'DM Mono'", fontSize: 11, fontWeight: 700, color: gc }}>{c.quality_grade} <span style={{ opacity: 0.6, fontWeight: 400 }}>{c.quality_score}</span></span>
                            : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                        </td>
                        <td>
                          {em
                            ? <span style={{ fontFamily: "'DM Mono'", fontSize: 11, color: em.color }}>{c.dominant_emotion}</span>
                            : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                        </td>
                        <td>
                          {c.conversation_flow
                            ? <span className={`flow-chip chip-${c.conversation_flow}`}>{c.conversation_flow}</span>
                            : <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                        </td>
                        <td>
                          {c.call_successful === true  && <span className="tag tag-success" style={{ fontSize: 10 }}>OK</span>}
                          {c.call_successful === false && <span className="tag tag-fail"    style={{ fontSize: 10 }}>Failed</span>}
                          {c.call_successful == null   && <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                        </td>
                      </motion.tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Detail Drawer */}
      <MotionDrawer open={!!selected} onClose={() => setSelected(null)}>{() => <>
            <div className="drawer-header">
              <div>
                <div className="drawer-title">Call Detail</div>
                <div className="drawer-id">{selected.call_id}</div>
              </div>
              <button className="drawer-close" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div className="drawer-badges">
              <span className={`tag ${selected.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`}>{selected.direction || '—'}</span>
              <span className={`flow-chip chip-${selected.conversation_flow}`}>{selected.conversation_flow || '—'} flow</span>
              {selected.sentiment_trajectory && (
                <span className={`traj traj-${selected.sentiment_trajectory}`} style={{ fontSize: 13 }}>
                  {selected.sentiment_trajectory === 'improving' ? '↑' : selected.sentiment_trajectory === 'deteriorating' ? '↓' : '→'} {selected.sentiment_trajectory}
                </span>
              )}
              {selected.quality_score != null && (() => {
                const gc = { A: '#22c55e', B: '#6ee7b7', C: '#fbbf24', D: '#fb923c', F: '#ef4444' }[selected.quality_grade] || '#64748b'
                return (
                  <span style={{ fontFamily:"'DM Mono'", fontSize:12, fontWeight:700, color:gc, background:gc+'18', border:`1px solid ${gc}40`, borderRadius:6, padding:'3px 9px' }}>
                    Quality {selected.quality_grade} · {selected.quality_score}
                  </span>
                )
              })()}
            </div>
            <div className="drawer-section">
              <div className="drawer-section-label">Engagement Score</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ flex: 1, background: 'var(--surface2)', borderRadius: 6, height: 10, overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(parseFloat(selected.engagement_score) || 0, 100)}%`, height: '100%', background: 'linear-gradient(90deg, var(--accent2), var(--accent))', borderRadius: 6 }} />
                </div>
                <span style={{ fontFamily: "'DM Mono'", fontSize: 20, fontWeight: 800, color: 'var(--accent)', minWidth: 48 }}>
                  {parseFloat(selected.engagement_score || 0).toFixed(1)}
                </span>
              </div>
            </div>
            <div className="drawer-section">
              <div className="drawer-section-label">Talk Time Split</div>
              {(() => {
                const a = parseFloat(selected.agent_talk_time_sec) || 0
                const c = parseFloat(selected.customer_talk_time_sec) || 0
                const s = parseFloat(selected.total_silence_sec) || 0
                const t = a + c + s || 1
                return (
                  <div className="talk-bars" style={{ gap: 10 }}>
                    {[
                      { label: 'Agent', sec: a, pct: a/t*100, cls: 'bar-agent', color: 'var(--accent2)' },
                      { label: 'Customer', sec: c, pct: c/t*100, cls: 'bar-customer', color: 'var(--accent3)' },
                      { label: 'Silence', sec: s, pct: s/t*100, cls: 'bar-silence', color: 'var(--muted)' },
                    ].map(({ label, sec, pct, cls, color }) => (
                      <div className="talk-row" key={label}>
                        <div className="talk-meta">
                          <span className="talk-role" style={{ color }}>{label}</span>
                          <span className="talk-pct">{pct.toFixed(1)}% · {sec.toFixed(1)}s</span>
                        </div>
                        <div className="bar-track"><div className={`bar-fill ${cls}`} style={{ width: `${pct}%` }} /></div>
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
                  { label: 'Avg Pitch',      value: `${parseFloat(selected.avg_pitch_hz || 0).toFixed(1)} Hz`,          color: 'var(--accent2)' },
                  { label: 'Agent Pitch',    value: `${parseFloat(selected.agent_avg_pitch_hz || 0).toFixed(1)} Hz`,    color: 'var(--accent2)' },
                  { label: 'Customer Pitch', value: `${parseFloat(selected.customer_avg_pitch_hz || 0).toFixed(1)} Hz`, color: 'var(--accent3)' },
                  { label: 'Avg Energy',     value: parseFloat(selected.avg_energy || 0).toFixed(4),                    color: 'var(--accent)' },
                ].map(({ label, value, color }) => (
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
                <div className="drawer-metric-row">
                  <span className="drawer-metric-label">Date &amp; Time</span>
                  <span className="drawer-metric-value" style={{ color: 'var(--muted2)', fontSize: 11 }}>
                    {selected.start_timestamp
                      ? new Date(selected.start_timestamp).toLocaleString('en-AU', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' })
                      : '—'}
                  </span>
                </div>
                <div className="drawer-metric-row">
                  <span className="drawer-metric-label">Duration</span>
                  <span className="drawer-metric-value" style={{ color: 'var(--muted2)' }}>
                    {selected.duration_ms ? `${Math.round(selected.duration_ms / 1000)}s` : '—'}
                  </span>
                </div>
                <div className="drawer-metric-row">
                  <span className="drawer-metric-label">Outcome</span>
                  <span className="drawer-metric-value" style={{ color: selected.call_successful ? 'var(--accent)' : 'var(--warn)' }}>
                    {selected.call_successful === true ? 'Successful' : selected.call_successful === false ? 'Unsuccessful' : '—'}
                  </span>
                </div>
                <div className="drawer-metric-row">
                  <span className="drawer-metric-label">Sentiment</span>
                  <span className="drawer-metric-value" style={{ color: 'var(--muted2)' }}>
                    {selected.user_sentiment || '—'}
                  </span>
                </div>
              </div>
            </div>
            <div className="drawer-section">
              <div className="drawer-section-label">Quality</div>
              <div className="drawer-metrics">
                {[
                  { label: 'Silence Ratio',  value: `${(parseFloat(selected.silence_ratio || 0)*100).toFixed(1)}%`, color: 'var(--accent3)' },
                  { label: 'Interruptions',  value: selected.interruption_count ?? '—',                              color: 'var(--warn)' },
                  { label: 'Hesitations',    value: selected.hesitation_count ?? '—',                                color: 'var(--warn)' },
                  { label: 'Total Turns',    value: selected.total_turns ?? '—',                                     color: 'var(--muted2)' },
                ].map(({ label, value, color }) => (
                  <div className="drawer-metric-row" key={label}>
                    <span className="drawer-metric-label">{label}</span>
                    <span className="drawer-metric-value" style={{ color }}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Audio Player */}
            <div className="drawer-section">
              <div className="drawer-section-label">Recording</div>
              <AudioPlayer callId={selected.call_id} />
            </div>

            {/* Call Summary */}
            <div className="drawer-section">
              <div className="drawer-section-label">Call Summary</div>
              {detailLoading ? (
                <div className="drawer-loading">Loading summary...</div>
              ) : callDetail?.call_summary ? (
                <div className="call-summary-box">{callDetail.call_summary}</div>
              ) : (
                <div style={{ color: 'var(--muted)', fontSize: 12 }}>No summary available</div>
              )}
            </div>

            {/* Transcript */}
            <div className="drawer-section" style={{ borderBottom: 'none' }}>
              <div className="drawer-section-label">Transcript</div>
              {detailLoading ? (
                <div className="drawer-loading">Loading transcript...</div>
              ) : callDetail?.transcript?.length > 0 ? (
                <div className="transcript-scroll">
                  {callDetail.transcript.map(t => (
                    <div key={t.index} className={`tx-turn ${t.role === 'user' ? 'tx-turn-user' : ''}`}>
                      <span className={`tx-role-tag ${t.role === 'agent' ? 'tx-role-agent' : 'tx-role-user'}`}>
                        {t.role === 'agent' ? 'Agent' : 'Customer'}
                      </span>
                      <div className="tx-bubble">
                        {t.content}
                        {t.emotion && t.emotion !== 'unknown' && (
                          <EmotionBadge emotion={t.emotion} score={t.emotion_score} />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: 'var(--muted)', fontSize: 12 }}>No transcript available</div>
              )}
            </div>
      </>}</MotionDrawer>
    </div>
  )
}
