import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import api from '../../api/apiClient'
import '../../App.css'

// ─── Animation variants ────────────────────────────────────────────────────
const pillItem = {
  hidden: { opacity: 0, scale: 0.85, y: 6 },
  show:   { opacity: 1, scale: 1,    y: 0, transition: { type: 'spring', stiffness: 340, damping: 22 } },
}
const msgVariant = {
  hidden: { opacity: 0, y: 14 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' } },
}

// ─── General RAG suggestion pills ─────────────────────────────────────────
const GENERAL_PILLS = [
  'How many calls do I have?',
  'What is our call success rate?',
  'What are callers mostly calling about?',
  'What is the average engagement score?',
  'Which calls went poorly and why?',
  'What time of day are we busiest?',
  'How are customers feeling?',
  'How many calls are improving vs deteriorating?',
  'Tell me about the worst performing calls',
  'What is the average silence ratio?',
]

// ─── Client → agent config (client-scoped — only show relevant agents) ────
const CLIENT_AGENTS = {
  client_heya_001: [
    {
      key:    'Sasha',
      name:   'Sasha',
      role:   'AI Concierge',
      emoji:  '🏢',
      color:  'var(--accent)',
      bg:     '#6ee7b712',
      border: '#6ee7b730',
      preset: [
        'How is Sasha performing overall?',
        "What topics do callers ask Sasha most?",
        "What is Sasha's average engagement score?",
        "How often does Sasha successfully handle calls?",
        "Are guests happy when talking to Sasha?",
      ],
    },
  ],
  client_heya_002: [
    {
      key:    'Justine',
      name:   'Justine',
      role:   'AI Receptionist',
      emoji:  '⚖️',
      color:  '#a78bfa',
      bg:     '#a78bfa12',
      border: '#a78bfa30',
      preset: [
        'How is Justine performing overall?',
        'What are callers contacting MVAA about most?',
        "What is Justine's call success rate?",
        'How engaged are callers when speaking to Justine?',
        "What is Justine's average hesitation count?",
      ],
    },
    {
      key:    'Sarah',
      name:   'Sarah',
      role:   'At-Fault Collector',
      emoji:  '🚗',
      color:  'var(--accent3)',
      bg:     '#fb923c12',
      border: '#fb923c30',
      preset: [
        'How is Sarah performing outbound vs inbound?',
        "Why is Sarah's inbound success rate so low?",
        "What is Sarah's outbound call success rate?",
        "How does Sarah's engagement compare to other agents?",
        "What happens on Sarah's failed calls?",
      ],
    },
    {
      key:    'Julia',
      name:   'Julia',
      role:   'Welcome Pack Follow-up',
      emoji:  '📄',
      color:  '#f472b6',
      bg:     '#f472b612',
      border: '#f472b630',
      preset: [
        'How is Julia performing on welcome pack follow-ups?',
        "Why does Julia have a low success rate?",
        'How many welcome pack calls has Julia made?',
        'Compare Julia outbound vs inbound performance',
        "What can be done to improve Julia's success rate?",
      ],
    },
  ],
}

// All-agents option (shown for every client)
const ALL_AGENTS_OPTION = {
  key:    'all',
  name:   'All Agents',
  role:   'Overview',
  emoji:  '📊',
  color:  'var(--accent2)',
  bg:     '#818cf812',
  border: '#818cf830',
  preset: [
    'Compare all agents by success rate',
    'Which agent has the highest engagement score?',
    'Give me a full performance overview of all agents',
    'Which agent is performing worst and why?',
    'How does each agent perform by call topic?',
  ],
}

// ─── Confidence badge ──────────────────────────────────────────────────────
const CONFIDENCE_META = {
  VERIFIED: { label: 'Verified from database',  color: '#22c55e', bg: '#22c55e15' },
  HIGH:     { label: 'Grounded in statistics',  color: '#6ee7b7', bg: '#6ee7b715' },
  MEDIUM:   { label: 'AI + call records',        color: '#fbbf24', bg: '#fbbf2415' },
  LOW:      { label: 'Limited data',             color: '#fb923c', bg: '#fb923c15' },
}

function ConfidenceBadge({ confidence }) {
  const meta = CONFIDENCE_META[confidence] || CONFIDENCE_META.HIGH
  return (
    <span style={{
      fontFamily: "'DM Mono'", fontSize: 10, letterSpacing: '0.04em',
      color: meta.color, background: meta.bg,
      border: `1px solid ${meta.color}40`,
      borderRadius: 5, padding: '2px 8px',
    }}>
      {meta.label}
    </span>
  )
}

// ─── Reasoning steps toggle (inline in chat bubble) ───────────────────────
function ReasoningToggle({ steps }) {
  const [open, setOpen] = useState(false)
  if (!steps?.length) return null
  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'none', border: 'none', cursor: 'pointer', padding: '2px 0',
          color: 'var(--accent2)', fontSize: 11, fontFamily: "'DM Mono'",
          letterSpacing: '0.04em',
        }}
      >
        <span style={{ display: 'inline-block', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.18s ease' }}>▶</span>
        {open ? 'Hide' : 'Show'} reasoning ({steps.length} step{steps.length !== 1 ? 's' : ''})
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
              {steps.map((step, i) => (
                <div key={i} style={{
                  background: 'var(--inset-bg)', border: '1px solid var(--border2)',
                  borderRadius: 7, padding: '8px 12px',
                  display: 'flex', flexDirection: 'column', gap: 5,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <span style={{
                      fontFamily: "'DM Mono'", fontSize: 9, color: 'var(--accent2)',
                      background: '#818cf815', border: '1px solid #818cf830',
                      borderRadius: 4, padding: '1px 6px', flexShrink: 0,
                    }}>#{step.iteration}</span>
                    {step.tool && (
                      <span style={{
                        fontFamily: "'DM Mono'", fontSize: 9, color: 'var(--accent)',
                        background: '#6ee7b715', border: '1px solid #6ee7b730',
                        borderRadius: 4, padding: '1px 6px', flexShrink: 0,
                      }}>{step.tool}</span>
                    )}
                    <span style={{ fontSize: 11, color: 'var(--muted)', flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                      {step.thought || 'Synthesising…'}
                    </span>
                  </div>
                  {step.observation && (
                    <div style={{
                      fontFamily: "'DM Mono'", fontSize: 10,
                      color: 'var(--muted2)', whiteSpace: 'pre-wrap', lineHeight: 1.45,
                      maxHeight: 100, overflowY: 'auto',
                    }}>{step.observation}</div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────
export default function AskYourData() {
  const { user }   = useAuth()
  const clientId   = user?.client_id
  const bottomRef  = useRef(null)

  // Agent section state
  const clientAgents    = [ALL_AGENTS_OPTION, ...(CLIENT_AGENTS[clientId] || [])]
  const [selectedAgent, setSelectedAgent] = useState(ALL_AGENTS_OPTION)

  const [messages, setMessages] = useState([
    {
      role: 'system',
      text: 'Ask me anything about your calls — volumes, topics, engagement, sentiment, peak hours, worst calls, and more. Every answer is grounded in your actual call data.',
    }
  ])
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Send general RAG question ──────────────────────────────────────────
  async function sendRag(q) {
    const question = (q || input).trim()
    if (!question || loading) return
    setInput('')

    setMessages(prev => [...prev, { role: 'user', text: question }])
    setLoading(true)

    const history = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-12)
      .map(m => ({ role: m.role, content: m.text }))

    try {
      const res = await api.post('/query', { question, client_id: clientId, history })
      setMessages(prev => [...prev, {
        role:       'assistant',
        text:       res.data.answer,
        route:      res.data.route,
        confidence: res.data.confidence,
        sources:    res.data.sources || [],
        isAgentAnswer: false,
      }])
    } catch (e) {
      const detail = e.response?.data?.detail
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: detail ? `Error: ${detail}` : 'Could not reach the server. Make sure the backend is running on port 8000.',
        route: 'error', confidence: null, sources: [], isAgentAnswer: false,
      }])
    } finally {
      setLoading(false)
    }
  }

  // ── Send agent ReAct question ──────────────────────────────────────────
  async function sendAgent(q) {
    const question = (q || input).trim()
    if (!question || loading) return
    setInput('')

    setMessages(prev => [...prev, {
      role: 'user', text: question,
      agentContext: selectedAgent.key !== 'all' ? selectedAgent.name : null,
    }])
    setLoading(true)

    try {
      const res = await api.post(`/agent/analyze/${clientId}`, { question, mode: 'auto' }, { timeout: 60000 })
      setMessages(prev => [...prev, {
        role:            'assistant',
        text:            res.data.answer,
        confidence:      res.data.confidence,
        sources:         res.data.sources || [],
        isAgentAnswer:   true,
        tools_used:      res.data.tools_used || [],
        reasoning_steps: res.data.reasoning_steps || [],
        iterations:      res.data.iterations,
        response_ms:     res.data.response_ms,
      }])
    } catch (e) {
      const detail = e.response?.data?.detail
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: detail ? `Error: ${detail}` : 'Agent analysis failed. Make sure the backend is running on port 8000.',
        route: 'error', confidence: null, sources: [], isAgentAnswer: false,
      }])
    } finally {
      setLoading(false)
    }
  }

  function send(q) {
    return sendRag(q || input)
  }

  function clearConversation() {
    setMessages([{
      role: 'system',
      text: 'Ask me anything about your calls — volumes, topics, engagement, sentiment, peak hours, worst calls, and more. Every answer is grounded in your actual call data.',
    }])
  }

  return (
    <div className="chat-shell">
      {/* ── Page header ── */}
      <div className="page-header" style={{ alignItems: 'center', gap: 16 }}>
        {/* Title */}
        <div style={{ flexShrink: 0 }}>
          <h2 className="page-title">Ask Your Data</h2>
          <div className="page-sub">Every answer comes from your call records — zero hallucination</div>
        </div>

        {/* Agent selector — lives in the header */}
        <motion.div
          style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1 }}
          initial="hidden" animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
        >
          {clientAgents.map(agent => (
            <motion.button
              key={agent.key}
              variants={pillItem}
              whileHover={{ scale: 1.04, y: -2 }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 380, damping: 22 }}
              onClick={() => setSelectedAgent(agent)}
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                padding: '6px 12px',
                background: selectedAgent.key === agent.key ? agent.bg : 'var(--surface)',
                border: `1px solid ${selectedAgent.key === agent.key ? agent.border : 'var(--border2)'}`,
                borderRadius: 9, cursor: 'pointer',
                transition: 'background 0.18s, border-color 0.18s',
                outline: 'none',
              }}
            >
              <div style={{ textAlign: 'left' }}>
                <div style={{
                  fontSize: 11, fontWeight: 700,
                  color: selectedAgent.key === agent.key ? agent.color : 'var(--text)',
                }}>{agent.name}</div>
                <div style={{ fontSize: 9, color: 'var(--muted)', fontFamily: "'DM Mono'", marginTop: 1 }}>
                  {agent.role}
                </div>
              </div>
            </motion.button>
          ))}
          <span className="tag tag-purple" style={{ fontSize: 9, alignSelf: 'center' }}>ReAct</span>
          <span className="tag tag-green"  style={{ fontSize: 9, alignSelf: 'center' }}>Live DB</span>
        </motion.div>

        {/* Right side controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {messages.filter(m => m.role === 'user' || m.role === 'assistant').length > 0 && (
            <span style={{
              fontFamily: "'DM Mono'", fontSize: 10, letterSpacing: '0.04em',
              color: 'var(--accent2)', background: '#818cf812',
              border: '1px solid #818cf830', borderRadius: 5, padding: '3px 9px',
            }}>
              ↺ {Math.min(messages.filter(m => m.role === 'user' || m.role === 'assistant').length, 12)} msgs in memory
            </span>
          )}
          <motion.button
            className="export-btn"
            style={{ fontSize: 11, padding: '5px 12px' }}
            onClick={clearConversation}
            whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
          >
            Clear
          </motion.button>
          <span className="tag tag-purple">RAG</span>
        </div>
      </div>

      {/* ── General suggestion pills ── */}
      <motion.div
        className="query-pills"
        style={{ marginBottom: 12 }}
        initial="hidden" animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}
      >
        {GENERAL_PILLS.map(p => (
          <motion.span key={p} className="pill" variants={pillItem}
            whileHover={{ scale: 1.06, y: -2 }} whileTap={{ scale: 0.93 }}
            onClick={() => send(p)}>{p}</motion.span>
        ))}
      </motion.div>

      {/* ── Agent preset pills ── */}
      <AnimatePresence mode="wait">
        <motion.div
          key={selectedAgent.key}
          style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 20 }}
          initial="hidden" animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}
        >
          {selectedAgent.preset.map(p => (
            <motion.span
              key={p} className="pill" variants={pillItem}
              whileHover={{ scale: 1.06, y: -2 }} whileTap={{ scale: 0.93 }}
              onClick={() => !loading && sendAgent(p)}
              style={{
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1,
                borderColor: selectedAgent.border,
                color: selectedAgent.color,
              }}
            >
              {p}
            </motion.span>
          ))}
        </motion.div>
      </AnimatePresence>

      {/* ── Chat messages ── */}
      <div className="chat-messages">
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div key={i} className={`chat-msg chat-msg-${m.role}`}
              variants={msgVariant} initial="hidden" animate="show"
            >
              {m.role === 'user'      && <div className="chat-avatar user-avatar">You</div>}
              {m.role === 'assistant' && <div className="chat-avatar ai-avatar">AI</div>}
              {m.role === 'system'    && <div className="chat-avatar sys-avatar">H</div>}
              <div className="chat-bubble">
                {/* Agent context label on user messages */}
                {m.role === 'user' && m.agentContext && (
                  <div style={{
                    fontFamily: "'DM Mono'", fontSize: 9, letterSpacing: '0.05em',
                    color: 'var(--accent2)', marginBottom: 5,
                    textTransform: 'uppercase',
                  }}>
                    → {m.agentContext}
                  </div>
                )}

                <div className="chat-text" style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>

                {/* RAG answer metadata */}
                {m.role === 'assistant' && !m.isAgentAnswer && m.confidence && (
                  <div className="chat-meta" style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <ConfidenceBadge confidence={m.confidence} />
                    {m.route && m.route !== 'error' && (
                      <span className={`answer-route ${m.route?.includes('sql') ? 'route-sql' : 'route-semantic'}`}>
                        {m.route}
                      </span>
                    )}
                  </div>
                )}

                {/* Agent ReAct answer metadata */}
                {m.role === 'assistant' && m.isAgentAnswer && m.confidence && (
                  <div className="chat-meta" style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <ConfidenceBadge confidence={m.confidence} />
                    {m.tools_used?.map(t => (
                      <span key={t} style={{
                        fontFamily: "'DM Mono'", fontSize: 10,
                        color: 'var(--accent)', background: '#6ee7b715',
                        border: '1px solid #6ee7b730', borderRadius: 5, padding: '2px 7px',
                      }}>{t}</span>
                    ))}
                    {m.iterations != null && (
                      <span style={{
                        fontFamily: "'DM Mono'", fontSize: 10,
                        color: 'var(--muted)', background: 'var(--surface)',
                        border: '1px solid var(--border2)', borderRadius: 5, padding: '2px 7px',
                      }}>{m.iterations} step{m.iterations !== 1 ? 's' : ''}</span>
                    )}
                    {m.response_ms != null && (
                      <span style={{
                        fontFamily: "'DM Mono'", fontSize: 10,
                        color: 'var(--muted)', background: 'var(--surface)',
                        border: '1px solid var(--border2)', borderRadius: 5, padding: '2px 7px',
                      }}>{m.response_ms}ms</span>
                    )}
                  </div>
                )}

                {/* Reasoning steps toggle for agent answers */}
                {m.role === 'assistant' && m.isAgentAnswer && (
                  <ReasoningToggle steps={m.reasoning_steps} />
                )}

                {/* Source call IDs (RAG answers) */}
                {m.sources?.length > 0 && !m.isAgentAnswer && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)', cursor: 'pointer', letterSpacing: '0.04em' }}>
                      {m.sources.length} source call{m.sources.length !== 1 ? 's' : ''}
                    </summary>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                      {m.sources.map(id => (
                        <span key={id} style={{
                          fontFamily: "'DM Mono'", fontSize: 10,
                          color: 'var(--muted2)', background: 'var(--surface2)',
                          border: '1px solid var(--border2)', borderRadius: 4, padding: '2px 7px',
                        }}>{id}</span>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        <AnimatePresence>
          {loading && (
            <motion.div
              className="chat-msg chat-msg-assistant"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
            >
              <div className="chat-avatar ai-avatar">AI</div>
              <div className="chat-bubble">
                <div className="chat-typing"><span/><span/><span/></div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div className="chat-input-row">
        <input
          className="query-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Ask anything about your calls..."
          disabled={loading}
        />
        <motion.button className="query-btn" onClick={() => send()} disabled={loading || !input.trim()}
          whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400, damping: 20 }}>
          {loading ? '...' : 'Send →'}
        </motion.button>
      </div>
    </div>
  )
}
