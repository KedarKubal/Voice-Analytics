import React from 'react'
import { motion } from 'framer-motion'
import { useClientData } from '../../hooks/useClientData'
import { useFilters } from '../../context/FilterContext'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts'
import '../../App.css'

const E = [0.22, 1, 0.36, 1]
const cardIn  = { hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: 0.42, ease: E } } }
const rowStagger = { hidden: {}, show: { transition: { staggerChildren: 0.09 } } }

const TT = {
  contentStyle: { background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 8, fontFamily: 'Inter, sans-serif' },
  labelStyle:   { color: 'var(--tooltip-text)', fontSize: 12 },
  itemStyle:    { color: 'var(--tooltip-item)', fontSize: 12 },
}

const EMOTION_COLORS = {
  happy: '#22c55e', sad: '#60a5fa', angry: '#ef4444',
  neutral: '#94a3b8', fearful: '#fb923c', disgusted: '#a3e635', surprised: '#c084fc',
}
const GRADE_COLORS_MAP = { A: '#22c55e', B: '#6ee7b7', C: '#fbbf24', D: '#fb923c', F: '#ef4444' }
const TOPIC_COLORS = {
  booking: '#6ee7b7', cancellation: '#fb923c', complaint: '#f87171', payment: '#34d399',
  enquiry: '#818cf8', technical_support: '#22d3ee', emergency: '#ef4444',
  follow_up: '#a78bfa', general: '#64748b',
}

function mean(arr, key) {
  const vals = arr.map(r => parseFloat(r[key]) || 0).filter(v => v > 0)
  return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0
}
function buildHistogram(insights) {
  const b = [{ r: '0–20', n: 0 }, { r: '20–40', n: 0 }, { r: '40–60', n: 0 }, { r: '60–80', n: 0 }, { r: '80–100', n: 0 }]
  insights.forEach(r => { const s = parseFloat(r.engagement_score) || 0; b[Math.min(Math.floor(s / 20), 4)].n++ })
  return b
}

// ── Storytelling section header ───────────────────────────────────────────────
function StorySection({ num, title, sub }) {
  return (
    <div className="story-section">
      <span className="story-section-num">{num}</span>
      <div>
        <div className="story-section-title">{title}</div>
        <div className="story-section-sub">{sub}</div>
      </div>
    </div>
  )
}

// ── Auto-generated narrative summary ─────────────────────────────────────────
function NarrativeSummary({ n, avgEngagement, dominantFlow, flowCounts, agentPct, custPct, hasFilter }) {
  if (!n) return null

  const engLevel = avgEngagement >= 75 ? 'strong' : avgEngagement >= 55 ? 'moderate' : 'low'
  const engColor = avgEngagement >= 75 ? 'var(--accent)' : avgEngagement >= 55 ? 'var(--accent3)' : 'var(--warn)'
  const flowColor = dominantFlow === 'smooth' ? 'var(--accent)' : dominantFlow === 'moderate' ? 'var(--accent3)' : 'var(--warn)'

  const flowTip = dominantFlow === 'smooth'
    ? 'Calls are well-paced with natural pauses — a positive signal.'
    : dominantFlow === 'moderate'
    ? 'Some calls show uneven pacing. Review agent pause frequency.'
    : 'Most calls have poor flow — agents may be over-talking. A key coaching opportunity.'

  const talkTip = agentPct > 65
    ? `Agents dominate ${agentPct.toFixed(0)}% of talk time — customers have limited floor share.`
    : agentPct < 45
    ? `Customers lead ${custPct.toFixed(0)}% of talk — agents may need to guide conversations more actively.`
    : `Talk time is balanced: agents at ${agentPct.toFixed(0)}%, customers at ${custPct.toFixed(0)}%.`

  return (
    <motion.div
      className="insight-narrative"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: E }}
    >
      <div className="insight-narrative-eyebrow">Insight Summary</div>
      <p>
        Across <strong>{n.toLocaleString()}</strong> {hasFilter ? 'filtered' : ''} call{n !== 1 ? 's' : ''},
        average engagement is{' '}
        <strong style={{ color: engColor }}>{avgEngagement.toFixed(0)}/100</strong> ({engLevel}).
        {' '}The dominant conversation flow is{' '}
        <strong style={{ color: flowColor }}>{dominantFlow}</strong>
        {flowCounts.smooth > 0 && flowCounts.poor > 0
          ? ` (${flowCounts.smooth} smooth, ${flowCounts.moderate} moderate, ${flowCounts.poor} poor)`
          : ''}.
        {' '}{flowTip}
        {' '}{talkTip}
      </p>
    </motion.div>
  )
}

