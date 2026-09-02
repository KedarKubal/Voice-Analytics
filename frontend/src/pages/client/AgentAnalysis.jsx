import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import api from '../../api/apiClient'
import '../../App.css'

// ─── Animation variants ────────────────────────────────────────────────────
const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
}
const stagger = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
}
const pillItem = {
  hidden: { opacity: 0, scale: 0.85, y: 6 },
  show:   { opacity: 1, scale: 1,    y: 0, transition: { type: 'spring', stiffness: 340, damping: 22 } },
}

// ─── Agent definitions ─────────────────────────────────────────────────────
const AGENTS = [
  {
    key:   'all',
    name:  'All Agents',
    role:  'Overview',
    emoji: '📊',
    color: 'var(--accent2)',
    bg:    '#818cf812',
    border:'#818cf830',
    preset: [
      'Compare all agents by success rate',
      'Which agent has the highest engagement score?',
      'Give me a full performance overview of all agents',
      'Which agent is performing worst and why?',
      'How does each agent perform by call topic?',
    ],
  },
  {
    key:   'Sasha',
    name:  'Sasha',
    role:  'AI Concierge · Artel Apartments',
    emoji: '🏢',
    color: 'var(--accent)',
    bg:    '#6ee7b712',
    border:'#6ee7b730',
    preset: [
      'How is Sasha performing overall?',
      'What topics do callers ask Sasha most?',
      'What is Sasha\'s average engagement score?',
      'How often does Sasha successfully handle calls?',
      'Are guests happy when talking to Sasha?',
    ],
  },
  {
    key:   'Justine',
    name:  'Justine',
    role:  'AI Receptionist · MVAA Legal',
    emoji: '⚖️',
    color: '#a78bfa',
    bg:    '#a78bfa12',
    border:'#a78bfa30',
    preset: [
      'How is Justine performing overall?',
      'What are callers contacting MVAA about most?',
      'What is Justine\'s call success rate?',
      'How engaged are callers when speaking to Justine?',
      'What is Justine\'s average hesitation count?',
    ],
  },
  {
    key:   'Sarah',
    name:  'Sarah',
    role:  'At-Fault Collector · MVAA Legal',
    emoji: '🚗',
    color: 'var(--accent3)',
    bg:    '#fb923c12',
    border:'#fb923c30',
    preset: [
      'How is Sarah performing outbound vs inbound?',
      'Why is Sarah\'s inbound success rate so low?',
      'What is Sarah\'s outbound call success rate?',
      'How does Sarah\'s engagement compare to other agents?',
      'What happens on Sarah\'s failed calls?',
    ],
  },
  {
    key:   'Julia',
    name:  'Julia',
    role:  'Welcome Pack Follow-up · MVAA Legal',
    emoji: '📄',
    color: '#f472b6',
    bg:    '#f472b612',
    border:'#f472b630',
    preset: [
      'How is Julia performing on welcome pack follow-ups?',
      'Why does Julia have a low success rate?',
      'How many welcome pack calls has Julia made?',
      'Compare Julia outbound vs inbound performance',
      'What can be done to improve Julia\'s success rate?',
    ],
  },
]

// ─── Confidence badge ──────────────────────────────────────────────────────
function ConfidenceBadge({ confidence }) {
  const map = {
    HIGH:     { label: 'Grounded in DB', color: '#6ee7b7', bg: '#6ee7b715' },
    VERIFIED: { label: 'Verified from DB', color: '#22c55e', bg: '#22c55e15' },
    MEDIUM:   { label: 'AI + call records', color: '#fbbf24', bg: '#fbbf2415' },
    LOW:      { label: 'Limited data',    color: '#fb923c', bg: '#fb923c15' },
  }
  const m = map[confidence] || map.HIGH
  return (
    <span style={{
      fontFamily: "'DM Mono'", fontSize: 10, letterSpacing: '0.04em',
      color: m.color, background: m.bg,
      border: `1px solid ${m.color}40`,
      borderRadius: 5, padding: '2px 8px',
    }}>
      {m.label}
    </span>
  )
}

