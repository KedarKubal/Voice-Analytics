import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import api from '../../api/apiClient'
import MotionDrawer from '../../components/MotionDrawer'
import '../../App.css'

const pillItem = {
  hidden: { opacity: 0, scale: 0.85, y: 6 },
  show:   { opacity: 1, scale: 1,    y: 0, transition: { type: 'spring', stiffness: 340, damping: 22 } },
}
const resultItem = {
  hidden: { opacity: 0, y: 18 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
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

const SUGGESTIONS = [
  'cancellation', 'appointment', 'booking', 'complaint',
  'refund', 'emergency', 'payment', 'callback',
]

function useDebouncedValue(value, delay = 350) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function Search() {
  const { user }  = useAuth()
  const navigate  = useNavigate()
  const inputRef  = useRef(null)

  const [query,    setQuery]    = useState('')
  const [results,  setResults]  = useState(null)   // null = never searched
  const [loading,  setLoading]  = useState(false)
  const [selected, setSelected] = useState(null)
  const [callDetail, setCallDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const debounced = useDebouncedValue(query)

  // Auto-search when debounced query changes
  useEffect(() => {
    if (!debounced || debounced.trim().length < 2) {
      setResults(null)
      return
    }
    setLoading(true)
    api.get('/search', { params: { q: debounced.trim(), limit: 20 } })
      .then(r => setResults(r.data))
      .catch(() => setResults({ query: debounced, total: 0, results: [] }))
      .finally(() => setLoading(false))
  }, [debounced])

  // Load call detail when a result is selected
  useEffect(() => {
    if (!selected || !user?.client_id) { setCallDetail(null); return }
    setDetailLoading(true)
    api.get(`/call/${selected.call_id}`)
      .then(r => setCallDetail(r.data))
      .catch(() => setCallDetail(null))
      .finally(() => setDetailLoading(false))
  }, [selected, user?.client_id])

  const dismiss = useCallback(() => setSelected(null), [])

  function handleSuggestion(s) {
    setQuery(s)
    inputRef.current?.focus()
  }

  return (
    <div>
      {/* Search bar */}
      <div className="search-hero">
        <h2 className="page-title" style={{ marginBottom: 8 }}>Search Transcripts</h2>
        <div className="page-sub" style={{ marginBottom: 24 }}>
          Find any word or phrase spoken across all calls
        </div>
        <div className="search-bar-wrap">
          <span className="search-icon">⌕</span>
          <input
            ref={inputRef}
            className="search-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="e.g. cancellation, booking, refund..."
            autoFocus
          />
          {loading && <span className="search-spinner" />}
          {query && (
            <button className="search-clear" onClick={() => { setQuery(''); setResults(null) }}>✕</button>
          )}
        </div>

        {/* Suggestion pills — shown before first search */}
        <AnimatePresence>
          {!results && !loading && (
            <motion.div
              className="search-suggestions"
              initial="hidden"
              animate="show"
              exit={{ opacity: 0 }}
              variants={{ hidden:{}, show:{ transition:{ staggerChildren:0.06 } } }}
            >
              {SUGGESTIONS.map(s => (
                <motion.span key={s} className="pill" variants={pillItem}
                  whileHover={{ scale: 1.07, y: -2 }} whileTap={{ scale: 0.93 }}
                  onClick={() => handleSuggestion(s)}>{s}</motion.span>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* RAG tip — shown before first search */}
        <AnimatePresence>
          {!results && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ delay: 0.3, duration: 0.3 }}
              style={{
                marginTop: 20, padding: '10px 16px',
                background: 'rgba(129, 140, 248, 0.06)',
                border: '1px solid rgba(129, 140, 248, 0.2)',
                borderRadius: 10, display: 'flex', alignItems: 'center', gap: 10,
                fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)',
              }}>
              <span style={{ fontSize: 14 }}>💡</span>
              <span>
                Tip: For complex questions like "which calls had frustrated customers?" try{' '}
                <a
                  href="/dashboard/ask"
                  onClick={e => { e.preventDefault(); navigate('/dashboard/ask') }}
                  style={{ color: 'var(--accent2)', fontWeight: 600, textDecoration: 'none', cursor: 'pointer' }}>
                  Ask Your Data →
                </a>
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Results count */}
      {results && (
        <div className="search-meta">
          {results.total === 0
            ? `No calls matched "${results.query}"`
            : `${results.total} call${results.total !== 1 ? 's' : ''} matched "${results.query}"`}
        </div>
      )}

      {/* Result cards */}
      <AnimatePresence>
        {results?.results?.length > 0 && (
          <motion.div
            className="search-results"
            initial="hidden"
            animate="show"
            variants={{ hidden:{}, show:{ transition:{ staggerChildren:0.07 } } }}
          >
            {results.results.map(r => (
              <motion.div
                key={r.call_id}
                className={`search-card ${selected?.call_id === r.call_id ? 'search-card-active' : ''}`}
                onClick={() => setSelected(r)}
                variants={resultItem}
                whileHover={{ y: -2, transition: { duration: 0.15 } }}
              >
              {/* Card header */}
              <div className="search-card-header">
                <div className="search-card-left">
                  <span className="search-call-id">{r.call_id}</span>
                  <div className="search-card-tags">
                    {r.direction && (
                      <span className={`tag ${r.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`}
                        style={{ fontSize: 10 }}>{r.direction}</span>
                    )}
                    {r.conversation_flow && (
                      <span className={`flow-chip chip-${r.conversation_flow}`}>{r.conversation_flow}</span>
                    )}
                    {r.user_sentiment && (
                      <span className="tag tag-purple" style={{ fontSize: 10 }}>{r.user_sentiment}</span>
                    )}
                    {r.call_successful === true  && <span className="tag tag-success" style={{ fontSize: 10 }}>Successful</span>}
                    {r.call_successful === false && <span className="tag tag-fail"    style={{ fontSize: 10 }}>Unsuccessful</span>}
                  </div>
                </div>
                <div className="search-card-right">
                  {r.engagement_score != null && (
                    <span className="search-engagement">
                      {r.engagement_score.toFixed(1)} <span style={{ color: 'var(--muted)', fontSize: 10 }}>eng</span>
                    </span>
                  )}
                  <span className="search-match-count">
                    {r.match_count > 0 ? `${r.match_count} match${r.match_count !== 1 ? 'es' : ''}` : 'summary match'}
                  </span>
                  {r.start_timestamp && (
                    <span className="search-date">
                      {new Date(r.start_timestamp).toLocaleDateString('en-AU', { day:'2-digit', month:'short', year:'numeric' })}
                    </span>
                  )}
                </div>
              </div>

              {/* Highlighted snippets */}
              <div className="search-snippets">
                {r.snippets.map((snip, i) => (
                  <div
                    key={i}
                    className="search-snippet"
                    dangerouslySetInnerHTML={{ __html: `"…${snip}…"` }}
                  />
                ))}
              </div>

              <div className="search-card-footer">
                Click to view full transcript →
              </div>
            </motion.div>
          ))}
        </motion.div>
        )}
      </AnimatePresence>

      {/* Empty state */}
      <AnimatePresence>
        {results?.total === 0 && (
          <motion.div
            className="search-empty"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.28, ease: 'easeOut' }}
          >
            <div className="search-empty-icon">⌕</div>
            <div className="search-empty-title">No matches found</div>
            <div className="search-empty-sub">
              Try a different word or phrase. Search looks through spoken words in every call transcript.
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Call detail drawer */}
      <MotionDrawer open={!!selected} onClose={dismiss}>{() => <>
            <div className="drawer-header">
              <div>
                <div className="drawer-title">Call Detail</div>
                <div className="drawer-id">{selected.call_id}</div>
              </div>
              <button className="drawer-close" onClick={dismiss}>✕</button>
            </div>

            <div className="drawer-badges">
              {selected.direction && (
                <span className={`tag ${selected.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`}>
                  {selected.direction}
                </span>
              )}
              {selected.conversation_flow && (
                <span className={`flow-chip chip-${selected.conversation_flow}`}>
                  {selected.conversation_flow} flow
                </span>
              )}
              {selected.user_sentiment && (
                <span className="tag tag-purple">{selected.user_sentiment}</span>
              )}
            </div>

            {/* Search context */}
            {selected.snippets?.length > 0 && (
              <div className="drawer-section">
                <div className="drawer-section-label">Matched Phrases</div>
                {selected.snippets.map((snip, i) => (
                  <div
                    key={i}
                    className="search-snippet search-snippet-drawer"
                    dangerouslySetInnerHTML={{ __html: `"…${snip}…"` }}
                  />
                ))}
              </div>
            )}

            {/* Call summary */}
            <div className="drawer-section">
              <div className="drawer-section-label">Call Summary</div>
              {detailLoading ? (
                <div className="drawer-loading">Loading...</div>
              ) : callDetail?.call_summary ? (
                <div className="call-summary-box">{callDetail.call_summary}</div>
              ) : (
                <div style={{ color: 'var(--muted)', fontSize: 12 }}>No summary available</div>
              )}
            </div>

            {/* Transcript */}
            <div className="drawer-section" style={{ borderBottom: 'none' }}>
              <div className="drawer-section-label">Full Transcript</div>
              {detailLoading ? (
                <div className="drawer-loading">Loading...</div>
              ) : callDetail?.transcript?.length > 0 ? (
                <div className="transcript-scroll">
                  {callDetail.transcript.map(t => (
                    <div key={t.index} className={`tx-turn ${t.role === 'user' ? 'tx-turn-user' : ''}`}>
                      <span className={`tx-role-tag ${t.role === 'agent' ? 'tx-role-agent' : 'tx-role-user'}`}>
                        {t.role === 'agent' ? 'Agent' : 'Customer'}
                      </span>
                      <div className="tx-bubble">
                        <span dangerouslySetInnerHTML={{
                          __html: t.content?.replace(
                            new RegExp(`(${query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
                            '<mark>$1</mark>'
                          ) || ''
                        }} />
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
