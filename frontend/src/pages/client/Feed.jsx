import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import api from '../../api/apiClient'
import MotionDrawer from '../../components/MotionDrawer'
import '../../App.css'

const POLL_SEC = 5

const GRADE_COLORS = { A:'#22c55e', B:'#6ee7b7', C:'#fbbf24', D:'#fb923c', F:'#ef4444' }
const EMOTION_COLORS = {
  happy:'#22c55e', sad:'#60a5fa', angry:'#ef4444',
  neutral:'#94a3b8', fearful:'#fb923c', disgusted:'#a3e635', surprised:'#c084fc',
}

const STATUS_META = {
  processing: { color:'#fbbf24', label:'PROCESSING', pulse:true  },
  complete:   { color:'#22c55e', label:'COMPLETE',   pulse:false },
  ingested:   { color:'#818cf8', label:'INGESTED',   pulse:false },
  failed:     { color:'#ef4444', label:'FAILED',     pulse:false },
}

const legendItem = {
  hidden: { opacity: 0, x: -8 },
  show:   { opacity: 1, x: 0, transition: { duration: 0.2, ease: 'easeOut' } },
}

function getStatus(c) {
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
  return new Date(ts).toLocaleDateString('en-AU', { day:'2-digit', month:'short' })
}

function EmotionBadge({ emotion, score }) {
  const color = EMOTION_COLORS[emotion]
  if (!color) return null
  return (
    <span className="emotion-badge" style={{ borderColor: color + '40', color }}>
      {emotion}
      {score != null && <span style={{ opacity:0.6, fontSize:9, marginLeft:3 }}>{Math.round(score*100)}%</span>}
    </span>
  )
}

