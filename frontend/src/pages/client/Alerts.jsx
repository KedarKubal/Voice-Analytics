import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import api from '../../api/apiClient'
import '../../App.css'

const cardItem = {
  hidden: { opacity: 0, y: 20 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
}
const historyRow = {
  hidden: { opacity: 0, x: -10 },
  show:   { opacity: 1, x: 0, transition: { duration: 0.22, ease: 'easeOut' } },
}

const ALERT_TYPES = [
  { id: 'high_silence',             label: 'High Silence Ratio',         desc: 'Fires when >10% of calls exceed 30% dead air'                   },
  { id: 'poor_conversation_flow',   label: 'Poor Conversation Flow',      desc: 'Fires when >40% of calls are classified as poor flow'           },
  { id: 'low_success_rate',         label: 'Low Call Success Rate',       desc: 'Fires when success rate falls below 80%'                        },
  { id: 'low_engagement',           label: 'Low Engagement Score',        desc: 'Fires when average engagement drops below 65/100'               },
  { id: 'deteriorating_trajectory', label: 'Deteriorating Trajectories',  desc: 'Fires when >35% of calls show declining caller energy'          },
  { id: 'high_interruptions',       label: 'High Interruption Rate',      desc: 'Fires when average interruptions exceed 3 per call'             },
  { id: 'negative_sentiment',       label: 'High Negative Sentiment',     desc: 'Fires when >25% of callers end with negative sentiment'         },
  { id: 'weekly_digest',            label: 'Weekly Performance Digest',   desc: 'Summary email every week with KPIs and top recommendations'     },
]

const STATUS_META = {
  sent:     { color: 'var(--accent)',  label: 'Sent'    },
  failed:   { color: 'var(--warn)',    label: 'Failed'  },
  cooldown: { color: 'var(--muted)',   label: 'Cooldown' },
}

export default function Alerts() {
  const { user } = useAuth()
  const clientId = user?.client_id

  const [configs,     setConfigs]     = useState([])
  const [history,     setHistory]     = useState([])
  const [loading,     setLoading]     = useState(true)
  const [saving,      setSaving]      = useState(null)
  const [testing,     setTesting]     = useState(null)
  const [running,     setRunning]     = useState(false)
  const [email,       setEmail]       = useState(user?.email || '')
  const [toast,       setToast]       = useState(null)

  // Local draft state — one entry per alert type
  const [drafts, setDrafts] = useState({})

  function showToast(msg, ok = true) {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  useEffect(() => {
    if (!clientId) return
    setLoading(true)
    Promise.all([
      api.get(`/alerts/config/${clientId}`),
      api.get(`/alerts/history/${clientId}`),
    ])
      .then(([cfg, hist]) => {
        const cfgMap = {}
        ;(cfg.data.configs || []).forEach(c => { cfgMap[c.alert_type] = c })
        setConfigs(cfgMap)
        setHistory(hist.data.logs || [])
        // Seed drafts from saved configs
        const d = {}
        ALERT_TYPES.forEach(({ id }) => {
          d[id] = {
            enabled:      cfgMap[id]?.enabled      ?? false,
            email:        cfgMap[id]?.email        ?? email,
            min_priority: cfgMap[id]?.min_priority ?? 'warning',
          }
        })
        setDrafts(d)
      })
      .catch(() => showToast('Failed to load alert settings', false))
      .finally(() => setLoading(false))
  }, [clientId])

  function updateDraft(type, field, value) {
    setDrafts(d => ({ ...d, [type]: { ...d[type], [field]: value } }))
  }

  async function saveConfig(type) {
    const draft = drafts[type]
    if (!draft?.email?.includes('@')) {
      showToast('Enter a valid email address first', false); return
    }
    setSaving(type)
    try {
      await api.post(`/alerts/config/${clientId}`, {
        alert_type:   type,
        enabled:      draft.enabled,
        email:        draft.email,
        min_priority: draft.min_priority,
      })
      showToast(`Saved — ${type.replace(/_/g, ' ')}`)
      // Refresh configs
      const r = await api.get(`/alerts/config/${clientId}`)
      const cfgMap = {}
      ;(r.data.configs || []).forEach(c => { cfgMap[c.alert_type] = c })
      setConfigs(cfgMap)
    } catch {
      showToast('Save failed', false)
    } finally {
      setSaving(null)
    }
  }

  async function sendTest(type) {
    const draft = drafts[type]
    if (!draft?.email?.includes('@')) {
      showToast('Enter a valid email address first', false); return
    }
    setTesting(type)
    try {
      const r = await api.post(`/alerts/test/${clientId}`, {
        alert_type:   type,
        enabled:      true,
        email:        draft.email,
        min_priority: draft.min_priority,
      })
      showToast(
        r.data.status === 'sent'
          ? `Test email sent to ${draft.email}`
          : `Failed: ${r.data.message}`,
        r.data.status === 'sent'
      )
    } catch {
      showToast('Test failed — check SMTP settings', false)
    } finally {
      setTesting(null)
    }
  }

  async function runChecks() {
    setRunning(true)
    try {
      await api.post(`/alerts/check/${clientId}`)
      showToast('Alert checks running in background')
      setTimeout(async () => {
        const r = await api.get(`/alerts/history/${clientId}`)
        setHistory(r.data.logs || [])
      }, 3000)
    } catch {
      showToast('Failed to trigger checks', false)
    } finally {
      setRunning(false)
    }
  }

  async function sendDigest() {
    try {
      await api.post(`/alerts/digest/${clientId}`)
      showToast('Weekly digest sending in background')
    } catch {
      showToast('Failed to send digest', false)
    }
  }

  if (loading) return <div className="loading-bar" />

  return (
    <div>
      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            className="alert-toast"
            style={{ background: toast.ok ? '#6ee7b720' : '#f8717120', borderColor: toast.ok ? '#6ee7b740' : '#f8717140', color: toast.ok ? 'var(--accent)' : 'var(--warn)' }}
            initial={{ opacity: 0, y: -14, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 340, damping: 24 }}
          >
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="page-header">
        <div>
          <h2 className="page-title">Alerts</h2>
          <div className="page-sub">Email notifications when your call metrics cross a threshold</div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <motion.button className="alert-action-btn" onClick={sendDigest}
            whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}>
            Send Digest Now
          </motion.button>
          <motion.button className="alert-action-btn alert-action-btn-primary" onClick={runChecks} disabled={running}
            whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}>
            {running ? 'Checking...' : 'Run Checks Now'}
          </motion.button>
        </div>
      </div>

      {/* Global email hint */}
      <div className="alert-hint">
        Set the email address for each alert below. All alerts for this account can share one address, or use different ones.
      </div>

      {/* Alert type cards */}
      <motion.div
        className="alert-grid"
        initial="hidden"
        animate="show"
        variants={{ hidden:{}, show:{ transition:{ staggerChildren:0.07 } } }}
      >
        {ALERT_TYPES.map(({ id, label, desc }) => {
          const draft      = drafts[id] || { enabled: false, email, min_priority: 'warning' }
          const saved      = configs[id]
          const isSaving   = saving  === id
          const isTesting  = testing === id
          const isDirty    = JSON.stringify(draft) !== JSON.stringify({
            enabled:      saved?.enabled      ?? false,
            email:        saved?.email        ?? '',
            min_priority: saved?.min_priority ?? 'warning',
          })

          return (
            <motion.div key={id} className={`alert-card ${draft.enabled ? 'alert-card-active' : ''}`}
              variants={cardItem}
              whileHover={{ y: -2, transition: { duration: 0.15 } }}
            >
              <div className="alert-card-header">
                <div className="alert-card-info">
                  <div className="alert-card-label">{label}</div>
                  <div className="alert-card-desc">{desc}</div>
                </div>
                {/* Toggle */}
                <label className="alert-toggle">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={e => updateDraft(id, 'enabled', e.target.checked)}
                  />
                  <span className="alert-toggle-track">
                    <span className="alert-toggle-thumb" />
                  </span>
                </label>
              </div>

              <AnimatePresence initial={false}>
              {draft.enabled && (
                <motion.div
                  className="alert-card-body"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: 'easeInOut' }}
                  style={{ overflow: 'hidden' }}
                >
                  <div className="alert-field-row">
                    <div className="alert-field">
                      <label className="alert-field-label">Email address</label>
                      <input
                        type="email"
                        className="alert-input"
                        value={draft.email}
                        placeholder="you@example.com"
                        onChange={e => updateDraft(id, 'email', e.target.value)}
                      />
                    </div>
                    {id !== 'weekly_digest' && (
                      <div className="alert-field alert-field-sm">
                        <label className="alert-field-label">Min severity</label>
                        <select
                          className="alert-select"
                          value={draft.min_priority}
                          onChange={e => updateDraft(id, 'min_priority', e.target.value)}
                        >
                          <option value="warning">Warning +</option>
                          <option value="critical">Critical only</option>
                        </select>
                      </div>
                    )}
                  </div>

                  <div className="alert-card-actions">
                    {saved?.last_triggered && (
                      <span className="alert-last-sent">
                        Last sent: {new Date(saved.last_triggered).toLocaleString('en-AU', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })}
                      </span>
                    )}
                    <motion.button
                      className="alert-btn-test"
                      onClick={() => sendTest(id)}
                      disabled={isTesting}
                      whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.95 }}
                      transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                    >
                      {isTesting ? 'Sending...' : 'Test email'}
                    </motion.button>
                    <motion.button
                      className={`alert-btn-save ${isDirty ? 'alert-btn-save-dirty' : ''}`}
                      onClick={() => saveConfig(id)}
                      disabled={isSaving || !isDirty}
                      whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.95 }}
                      transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                    >
                      {isSaving ? 'Saving...' : isDirty ? 'Save changes' : 'Saved ✓'}
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
      <div className="section-label" style={{ marginTop: 40 }}>Alert History</div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {history.length === 0 ? (
          <div style={{ padding: 24, color: 'var(--muted)', fontFamily: "'DM Mono'", fontSize: 12, textAlign: 'center' }}>
            No alerts sent yet — save a config and click "Run Checks Now"
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Alert Type</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Sent At</th>
              </tr>
            </thead>
            <tbody>
              {history.map((log, i) => {
                const meta = STATUS_META[log.status] || STATUS_META.failed
                return (
                  <motion.tr key={log.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05, duration: 0.22, ease: 'easeOut' }}
                  >
                    <td style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>
                      {log.alert_type?.replace(/_/g, ' ') || '—'}
                    </td>
                    <td style={{ fontFamily: "'DM Mono'", fontSize: 11, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {log.subject || '—'}
                    </td>
                    <td>
                      <span style={{ fontFamily: "'DM Mono'", fontSize: 10, fontWeight: 700, color: meta.color }}>
                        {meta.label}
                      </span>
                    </td>
                    <td style={{ fontFamily: "'DM Mono'", fontSize: 11, whiteSpace: 'nowrap' }}>
                      {log.sent_at
                        ? new Date(log.sent_at).toLocaleString('en-AU', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })
                        : '—'}
                    </td>
                  </motion.tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