// ── Redesigned Conversation Flow card ────────────────────────────────────────
function ConversationFlowCard({ n, dominantFlow, flowCounts }) {
  const flowColor = dominantFlow === 'smooth' ? 'var(--accent)' : dominantFlow === 'moderate' ? 'var(--accent3)' : 'var(--warn)'
  const flowRows = [
    { label: 'Smooth',   count: flowCounts.smooth,   color: 'var(--accent)'  },
    { label: 'Moderate', count: flowCounts.moderate, color: 'var(--accent3)' },
    { label: 'Poor',     count: flowCounts.poor,     color: 'var(--warn)'    },
  ]
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="card-header">
        <div>
          <div className="card-title">Conversation Flow</div>
          <div className="card-desc">pause-based quality signal — how naturally calls progress</div>
        </div>
        <span className="tag tag-purple">ACOUSTIC</span>
      </div>

      {/* Dominant label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, paddingBottom: 16, borderBottom: '1px solid var(--border)' }}>
        <div style={{ width: 12, height: 12, borderRadius: '50%', background: flowColor, boxShadow: `0 0 10px ${flowColor}80`, flexShrink: 0 }} />
        <span style={{ fontFamily: "'Syne', sans-serif", fontSize: 22, fontWeight: 800, color: flowColor, letterSpacing: '-0.02em', textTransform: 'capitalize' }}>
          {dominantFlow || '—'}
        </span>
        <span style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted)', marginLeft: 2 }}>dominant</span>
      </div>

      {/* Breakdown bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
        {flowRows.map(({ label, count, color }) => {
          const pct = n ? (count / n) * 100 : 0
          return (
            <div key={label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 600, color }}>{label}</span>
                <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 11, color: 'var(--muted2)' }}>
                  {count} · {pct.toFixed(0)}%
                </span>
              </div>
              <div style={{ height: 6, background: 'var(--surface2)', borderRadius: 3, overflow: 'hidden' }}>
                <motion.div
                  style={{ height: '100%', background: color, borderRadius: 3 }}
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.8, ease: E }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Tooltip component for small info icons
function InfoTooltip({ text }) {
  const [visible, setVisible] = React.useState(false)
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', marginLeft: 6 }}
      onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)}>
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 15, height: 15, borderRadius: '50%',
        border: '1px solid var(--muted)', color: 'var(--muted)',
        fontSize: 9, fontWeight: 700, cursor: 'default', userSelect: 'none',
        fontFamily: 'Inter, sans-serif',
      }}>i</span>
      {visible && (
        <div style={{
          position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)',
          marginBottom: 8, width: 260, padding: '10px 12px',
          background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 8,
          fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'var(--muted2)', lineHeight: 1.6,
          zIndex: 100, pointerEvents: 'none',
        }}>
          {text}
        </div>
      )}
    </span>
  )
}

export default function AudioInsights() {
  const { insights: allInsights, emotions, topics, loading } = useClientData()
  const { applyTo, hasActiveFilters } = useFilters()
  const insights = applyTo(allInsights)
  const n = insights.length

  // Computed values
  const avgEngagement  = mean(insights, 'engagement_score')
  const avgSilence     = mean(insights, 'silence_ratio')
  const avgAgentTalk   = mean(insights, 'agent_talk_time_sec')
  const avgCustTalk    = mean(insights, 'customer_talk_time_sec')
  const avgSilSec      = mean(insights, 'total_silence_sec')
  const totalTalk      = avgAgentTalk + avgCustTalk + avgSilSec || 1
  const agentPct       = (avgAgentTalk / totalTalk) * 100
  const custPct        = (avgCustTalk  / totalTalk) * 100
  const silPct         = (avgSilSec   / totalTalk) * 100

  const flowCounts = { smooth: 0, moderate: 0, poor: 0 }
  insights.forEach(r => { if (r.conversation_flow) flowCounts[r.conversation_flow] = (flowCounts[r.conversation_flow] || 0) + 1 })
  const dominantFlow   = Object.entries(flowCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'unknown'
  const gaugeOffset    = 220 - (Math.min(avgEngagement, 100) / 100) * 220

  const pitchData  = [{ role: 'Agent', hz: mean(insights, 'agent_avg_pitch_hz') }, { role: 'Customer', hz: mean(insights, 'customer_avg_pitch_hz') }]
  const energyData = [{ role: 'Agent', rms: mean(insights, 'agent_avg_energy') * 1000 }, { role: 'Customer', rms: mean(insights, 'customer_avg_energy') * 1000 }]
  const histData   = buildHistogram(insights).map(b => ({ range: b.r, count: b.n }))
  const flowPie    = [
    { name: 'Smooth',   value: flowCounts.smooth,   color: '#6ee7b7' },
    { name: 'Moderate', value: flowCounts.moderate, color: '#fb923c' },
    { name: 'Poor',     value: flowCounts.poor,     color: '#f87171' },
  ].filter(d => d.value > 0)

  const SENT_COLORS = { positive: '#6ee7b7', neutral: '#818cf8', negative: '#f87171' }
  const sentCounts = {}; const sentEngMap = {}
  insights.forEach(r => {
    const s = (r.user_sentiment || 'unknown').toLowerCase()
    sentCounts[s] = (sentCounts[s] || 0) + 1
    if (!sentEngMap[s]) sentEngMap[s] = []
    sentEngMap[s].push(parseFloat(r.engagement_score) || 0)
  })
  const sentPie    = Object.entries(sentCounts).map(([name, value]) => ({ name: name.charAt(0).toUpperCase() + name.slice(1), value, color: SENT_COLORS[name] || '#64748b' })).filter(d => d.value > 0).sort((a, b) => b.value - a.value)
  const sentEngData = Object.entries(sentEngMap).map(([s, vals]) => ({ sentiment: s.charAt(0).toUpperCase() + s.slice(1), avgEngagement: vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length * 10) / 10 : 0, color: SENT_COLORS[s] || '#64748b' })).sort((a, b) => b.avgEngagement - a.avgEngagement)

  const trajCounts = { improving: 0, stable: 0, deteriorating: 0 }
  insights.forEach(r => { if (r.sentiment_trajectory) trajCounts[r.sentiment_trajectory] = (trajCounts[r.sentiment_trajectory] || 0) + 1 })
  const trajTotal       = (trajCounts.improving + trajCounts.stable + trajCounts.deteriorating) || 1
  const avgSpeakingRate = mean(insights, 'speaking_rate')
  const avgHesitations  = mean(insights, 'hesitation_count')
  const avgCustPitch    = mean(insights, 'customer_avg_pitch_hz')
  const avgAgentPitch   = mean(insights, 'agent_avg_pitch_hz')
  const stressCallCount = insights.filter(r => parseFloat(r.customer_avg_pitch_hz) > avgCustPitch * 1.2).length

  return (
    <div>
      {loading && <div className="loading-bar" />}

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Audio Insights</h2>
          <div className="page-sub">
            {hasActiveFilters
              ? `Filtered view · ${n} of ${allInsights.length} calls`
              : `Acoustic intelligence across ${n} processed calls`}
          </div>
        </div>
      </div>

      {/* ── Empty state — show when no audio insights are available yet ──── */}
      {!loading && allInsights.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24,
          }}
        >
          {['Emotion Detection', 'Engagement Scoring', 'Sentiment Trajectory', 'Silence Analysis', 'Speaking Rate', 'Acoustic Stress'].map(label => (
            <div key={label} style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 12, padding: '24px 20px',
              display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              <div style={{ height: 8, background: 'var(--surface2)', borderRadius: 4, width: '60%', animation: 'shimmer 1.5s infinite' }} />
              <div style={{ height: 80, background: 'var(--surface2)', borderRadius: 8, animation: 'shimmer 1.5s infinite' }} />
              <div style={{
                fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted)',
                textAlign: 'center', paddingTop: 8,
              }}>
                {label} · Audio processing in progress
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {/* ── Narrative Summary ─────────────────────────────────────────────── */}
      <NarrativeSummary
        n={n} avgEngagement={avgEngagement} dominantFlow={dominantFlow}
        flowCounts={flowCounts} agentPct={agentPct} custPct={custPct}
        hasFilter={hasActiveFilters}
      />

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 01 — Call Quality at a Glance                                       */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <StorySection
        num="01"
        title="Call Quality at a Glance"
        sub="Engagement score, conversation flow quality, and how participants share the floor"
      />

      <motion.div className="chart-grid-3col" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>

        {/* Engagement Gauge */}
        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Engagement Score</div>
              <div className="card-desc">Composite vocal metric — average across all calls</div>
            </div>
            <span className="tag tag-green">LIVE</span>
          </div>
          <div className="gauge-wrap">
            <svg viewBox="0 0 180 120" width="180" height="120">
              <defs>
                <linearGradient id="gg" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#818cf8" />
                  <stop offset="100%" stopColor="#6ee7b7" />
                </linearGradient>
              </defs>
              <path className="gauge-track" d="M 20 95 A 70 70 0 0 1 160 95" fill="none" stroke="#ffffff0f" strokeWidth="10" strokeLinecap="round"/>
              <path d="M 20 95 A 70 70 0 0 1 160 95" fill="none" stroke="url(#gg)" strokeWidth="10"
                strokeLinecap="round" strokeDasharray="220" strokeDashoffset={n ? gaugeOffset : 220}
                style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)' }}/>
              <text x="90" y="88" textAnchor="middle" className="gauge-val">{n ? avgEngagement.toFixed(0) : '—'}</text>
              <text x="90" y="105" textAnchor="middle" className="gauge-label">SCORE / 100</text>
            </svg>
          </div>
          {/* Context line */}
          {n > 0 && (
            <div style={{ marginTop: 8, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
              {avgEngagement >= 75 ? '✓ Strong engagement — calls are holding customer attention well.'
               : avgEngagement >= 55 ? '~ Moderate engagement — room to improve pacing and relevance.'
               : '↓ Low engagement — consider reviewing agent talk ratios and silence patterns.'}
            </div>
          )}
        </motion.div>

        {/* Conversation Flow — redesigned */}
        <motion.div variants={cardIn}>
          <ConversationFlowCard n={n} dominantFlow={dominantFlow} flowCounts={flowCounts} />
        </motion.div>

        {/* Talk Time Split */}
        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Talk Time Split</div>
              <div className="card-desc">Average agent vs customer vs silence ratio</div>
            </div>
            <span className="tag tag-orange">DIARISED</span>
          </div>
          <div className="talk-bars" style={{ marginTop: 8 }}>
            {[
              { label: 'Agent',    pct: agentPct, cls: 'bar-agent',    color: 'var(--accent2)' },
              { label: 'Customer', pct: custPct,  cls: 'bar-customer', color: 'var(--accent3)' },
              { label: 'Silence',  pct: silPct,   cls: 'bar-silence',  color: 'var(--muted)' },
            ].map(({ label, pct, cls, color }) => (
              <div className="talk-row" key={label}>
                <div className="talk-meta">
                  <span className="talk-role" style={{ color, fontFamily: 'Inter, sans-serif', fontSize: 13 }}>{label}</span>
                  <span className="talk-pct">{pct.toFixed(1)}%</span>
                </div>
                <div className="bar-track"><div className={`bar-fill ${cls}`} style={{ width: `${pct}%` }} /></div>
              </div>
            ))}
          </div>
          {n > 0 && (
            <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
              {agentPct > 65
                ? `Agents speak ${agentPct.toFixed(0)}% of the time — customers have limited floor share.`
                : agentPct < 45
                ? `Customers lead at ${custPct.toFixed(0)}% — agents may need to guide calls more actively.`
                : `Well-balanced: agents at ${agentPct.toFixed(0)}%, customers at ${custPct.toFixed(0)}%.`}
            </div>
          )}
        </motion.div>
      </motion.div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 02 — Score Distribution & Flow Quality                              */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <StorySection
        num="02"
        title="Score Distribution & Flow Quality"
        sub="Where calls cluster on the engagement scale, and how conversation quality breaks down"
      />

      <motion.div className="chart-grid" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Engagement Score Distribution</div>
              <div className="card-desc">Number of calls in each 20-point score band — shows where performance concentrates</div>
            </div>
            <span className="tag tag-purple">HISTOGRAM</span>
          </div>
          <div className="chart-wrap" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={histData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <defs>
                  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#818cf8"/>
                    <stop offset="100%" stopColor="#6ee7b7" stopOpacity={0.6}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                <XAxis dataKey="range" tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'Inter, sans-serif' }}/>
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false}/>
                <Tooltip {...TT} formatter={v => [v, 'calls']}/>
                <Bar dataKey="count" fill="url(#bg)" radius={[4, 4, 0, 0]}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {n > 0 && (() => {
            const peak = histData.reduce((a, b) => b.count > a.count ? b : a, histData[0])
            return (
              <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
                Most calls ({peak.count}) score in the <strong style={{ color: 'var(--text)' }}>{peak.range}</strong> band. {peak.range === '60–80' || peak.range === '80–100' ? 'Solid performance distribution.' : 'Engagement is skewed low — coaching may improve scores.'}
              </div>
            )
          })()}
        </motion.div>

        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Flow Quality Breakdown</div>
              <div className="card-desc">How calls distribute across smooth, moderate, and poor conversation quality</div>
            </div>
            <span className="tag tag-green">FLOW</span>
          </div>
          <div className="chart-wrap" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={flowPie} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value" paddingAngle={3}>
                  {flowPie.map((d, i) => <Cell key={i} fill={d.color}/>)}
                </Pie>
                <Tooltip {...TT} formatter={(v, n) => [v + ' calls', n]}/>
                <Legend iconSize={10} formatter={v => <span style={{ color: '#94a3b8', fontSize: 12, fontFamily: 'Inter, sans-serif' }}>{v}</span>}/>
              </PieChart>
            </ResponsiveContainer>
          </div>
          {n > 0 && (
            <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
              {flowCounts.smooth > flowCounts.poor
                ? `${((flowCounts.smooth / n) * 100).toFixed(0)}% of calls flow smoothly. Strong overall quality.`
                : `${((flowCounts.poor / n) * 100).toFixed(0)}% of calls show poor flow. Focus coaching on natural pausing.`}
            </div>
          )}
        </motion.div>
      </motion.div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 03 — Voice Dynamics                                                 */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <StorySection
        num="03"
        title="Voice Dynamics"
        sub="Pitch and vocal energy reveal emotional state, confidence, and speaker arousal patterns"
      />

      <motion.div className="chart-grid" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Average Pitch by Role</div>
              <div className="card-desc">Fundamental frequency (Hz) — higher pitch signals emotional arousal or stress</div>
            </div>
            <span className="tag tag-purple">F0</span>
          </div>
          <div className="chart-wrap" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={pitchData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                <XAxis dataKey="role" tick={{ fill: '#64748b', fontSize: 12, fontFamily: 'Inter, sans-serif' }}/>
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} unit=" Hz"/>
                <Tooltip {...TT} formatter={v => [`${v.toFixed(1)} Hz`, 'Avg Pitch']}/>
                <Bar dataKey="hz" radius={[6, 6, 0, 0]} maxBarSize={80}>
                  <Cell fill="#818cf8"/><Cell fill="#fb923c"/>
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {pitchData[0].hz > 0 && (
            <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
              {pitchData[1].hz > pitchData[0].hz
                ? `Customers average ${(pitchData[1].hz - pitchData[0].hz).toFixed(0)} Hz higher than agents — elevated arousal or concern.`
                : `Agents average ${(pitchData[0].hz - pitchData[1].hz).toFixed(0)} Hz higher — could reflect enthusiasm or assertiveness.`}
            </div>
          )}
        </motion.div>

        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Average Vocal Energy by Role</div>
              <div className="card-desc">RMS energy ×1000 — measures speaker emphasis, confidence, and volume</div>
            </div>
            <span className="tag tag-green">RMS</span>
          </div>
          <div className="chart-wrap" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={energyData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                <XAxis dataKey="role" tick={{ fill: '#64748b', fontSize: 12, fontFamily: 'Inter, sans-serif' }}/>
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }}/>
                <Tooltip {...TT} formatter={v => [`${v.toFixed(3)}`, 'Energy ×1000']}/>
                <Bar dataKey="rms" radius={[6, 6, 0, 0]} maxBarSize={80}>
                  <Cell fill="#6ee7b7"/><Cell fill="#fbbf24"/>
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {energyData[0].rms > 0 && (
            <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
              {energyData[0].rms > energyData[1].rms
                ? `Agents speak with ${((energyData[0].rms / energyData[1].rms - 1) * 100).toFixed(0)}% more vocal energy than customers.`
                : `Customers are more vocally expressive — agents could increase energy to match engagement.`}
            </div>
          )}
        </motion.div>
      </motion.div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 04 — Call Topics (conditional)                                      */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {topics?.distribution?.length > 0 && (
        <>
          <StorySection
            num="04"
            title="Why Customers Are Calling"
            sub="Topic classification reveals the primary intent behind each call — useful for staffing and script optimisation"
          />
          <motion.div className="chart-grid" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Topic Distribution</div>
                  <div className="card-desc">{topics.total} calls classified — call intent ranked by volume</div>
                </div>
                <span className="tag tag-purple">TOPICS</span>
              </div>
              <div className="chart-wrap" style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={topics.distribution.map(d => ({ name: d.topic.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()), count: d.count, pct: d.pct, color: TOPIC_COLORS[d.topic] || '#64748b' }))}
                    layout="vertical" margin={{ top: 5, right: 60, left: 110, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" horizontal={false}/>
                    <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false}/>
                    <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12, fontFamily: 'Inter, sans-serif' }} width={110}/>
                    <Tooltip {...TT} formatter={(v, _, props) => [`${v} calls (${props.payload.pct}%)`, 'Count']}/>
                    <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22}>
                      {topics.distribution.map((d, i) => <Cell key={i} fill={TOPIC_COLORS[d.topic] || '#64748b'}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Topic Share Breakdown</div>
                  <div className="card-desc">Percentage of total volume per call intent</div>
                </div>
                <span className="tag tag-green">INTENT</span>
              </div>
              <div style={{ padding: '8px 0' }}>
                {topics.distribution.map(d => {
                  const color = TOPIC_COLORS[d.topic] || '#64748b'
                  const label = d.topic.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
                  return (
                    <div key={d.topic} style={{ marginBottom: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                        <span style={{ fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 500, color }}>{label}</span>
                        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 11, color: 'var(--muted2)' }}>{d.count} calls · {d.pct}%</span>
                      </div>
                      <div style={{ height: 6, background: 'var(--surface2)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: `${d.pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.8s ease' }}/>
                      </div>
                    </div>
                  )
                })}
              </div>
            </motion.div>
          </motion.div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 05 — Call Quality Grades (conditional)                              */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {(() => {
        const scores = insights.map(r => r.quality_score).filter(s => s != null)
        if (scores.length === 0) return null
        const avgQ = Math.round(scores.reduce((s, v) => s + v, 0) / scores.length)
        const topGrade = { A: 0, B: 0, C: 0, D: 0, F: 0 }
        insights.forEach(r => { if (r.quality_grade) topGrade[r.quality_grade]++ })
        const gradeData = Object.entries(topGrade).map(([grade, count]) => ({ grade, count, color: GRADE_COLORS_MAP[grade] })).filter(d => d.count > 0)
        const dominantGrade = gradeData.sort((a, b) => b.count - a.count)[0]?.grade || '—'

        return (
          <>
            <StorySection
              num={topics?.distribution?.length > 0 ? '05' : '04'}
              title="Call Quality Grades"
              sub={`Composite quality score across ${scores.length} calls — grades A (excellent) to F (critical)`}
            />
            <motion.div className="chart-grid-3col" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
              <motion.div className="card" variants={cardIn}>
                <div className="card-header">
                  <div>
                    <div className="card-title">Average Quality Score</div>
                    <div className="card-desc">Composite 0–100 across {scores.length} calls</div>
                  </div>
                  <span className="tag tag-green">QUALITY</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '20px 0' }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 60, fontWeight: 800, color: GRADE_COLORS_MAP[dominantGrade] || '#818cf8', lineHeight: 1, letterSpacing: '-0.04em' }}>{avgQ}</div>
                    <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted)', marginTop: 8 }}>out of 100 · Grade {dominantGrade}</div>
                  </div>
                </div>
              </motion.div>
              <motion.div className="card" style={{ gridColumn: 'span 2' }} variants={cardIn}>
                <div className="card-header">
                  <div>
                    <div className="card-title">Grade Distribution</div>
                    <div className="card-desc">How calls spread across quality grades — A is excellent, F is critical</div>
                  </div>
                  <span className="tag tag-purple">GRADES</span>
                </div>
                <div className="chart-wrap" style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={['A','B','C','D','F'].map(g => ({ grade: g, count: topGrade[g], color: GRADE_COLORS_MAP[g] }))} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                      <XAxis dataKey="grade" tick={{ fill: '#94a3b8', fontSize: 14, fontWeight: 700, fontFamily: 'Inter, sans-serif' }}/>
                      <YAxis tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false}/>
                      <Tooltip {...TT} formatter={v => [v + ' calls', 'Count']}/>
                      <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={60}>
                        {['A','B','C','D','F'].map((g, i) => <Cell key={i} fill={GRADE_COLORS_MAP[g]}/>)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            </motion.div>
          </>
        )
      })()}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 06 — Emotion Analysis (conditional)                                 */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {emotions && (emotions.utterance_distribution?.length > 0 || emotions.call_distribution?.length > 0) && (() => {
        const uttDist  = (emotions.utterance_distribution || []).map(d => ({ ...d, color: EMOTION_COLORS[d.emotion] || '#64748b', name: d.emotion.charAt(0).toUpperCase() + d.emotion.slice(1) }))
        const callDist = (emotions.call_distribution || []).map(d => ({ ...d, color: EMOTION_COLORS[d.emotion] || '#64748b', name: d.emotion.charAt(0).toUpperCase() + d.emotion.slice(1) }))
        const trendData = emotions.weekly_trend || []
        const trendEmotions = [...new Set(trendData.flatMap(w => Object.keys(w).filter(k => k !== 'week')))]
        const topEmotion = uttDist[0]
        const totalUtt = uttDist.reduce((s, d) => s + d.count, 0)

        return (
          <>
            <StorySection
              num="06"
              title="Customer Emotion Analysis"
              sub="emotion2vec classification per utterance and call — reveals how customers feel during conversations"
            />
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: -8, paddingLeft: 2 }}>
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted)', letterSpacing: '0.02em' }}>Emotion Detection</span>
              <InfoTooltip text="Emotions are derived from vocal pitch and energy patterns detected in the audio recording — not from transcript text. Higher pitch and energy patterns signal potential frustration or stress." />
            </div>
            <motion.div className="chart-grid" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
              <motion.div className="card" variants={cardIn}>
                <div className="card-header">
                  <div>
                    <div className="card-title">Emotion Per Utterance</div>
                    <div className="card-desc">Emotion detected on each customer turn — shows moment-to-moment mood</div>
                  </div>
                  <span className="tag tag-green">UTTERANCES</span>
                </div>
                <div className="chart-wrap" style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={uttDist} cx="50%" cy="50%" innerRadius={58} outerRadius={85} dataKey="count" paddingAngle={3}>
                        {uttDist.map((d, i) => <Cell key={i} fill={d.color}/>)}
                      </Pie>
                      <Tooltip {...TT} formatter={(v, name) => [v + ' utterances', name]}/>
                      <Legend iconSize={10} formatter={v => <span style={{ color: '#94a3b8', fontSize: 12, fontFamily: 'Inter, sans-serif' }}>{v}</span>}/>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {topEmotion && (
                  <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
                    Most frequent: <strong style={{ color: topEmotion.color }}>{topEmotion.name}</strong> in {((topEmotion.count / totalUtt) * 100).toFixed(1)}% of customer turns
                  </div>
                )}
              </motion.div>

              <motion.div className="card" variants={cardIn}>
                <div className="card-header">
                  <div>
                    <div className="card-title">Dominant Emotion Per Call</div>
                    <div className="card-desc">The most frequent emotion across each full call — overall call mood</div>
                  </div>
                  <span className="tag tag-purple">CALLS</span>
                </div>
                <div className="chart-wrap" style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={callDist} layout="vertical" margin={{ top: 5, right: 20, left: 68, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" horizontal={false}/>
                      <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }}/>
                      <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12, fontFamily: 'Inter, sans-serif' }} width={68}/>
                      <Tooltip {...TT} formatter={v => [v + ' calls', 'Count']}/>
                      <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
                        {callDist.map((d, i) => <Cell key={i} fill={d.color}/>)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            </motion.div>

            {trendData.length > 1 && (
              <motion.div className="card" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-40px' }} transition={{ duration: 0.42, ease: E }}>
                <div className="card-header">
                  <div>
                    <div className="card-title">Weekly Emotion Trend</div>
                    <div className="card-desc">Dominant customer emotion per call over the last 8 weeks — spot mood shifts over time</div>
                  </div>
                  <span className="tag tag-orange">TREND</span>
                </div>
                <div className="chart-wrap" style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={trendData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                      <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'Inter, sans-serif' }}/>
                      <YAxis tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false}/>
                      <Tooltip {...TT} formatter={(v, name) => [v + ' calls', name]}/>
                      <Legend iconSize={10} formatter={v => <span style={{ color: '#94a3b8', fontSize: 12, fontFamily: 'Inter, sans-serif' }}>{v.charAt(0).toUpperCase() + v.slice(1)}</span>}/>
                      {trendEmotions.map(e => (
                        <Bar key={e} dataKey={e} stackId="a" fill={EMOTION_COLORS[e] || '#64748b'} radius={trendEmotions.indexOf(e) === trendEmotions.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}/>
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            )}
          </>
        )
      })()}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 07 — Sentiment Analysis                                             */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <StorySection
        num="07"
        title="Sentiment Analysis"
        sub="Caller sentiment polarity and its correlation with engagement — positive callers are easier to engage"
      />
      <motion.div className="chart-grid" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Caller Sentiment Distribution</div>
              <div className="card-desc">Positive / neutral / negative — derived from AI transcript analysis</div>
            </div>
            <span className="tag tag-green">SENTIMENT</span>
          </div>
          <div className="chart-wrap" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={sentPie} cx="50%" cy="50%" innerRadius={58} outerRadius={85} dataKey="value" paddingAngle={3}>
                  {sentPie.map((d, i) => <Cell key={i} fill={d.color}/>)}
                </Pie>
                <Tooltip {...TT} formatter={(v, name) => [v + ' calls', name]}/>
                <Legend iconSize={10} formatter={v => <span style={{ color: '#94a3b8', fontSize: 12, fontFamily: 'Inter, sans-serif' }}>{v}</span>}/>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
            {sentPie.map(d => (
              <div key={d.name} style={{ flex: 1, minWidth: 80, background: 'var(--surface2)', borderRadius: 8, padding: '10px 14px', border: '1px solid var(--border2)' }}>
                <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{d.name}</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 22, fontWeight: 800, color: d.color, letterSpacing: '-0.02em' }}>{d.value}</div>
                <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'var(--muted2)' }}>{n ? ((d.value / n) * 100).toFixed(1) : 0}% of calls</div>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div className="card" variants={cardIn}>
          <div className="card-header">
            <div>
              <div className="card-title">Engagement by Sentiment</div>
              <div className="card-desc">Does caller mood affect engagement? This shows the correlation</div>
            </div>
            <span className="tag tag-purple">CORRELATION</span>
          </div>
          <div className="chart-wrap" style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={sentEngData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                <XAxis dataKey="sentiment" tick={{ fill: '#64748b', fontSize: 12, fontFamily: 'Inter, sans-serif' }}/>
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} domain={[0, 100]}/>
                <Tooltip {...TT} formatter={v => [`${v}/100`, 'Avg Engagement']}/>
                <Bar dataKey="avgEngagement" radius={[6, 6, 0, 0]} maxBarSize={80}>
                  {sentEngData.map((d, i) => <Cell key={i} fill={d.color}/>)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {sentEngData.length > 1 && (
            <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
              <strong style={{ color: 'var(--text)' }}>{sentEngData[0].sentiment}</strong> callers score {sentEngData[0].avgEngagement.toFixed(1)}/100 — {(sentEngData[0].avgEngagement - sentEngData[sentEngData.length - 1].avgEngagement).toFixed(1)} pts above <strong style={{ color: 'var(--text)' }}>{sentEngData[sentEngData.length - 1].sentiment.toLowerCase()}</strong> callers. Sentiment strongly predicts engagement outcomes.
            </div>
          )}
        </motion.div>
      </motion.div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 08 — Sentiment Trajectory                                           */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {n > 0 && trajTotal > 1 && (
        <>
          <StorySection
            num="08"
            title="Sentiment Trajectory"
            sub="How caller emotional state evolves over each call — improving signals positive de-escalation, deteriorating flags friction"
          />
          <motion.div className="chart-grid" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Trajectory Distribution</div>
                  <div className="card-desc">Emotional arc per call — opening vs close sentiment shift</div>
                </div>
                <span className="tag tag-green">TRAJECTORY</span>
              </div>
              <div style={{ padding: '8px 0', display: 'flex', flexDirection: 'column', gap: 14, marginTop: 8 }}>
                {[
                  { label: 'Improving',     count: trajCounts.improving,     color: '#22c55e' },
                  { label: 'Stable',        count: trajCounts.stable,        color: '#818cf8' },
                  { label: 'Deteriorating', count: trajCounts.deteriorating, color: '#f87171' },
                ].map(({ label, count, color }) => {
                  const pct = (count / trajTotal) * 100
                  return (
                    <div key={label}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                        <span style={{ fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 600, color }}>{label}</span>
                        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 11, color: 'var(--muted2)' }}>{count} · {pct.toFixed(0)}%</span>
                      </div>
                      <div style={{ height: 6, background: 'var(--surface2)', borderRadius: 3, overflow: 'hidden' }}>
                        <motion.div style={{ height: '100%', background: color, borderRadius: 3 }}
                          initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8, ease: E }}/>
                      </div>
                    </div>
                  )
                })}
              </div>
              <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
                {trajCounts.improving > trajCounts.deteriorating
                  ? `${((trajCounts.improving / trajTotal) * 100).toFixed(0)}% of calls end on a positive note — agents are successfully building rapport.`
                  : `${((trajCounts.deteriorating / trajTotal) * 100).toFixed(0)}% of calls deteriorate — review agent responses in the second half of calls.`}
              </div>
            </motion.div>

            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Trajectory Volume</div>
                  <div className="card-desc">Call count per trajectory type</div>
                </div>
                <span className="tag tag-purple">BREAKDOWN</span>
              </div>
              <div className="chart-wrap" style={{ height: 220 }}>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={[
                      { name: 'Improving',     count: trajCounts.improving },
                      { name: 'Stable',        count: trajCounts.stable },
                      { name: 'Deteriorating', count: trajCounts.deteriorating },
                    ]}
                    margin={{ top: 5, right: 20, left: -10, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                    <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'Inter, sans-serif' }}/>
                    <YAxis tick={{ fill: '#64748b', fontSize: 11 }} allowDecimals={false}/>
                    <Tooltip {...TT} formatter={v => [v + ' calls', 'Count']}/>
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={60}>
                      <Cell fill="#22c55e"/><Cell fill="#818cf8"/><Cell fill="#f87171"/>
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* 09 — Acoustic Stress Indicators                                     */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {n > 0 && (avgCustPitch > 0 || avgSpeakingRate > 0 || avgHesitations > 0) && (
        <>
          <StorySection
            num="09"
            title="Acoustic Stress Indicators"
            sub="Pitch variance and energy patterns associated with elevated emotional states, plus speaking rate and hesitation markers"
          />

          {/* Positive / coaching framing summary card */}
          <motion.div
            initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }} transition={{ duration: 0.38 }}
            style={{
              marginBottom: 16, padding: '14px 18px',
              background: stressCallCount > n * 0.3
                ? 'rgba(248, 113, 113, 0.06)'
                : stressCallCount > n * 0.15
                ? 'rgba(251, 191, 36, 0.06)'
                : 'rgba(34, 197, 94, 0.06)',
              border: `1px solid ${stressCallCount > n * 0.3 ? '#f8717130' : stressCallCount > n * 0.15 ? '#fbbf2430' : '#22c55e30'}`,
              borderRadius: 10,
              fontFamily: 'Inter, sans-serif', fontSize: 13, lineHeight: 1.6,
              color: stressCallCount > n * 0.3 ? '#f87171' : stressCallCount > n * 0.15 ? '#fbbf24' : '#22c55e',
            }}>
            {stressCallCount <= n * 0.15
              ? `${n ? (100 - (stressCallCount / n * 100)).toFixed(0) : 0}% of your calls show low stress indicators — your agent is handling calls well.`
              : stressCallCount <= n * 0.3
              ? `We detected elevated stress signals in ${n ? ((stressCallCount / n) * 100).toFixed(0) : 0}% of calls. Review the flagged calls below for coaching opportunities.`
              : `We detected elevated stress signals in ${n ? ((stressCallCount / n) * 100).toFixed(0) : 0}% of calls. Review flagged calls — this is a key coaching opportunity.`}
          </motion.div>

          <motion.div className="chart-grid-3col" variants={rowStagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }}>
            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Elevated-Pitch Calls</div>
                  <div className="card-desc">Calls where customer pitch exceeds dataset average by &gt;20% — vocal stress proxy</div>
                </div>
                <span className="tag tag-orange">STRESS</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '20px 0', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 56, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1,
                  color: stressCallCount > n * 0.3 ? '#f87171' : stressCallCount > n * 0.15 ? '#fbbf24' : '#22c55e' }}>
                  {stressCallCount}
                </div>
                <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted)' }}>
                  of {n} calls · {n ? ((stressCallCount / n) * 100).toFixed(1) : 0}%
                </div>
              </div>
              <div style={{ padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
                {stressCallCount > n * 0.3
                  ? 'Elevated stress detected — identify recurring pain points as a coaching opportunity.'
                  : stressCallCount > n * 0.15
                  ? 'Some elevated-pitch calls detected — isolated friction worth reviewing with your agent.'
                  : 'Low stress signal — your agent is keeping customers calm. Strong performance.'}
              </div>
            </motion.div>

            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Speaking Rate & Hesitation</div>
                  <div className="card-desc">Avg words/min and hesitation events per call — signals uncertainty or discomfort</div>
                </div>
                <span className="tag tag-purple">RATE</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginTop: 16 }}>
                {[
                  { label: 'Avg Speaking Rate', value: avgSpeakingRate > 0 ? `${avgSpeakingRate.toFixed(1)} w/min` : '—', color: 'var(--accent2)' },
                  { label: 'Avg Hesitations / Call', value: avgHesitations > 0 ? avgHesitations.toFixed(1) : '—', color: avgHesitations > 5 ? 'var(--warn)' : 'var(--accent)' },
                ].map(({ label, value, color }) => (
                  <div key={label} style={{ padding: '12px 16px', background: 'var(--surface2)', borderRadius: 8, border: '1px solid var(--border2)' }}>
                    <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>{label}</div>
                    <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 28, fontWeight: 800, color, letterSpacing: '-0.02em' }}>{value}</div>
                  </div>
                ))}
              </div>
            </motion.div>

            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div>
                  <div className="card-title">Pitch Delta</div>
                  <div className="card-desc">Customer vs agent pitch gap — wide delta may indicate emotional asymmetry</div>
                </div>
                <span className="tag tag-green">F0 DELTA</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '20px 0', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 40, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--accent3)', lineHeight: 1 }}>
                  {avgCustPitch > 0 && avgAgentPitch > 0 ? `${Math.abs(avgCustPitch - avgAgentPitch).toFixed(1)} Hz` : '—'}
                </div>
                <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted)' }}>
                  {avgCustPitch > avgAgentPitch ? 'customer higher' : avgAgentPitch > avgCustPitch ? 'agent higher' : ''}
                </div>
              </div>
              <div style={{ padding: '10px 14px', background: 'var(--surface2)', borderRadius: 8, fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--muted2)', lineHeight: 1.6 }}>
                {avgCustPitch > 0 && avgAgentPitch > 0
                  ? `Agent: ${avgAgentPitch.toFixed(1)} Hz · Customer: ${avgCustPitch.toFixed(1)} Hz. ${Math.abs(avgCustPitch - avgAgentPitch) > 40 ? 'Significant pitch asymmetry — customer may be emotionally elevated.' : 'Pitch levels are closely matched.'}`
                  : 'Pitch data not yet available for this call set.'}
              </div>
            </motion.div>
          </motion.div>
        </>
      )}

      {/* section 10 (Call Records) moved — see Calls page */}
    </div>
  )
}