export default function Feed() {
  const { user } = useAuth()
  const clientId = user?.client_id

  const [calls,        setCalls]        = useState([])
  const [newIds,       setNewIds]       = useState(new Set())
  const [lastSync,     setLastSync]     = useState(null)
  const [countdown,    setCountdown]    = useState(POLL_SEC)
  const [loading,      setLoading]      = useState(true)
  const [selected,     setSelected]     = useState(null)
  const [callDetail,   setCallDetail]   = useState(null)
  const [detailLoad,   setDetailLoad]   = useState(false)
  const seenRef = useRef(new Set())

  const fetchFeed = useCallback((silent = false) => {
    if (!clientId) return
    if (!silent) setLoading(true)
    api.get(`/feed/${clientId}`)
      .then(r => {
        const fresh = r.data.calls || []
        const freshNew = new Set()
        fresh.forEach(c => {
          if (!seenRef.current.has(c.call_id)) {
            freshNew.add(c.call_id)
            seenRef.current.add(c.call_id)
          }
        })
        setCalls(fresh)
        if (freshNew.size > 0) {
          setNewIds(freshNew)
          setTimeout(() => setNewIds(new Set()), 3500)
        }
        setLastSync(new Date())
        setCountdown(POLL_SEC)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [clientId])

  useEffect(() => { fetchFeed() }, [fetchFeed])

  useEffect(() => {
    const tick = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { fetchFeed(true); return POLL_SEC }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [fetchFeed])

  useEffect(() => {
    if (!selected) { setCallDetail(null); return }
    setDetailLoad(true)
    api.get(`/call/${selected.call_id}`)
      .then(r => setCallDetail(r.data))
      .catch(() => setCallDetail(null))
      .finally(() => setDetailLoad(false))
  }, [selected])

  const newCount = newIds.size

  return (
    <div>
      {loading && <div className="loading-bar" />}

      <div className="page-header">
        <div>
          <h2 className="page-title">Live Call Feed</h2>
          <div className="page-sub">{calls.length} most recent calls · auto-updates every {POLL_SEC}s</div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <AnimatePresence>
            {newCount > 0 && (
              <motion.span
                initial={{ opacity: 0, scale: 0.8, y: -6 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ type: 'spring', stiffness: 360, damping: 22 }}
                style={{ fontFamily:"'DM Mono'", fontSize:11, color:'#22c55e', background:'#22c55e15', border:'1px solid #22c55e40', borderRadius:6, padding:'4px 12px' }}
              >
                +{newCount} new
              </motion.span>
            )}
          </AnimatePresence>
          <div style={{ display:'flex', alignItems:'center', gap:8, fontFamily:"'DM Mono'", fontSize:10, letterSpacing:'0.06em' }}>
            <span style={{ width:7, height:7, borderRadius:'50%', background:'#22c55e', boxShadow:'0 0 6px #22c55e', display:'inline-block', animation:'pulse-green 2s infinite' }} />
            <span style={{ color:'#22c55e' }}>LIVE</span>
            <span style={{ color:'var(--muted)', marginLeft:8 }}>refresh in {countdown}s</span>
            {lastSync && (
              <span style={{ color:'var(--muted)', marginLeft:4 }}>
                · {lastSync.toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Status legend — staggered */}
      <motion.div
        style={{ display:'flex', gap:20, marginBottom:16, flexWrap:'wrap' }}
        initial="hidden"
        animate="show"
        variants={{ hidden:{}, show:{ transition:{ staggerChildren:0.07 } } }}
      >
        {Object.entries(STATUS_META).map(([key, meta]) => (
          <motion.div key={key} variants={legendItem} style={{ display:'flex', alignItems:'center', gap:6, fontFamily:"'DM Mono'", fontSize:10, color:'var(--muted)', letterSpacing:'0.06em' }}>
            <span style={{ width:7, height:7, borderRadius:'50%', background:meta.color, display:'inline-block' }} />
            {meta.label}
          </motion.div>
        ))}
      </motion.div>

      {/* Feed table */}
      <div className="card" style={{ padding:0, overflow:'hidden' }}>
        <div className="table-wrap" style={{ margin:0 }}>
          <table>
            <thead>
              <tr>
                <th style={{ width:16 }}></th>
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
              {calls.length === 0 ? (
                <tr><td colSpan={10} style={{ textAlign:'center', padding:32, color:'var(--muted)' }}>
                  {loading ? 'Loading...' : 'No calls yet — they will appear here as they arrive'}
                </td></tr>
              ) : calls.map(c => {
                const status = getStatus(c)
                const sm     = STATUS_META[status]
                const isNew  = newIds.has(c.call_id)
                const gc     = GRADE_COLORS[c.quality_grade]  || '#64748b'
                const ec     = EMOTION_COLORS[c.dominant_emotion] || '#64748b'
                return (
                  <motion.tr
                    key={c.call_id}
                    onClick={() => setSelected(c)}
                    style={{
                      cursor: 'pointer',
                      background: isNew ? '#22c55e08' : 'transparent',
                      borderLeft: isNew ? '2px solid #22c55e40' : '2px solid transparent',
                      transition: 'background 1s ease, border-color 1s ease',
                    }}
                    whileHover={{ backgroundColor: 'var(--hover-bg)' }}
                    transition={{ duration: 0.12 }}
                  >
                    <td style={{ paddingLeft:12 }}>
                      <span style={{
                        display:'inline-block', width:8, height:8, borderRadius:'50%',
                        background: sm.color, boxShadow:`0 0 5px ${sm.color}80`,
                        animation: sm.pulse ? 'pulse-green 1.2s infinite' : 'none',
                      }} />
                    </td>
                    <td>
                      <span style={{ fontFamily:"'DM Mono'", fontSize:10, letterSpacing:'0.06em', color:sm.color }}>
                        {sm.label}
                      </span>
                    </td>
                    <td style={{ fontFamily:"'DM Mono'", fontSize:11 }}>{c.call_id}</td>
                    <td>
                      {c.direction
                        ? <span className={`tag ${c.direction==='inbound'?'tag-green':'tag-purple'}`} style={{fontSize:10}}>{c.direction}</span>
                        : <span style={{color:'var(--muted)'}}>—</span>}
                    </td>
                    <td style={{ fontFamily:"'DM Mono'", fontSize:11, color:'var(--muted2)', whiteSpace:'nowrap' }}>
                      {timeAgo(c.start_timestamp)}
                    </td>
                    <td style={{ fontFamily:"'DM Mono'", fontSize:11, color:'var(--muted2)' }}>
                      {c.duration_ms ? `${Math.round(c.duration_ms/1000)}s` : '—'}
                    </td>
                    <td>
                      {c.quality_score != null
                        ? <span style={{ fontFamily:"'DM Mono'", fontSize:11, fontWeight:700, color:gc }}>
                            {c.quality_grade} <span style={{ opacity:0.6, fontWeight:400 }}>{c.quality_score}</span>
                          </span>
                        : <span style={{ color:'var(--muted)', fontSize:12 }}>—</span>}
                    </td>
                    <td>
                      {c.dominant_emotion && EMOTION_COLORS[c.dominant_emotion]
                        ? <span style={{ fontFamily:"'DM Mono'", fontSize:11, color:ec }}>{c.dominant_emotion}</span>
                        : <span style={{ color:'var(--muted)', fontSize:12 }}>—</span>}
                    </td>
                    <td>
                      {c.conversation_flow
                        ? <span className={`flow-chip chip-${c.conversation_flow}`}>{c.conversation_flow}</span>
                        : <span style={{ color:'var(--muted)', fontSize:12 }}>—</span>}
                    </td>
                    <td>
                      {c.call_successful===true  && <span className="tag tag-success" style={{fontSize:10}}>OK</span>}
                      {c.call_successful===false && <span className="tag tag-fail"    style={{fontSize:10}}>Failed</span>}
                      {c.call_successful==null   && <span style={{color:'var(--muted)',fontSize:12}}>—</span>}
                    </td>
                  </motion.tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Call detail drawer */}
      <MotionDrawer open={!!selected} onClose={() => setSelected(null)}>{() => <>
            <div className="drawer-header">
              <div>
                <div className="drawer-title">Call Detail</div>
                <div className="drawer-id">{selected.call_id}</div>
              </div>
              <button className="drawer-close" onClick={() => setSelected(null)}>✕</button>
            </div>

            <div className="drawer-badges">
              <span className={`tag ${selected.direction==='inbound'?'tag-green':'tag-purple'}`}>{selected.direction||'—'}</span>
              {selected.conversation_flow && (
                <span className={`flow-chip chip-${selected.conversation_flow}`}>{selected.conversation_flow} flow</span>
              )}
              {selected.sentiment_trajectory && (
                <span className={`traj traj-${selected.sentiment_trajectory}`} style={{fontSize:13}}>
                  {selected.sentiment_trajectory==='improving'?'↑':selected.sentiment_trajectory==='deteriorating'?'↓':'→'} {selected.sentiment_trajectory}
                </span>
              )}
              {selected.quality_score != null && (() => {
                const gc = GRADE_COLORS[selected.quality_grade]||'#64748b'
                return (
                  <span style={{fontFamily:"'DM Mono'",fontSize:12,fontWeight:700,color:gc,background:gc+'18',border:`1px solid ${gc}40`,borderRadius:6,padding:'3px 9px'}}>
                    Quality {selected.quality_grade} · {selected.quality_score}
                  </span>
                )
              })()}
            </div>

            <div className="drawer-section">
              <div className="drawer-section-label">Status</div>
              <div className="drawer-metrics">
                {[
                  { label:'Processing', value: selected.processing_status || '—', color:'var(--muted2)' },
                  { label:'When',       value: selected.start_timestamp ? new Date(selected.start_timestamp).toLocaleString('en-AU',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—', color:'var(--muted2)' },
                  { label:'Duration',   value: selected.duration_ms ? `${Math.round(selected.duration_ms/1000)}s` : '—', color:'var(--muted2)' },
                  { label:'Outcome',    value: selected.call_successful===true?'Successful':selected.call_successful===false?'Unsuccessful':'—', color:selected.call_successful?'var(--accent)':'var(--warn)' },
                  { label:'Sentiment',  value: selected.user_sentiment||'—', color:'var(--muted2)' },
                  { label:'Emotion',    value: selected.dominant_emotion||'—', color: EMOTION_COLORS[selected.dominant_emotion]||'var(--muted2)' },
                ].map(({ label, value, color }) => (
                  <div className="drawer-metric-row" key={label}>
                    <span className="drawer-metric-label">{label}</span>
                    <span className="drawer-metric-value" style={{color, fontSize:11}}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            {selected.engagement_score != null && (
              <div className="drawer-section">
                <div className="drawer-section-label">Engagement Score</div>
                <div style={{ display:'flex', alignItems:'center', gap:16 }}>
                  <div style={{ flex:1, background:'var(--surface2)', borderRadius:6, height:10, overflow:'hidden' }}>
                    <div style={{ width:`${Math.min(parseFloat(selected.engagement_score)||0,100)}%`, height:'100%', background:'linear-gradient(90deg,var(--accent2),var(--accent))', borderRadius:6 }}/>
                  </div>
                  <span style={{ fontFamily:"'DM Mono'", fontSize:20, fontWeight:800, color:'var(--accent)', minWidth:48 }}>
                    {parseFloat(selected.engagement_score).toFixed(1)}
                  </span>
                </div>
              </div>
            )}

            <div className="drawer-section">
              <div className="drawer-section-label">Call Summary</div>
              {detailLoad ? (
                <div className="drawer-loading">Loading...</div>
              ) : callDetail?.call_summary ? (
                <div className="call-summary-box">{callDetail.call_summary}</div>
              ) : (
                <div style={{color:'var(--muted)',fontSize:12}}>No summary available</div>
              )}
            </div>

            <div className="drawer-section" style={{borderBottom:'none'}}>
              <div className="drawer-section-label">Transcript</div>
              {detailLoad ? (
                <div className="drawer-loading">Loading transcript...</div>
              ) : callDetail?.transcript?.length > 0 ? (
                <div className="transcript-scroll">
                  {callDetail.transcript.map(t => (
                    <div key={t.index} className={`tx-turn ${t.role==='user'?'tx-turn-user':''}`}>
                      <span className={`tx-role-tag ${t.role==='agent'?'tx-role-agent':'tx-role-user'}`}>
                        {t.role==='agent'?'Agent':'Customer'}
                      </span>
                      <div className="tx-bubble">
                        {t.content}
                        {t.emotion && t.emotion!=='unknown' && (
                          <EmotionBadge emotion={t.emotion} score={t.emotion_score}/>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{color:'var(--muted)',fontSize:12}}>No transcript available</div>
              )}
            </div>
      </>}</MotionDrawer>
    </div>
  )
}