// ─── Single reasoning step row ─────────────────────────────────────────────
function ReasoningStep({ step, index }) {
  const [open, setOpen] = useState(index === 0)
  return (
    <motion.div
      variants={fadeUp}
      style={{
        border: '1px solid var(--border2)',
        borderRadius: 8,
        overflow: 'hidden',
        background: 'var(--surface2)',
      }}
    >
      {/* Header row — always visible */}
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: '9px 14px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        {/* Iteration badge */}
        <span style={{
          fontFamily: "'DM Mono'", fontSize: 10,
          color: 'var(--accent2)', background: '#818cf815',
          border: '1px solid #818cf830', borderRadius: 4,
          padding: '2px 7px', flexShrink: 0,
        }}>
          #{step.iteration}
        </span>

        {/* Tool chip */}
        {step.tool && (
          <span style={{
            fontFamily: "'DM Mono'", fontSize: 10,
            color: 'var(--accent)', background: '#6ee7b715',
            border: '1px solid #6ee7b730', borderRadius: 4,
            padding: '2px 7px', flexShrink: 0,
          }}>
            {step.tool}
          </span>
        )}

        {/* Thought preview */}
        <span style={{
          fontSize: 12, color: 'var(--muted)', flexGrow: 1,
          overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
        }}>
          {step.thought || 'Synthesising answer…'}
        </span>

        {/* Chevron */}
        <span style={{
          fontSize: 10, color: 'var(--muted)', flexShrink: 0,
          transform: open ? 'rotate(180deg)' : 'none',
          transition: 'transform 0.18s ease',
        }}>▼</span>
      </button>

      {/* Expanded body */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>

              {/* Thought */}
              {step.thought && (
                <div>
                  <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', marginBottom: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                    Thought
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.55 }}>
                    {step.thought}
                  </div>
                </div>
              )}

              {/* Tool + Params */}
              {step.tool && (
                <div>
                  <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', marginBottom: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                    Tool Call
                  </div>
                  <div style={{
                    fontFamily: "'DM Mono'", fontSize: 11,
                    background: '#0d0f1480', border: '1px solid var(--border2)',
                    borderRadius: 6, padding: '8px 12px',
                    color: 'var(--accent)', whiteSpace: 'pre-wrap', lineHeight: 1.5,
                  }}>
                    {step.tool}({JSON.stringify(step.params || {}, null, 2)})
                  </div>
                </div>
              )}

              {/* Observation */}
              {step.observation && (
                <div>
                  <div style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', marginBottom: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                    Observation
                  </div>
                  <div style={{
                    fontFamily: "'DM Mono'", fontSize: 11,
                    background: '#0d0f1480', border: '1px solid var(--border2)',
                    borderRadius: 6, padding: '8px 12px',
                    color: 'var(--muted2)', whiteSpace: 'pre-wrap', lineHeight: 1.5,
                    maxHeight: 200, overflowY: 'auto',
                  }}>
                    {step.observation}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────
export default function AgentAnalysis() {
  const { user }  = useAuth()
  const clientId  = user?.client_id

  const [selectedAgent, setSelectedAgent] = useState(AGENTS[0])
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState(null)
  const [error,   setError]   = useState(null)
  const [showSteps, setShowSteps] = useState(false)

  // Build question from preset or free input, inject agent name if not "all"
  function buildQuestion(raw) {
    if (selectedAgent.key === 'all') return raw
    // Only prepend agent name if question doesn't already name them
    const lower = raw.toLowerCase()
    if (!lower.includes(selectedAgent.key.toLowerCase())) return raw
    return raw
  }

  async function analyze(q) {
    const question = buildQuestion((q || input).trim())
    if (!question || loading) return
    setInput('')
    setResult(null)
    setError(null)
    setShowSteps(false)
    setLoading(true)

    try {
      const res = await api.post(`/agent/analyze/${clientId}`, { question, mode: 'auto' }, { timeout: 60000 })
      setResult(res.data)
      setShowSteps(false)
    } catch (e) {
      const detail = e.response?.data?.detail
      setError(detail || 'Could not reach the backend. Make sure the server is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  const activeAgentObj = selectedAgent
  const presetsToShow  = activeAgentObj.preset

  return (
    <div className="shell" style={{ paddingTop: 0 }}>

      {/* ── Page header ── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Agent Analysis</h2>
          <div className="page-sub">
            ReAct engine — the AI reasons step-by-step and queries live data to answer
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="tag tag-purple">ReAct Agent</span>
          <span className="tag tag-green">Live DB</span>
        </div>
      </div>

      {/* ── Agent selector cards ── */}
      <motion.div
        variants={stagger} initial="hidden" animate="show"
        style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}
      >
        {AGENTS.map(agent => (
          <motion.button
            key={agent.key}
            variants={fadeUp}
            whileHover={{ scale: 1.04, y: -2 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 380, damping: 22 }}
            onClick={() => { setSelectedAgent(agent); setResult(null); setError(null) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 16px',
              background: selectedAgent.key === agent.key ? agent.bg : 'var(--surface2)',
              border: `1px solid ${selectedAgent.key === agent.key ? agent.border : 'var(--border2)'}`,
              borderRadius: 10, cursor: 'pointer',
              transition: 'background 0.18s, border-color 0.18s',
              outline: 'none',
            }}
          >
            <span style={{ fontSize: 20 }}>{agent.emoji}</span>
            <div style={{ textAlign: 'left' }}>
              <div style={{
                fontSize: 13, fontWeight: 700,
                color: selectedAgent.key === agent.key ? agent.color : 'var(--text)',
              }}>
                {agent.name}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: "'DM Mono'", marginTop: 1 }}>
                {agent.role}
              </div>
            </div>
          </motion.button>
        ))}
      </motion.div>

      {/* ── Preset question pills ── */}
      <motion.div
        key={selectedAgent.key}  // re-animate when agent changes
        variants={stagger} initial="hidden" animate="show"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}
      >
        {presetsToShow.map(p => (
          <motion.span
            key={p}
            className="pill"
            variants={pillItem}
            whileHover={{ scale: 1.06, y: -2 }}
            whileTap={{ scale: 0.93 }}
            onClick={() => analyze(p)}
            style={{ cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1 }}
          >
            {p}
          </motion.span>
        ))}
      </motion.div>

      {/* ── Free-text input ── */}
      <div className="chat-input-row" style={{ marginBottom: 28 }}>
        <input
          className="query-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && analyze()}
          placeholder={
            selectedAgent.key === 'all'
              ? 'Ask anything about your agents…'
              : `Ask about ${selectedAgent.name}…`
          }
          disabled={loading}
          style={{ flex: 1 }}
        />
        <motion.button
          className="query-btn"
          onClick={() => analyze()}
          disabled={loading || !input.trim()}
          whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400, damping: 20 }}
        >
          {loading ? '…' : 'Analyse →'}
        </motion.button>
      </div>

      {/* ── Loading indicator ── */}
      <AnimatePresence>
        {loading && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '16px 20px',
              background: 'var(--surface2)',
              border: '1px solid var(--border2)',
              borderRadius: 10, marginBottom: 20,
            }}
          >
            <div style={{
              width: 18, height: 18, borderRadius: '50%',
              border: '2px solid var(--border2)',
              borderTop: `2px solid ${selectedAgent.color}`,
              animation: 'spin 0.75s linear infinite',
              flexShrink: 0,
            }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Agent is reasoning…</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: "'DM Mono'", marginTop: 2 }}>
                Running ReAct loop · querying live database
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Error ── */}
      <AnimatePresence>
        {error && (
          <motion.div
            variants={fadeUp} initial="hidden" animate="show" exit={{ opacity: 0 }}
            style={{
              padding: '14px 18px',
              background: '#f8717115', border: '1px solid #f8717130',
              borderRadius: 10, marginBottom: 20,
              fontSize: 13, color: 'var(--warn)', lineHeight: 1.5,
            }}
          >
            ⚠ {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Result panel ── */}
      <AnimatePresence>
        {result && (
          <motion.div
            variants={stagger} initial="hidden" animate="show"
            style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
          >

            {/* Answer card */}
            <motion.div
              variants={fadeUp}
              style={{
                padding: '20px 22px',
                background: 'var(--surface2)',
                border: `1px solid ${selectedAgent.border}`,
                borderRadius: 12,
              }}
            >
              {/* Top row: question + meta */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14, gap: 12 }}>
                <div style={{ fontSize: 12, color: 'var(--muted)', fontStyle: 'italic', flex: 1, lineHeight: 1.4 }}>
                  "{result.question}"
                </div>
                <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <ConfidenceBadge confidence={result.confidence} />
                  <span style={{
                    fontFamily: "'DM Mono'", fontSize: 10,
                    color: 'var(--muted)', background: 'var(--surface)',
                    border: '1px solid var(--border2)', borderRadius: 5, padding: '2px 8px',
                  }}>
                    {result.iterations} step{result.iterations !== 1 ? 's' : ''}
                  </span>
                  <span style={{
                    fontFamily: "'DM Mono'", fontSize: 10,
                    color: 'var(--muted)', background: 'var(--surface)',
                    border: '1px solid var(--border2)', borderRadius: 5, padding: '2px 8px',
                  }}>
                    {result.response_ms}ms
                  </span>
                </div>
              </div>

              {/* Answer text */}
              <div style={{ fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap', color: 'var(--text)' }}>
                {result.answer}
              </div>

              {/* Tools used chips */}
              {result.tools_used?.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 14 }}>
                  {result.tools_used.map(t => (
                    <span key={t} style={{
                      fontFamily: "'DM Mono'", fontSize: 10,
                      color: 'var(--accent)', background: '#6ee7b715',
                      border: '1px solid #6ee7b730', borderRadius: 5, padding: '2px 7px',
                    }}>
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* Sources */}
              {result.sources?.length > 0 && (
                <details style={{ marginTop: 12 }}>
                  <summary style={{
                    fontFamily: "'DM Mono'", fontSize: 10,
                    color: 'var(--muted)', cursor: 'pointer', letterSpacing: '0.04em',
                  }}>
                    {result.sources.length} source{result.sources.length !== 1 ? 's' : ''}
                  </summary>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                    {result.sources.map(s => (
                      <span key={s} style={{
                        fontFamily: "'DM Mono'", fontSize: 10,
                        color: 'var(--muted2)', background: 'var(--surface)',
                        border: '1px solid var(--border2)', borderRadius: 4, padding: '2px 7px',
                      }}>
                        {s}
                      </span>
                    ))}
                  </div>
                </details>
              )}
            </motion.div>

            {/* Reasoning steps toggle */}
            {result.reasoning_steps?.length > 0 && (
              <motion.div variants={fadeUp}>
                <button
                  onClick={() => setShowSteps(v => !v)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0',
                    color: 'var(--accent2)', fontSize: 12, fontFamily: "'DM Mono'",
                    letterSpacing: '0.04em',
                  }}
                >
                  <span style={{
                    display: 'inline-block',
                    transform: showSteps ? 'rotate(90deg)' : 'none',
                    transition: 'transform 0.18s ease',
                  }}>▶</span>
                  {showSteps ? 'Hide' : 'Show'} reasoning chain ({result.reasoning_steps.length} step{result.reasoning_steps.length !== 1 ? 's' : ''})
                </button>

                <AnimatePresence>
                  {showSteps && (
                    <motion.div
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      transition={{ duration: 0.2 }}
                    >
                      <motion.div
                        variants={stagger} initial="hidden" animate="show"
                        style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}
                      >
                        {result.reasoning_steps.map((step, i) => (
                          <ReasoningStep key={i} step={step} index={i} />
                        ))}
                      </motion.div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )}

          </motion.div>
        )}
      </AnimatePresence>

      {/* Empty state */}
      {!result && !loading && !error && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}
          style={{
            textAlign: 'center', padding: '52px 0',
            color: 'var(--muted)', fontSize: 13, lineHeight: 1.6,
          }}
        >
          <div style={{ fontSize: 36, marginBottom: 14 }}>{selectedAgent.emoji}</div>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>
            Ask about {selectedAgent.name === 'All Agents' ? 'your agents' : selectedAgent.name}
          </div>
          <div style={{ color: 'var(--muted2)', maxWidth: 380, margin: '0 auto' }}>
            Pick a preset question above or type your own.
            The agent will query your live call database and show its reasoning.
          </div>
        </motion.div>
      )}

      {/* Spin keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
