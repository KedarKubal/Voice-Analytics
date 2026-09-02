import { useNavigate } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import { useClientData } from '../../hooks/useClientData'
import { useFilters } from '../../context/FilterContext'
import api from '../../api/apiClient'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
  AreaChart, Area,
} from 'recharts'
import '../../App.css'

const TT = {
  contentStyle: { background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 8, fontSize: 12 },
  labelStyle:   { color: 'var(--tooltip-text)' },
  itemStyle:    { color: 'var(--tooltip-item)' },
  cursor:       { fill: 'var(--hover-bg)' },
}

function buildHistogram(insights) {
  const b = [
    { range: '0–20',   count: 0 },
    { range: '20–40',  count: 0 },
    { range: '40–60',  count: 0 },
    { range: '60–80',  count: 0 },
    { range: '80–100', count: 0 },
  ]
  insights.forEach(r => {
    const s = parseFloat(r.engagement_score) || 0
    b[Math.min(Math.floor(s / 20), 4)].count++
  })
  return b
}

const CLIENT_DISPLAY_NAMES = {
  'client_heya_001': 'Artel Apartments',
  'client_heya_002': 'MVAA Legal',
}

function mean(arr, key) {
  const vals = arr.map(r => parseFloat(r[key]) || 0).filter(v => v > 0)
  return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0
}

const cardVariant = {
  hidden: { opacity: 0, y: 20 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
}

const fadeUp = {
  hidden: { opacity: 0, y: 22 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
}

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
}

function StoryCard({ headline, sub, color = 'var(--accent2)', accent }) {
  return (
    <motion.div className="story-card" variants={cardVariant}>
      <div className="story-accent" style={{ background: accent || color }} />
      <div className="story-headline" style={{ color }}>{headline}</div>
      <div className="story-sub">{sub}</div>
    </motion.div>
  )
}

function flowColor(f) {
  return f === 'smooth' ? 'var(--accent)' : f === 'moderate' ? 'var(--accent3)' : 'var(--warn)'
}

// ── Agent Performance Chart ───────────────────────────────────────────────────
function AgentPerformanceChart({ insights }) {
  const [selected, setSelected] = useState('all')

  const agentStats = useMemo(() => {
    const map = {}
    insights.forEach(r => {
      const name = r.agent_name
      if (!name) return
      if (!map[name]) map[name] = { name, total: 0, successful: 0, engSum: 0, hesSum: 0, silSum: 0, intSum: 0 }
      map[name].total++
      if (r.call_successful === true) map[name].successful++
      map[name].engSum  += parseFloat(r.engagement_score)    || 0
      map[name].hesSum  += parseFloat(r.hesitation_count)    || 0
      map[name].silSum  += parseFloat(r.silence_ratio)       || 0
      map[name].intSum  += parseFloat(r.interruption_count)  || 0
    })
    return Object.values(map)
      .filter(a => a.total > 0)
      .map(a => ({
        name:              a.name,
        total_calls:       a.total,
        success_rate:      Math.round(a.successful / a.total * 1000) / 10,
        avg_engagement:    Math.round(a.engSum  / a.total * 10) / 10,
        avg_hesitations:   Math.round(a.hesSum  / a.total * 10) / 10,
        avg_silence_pct:   Math.round(a.silSum  / a.total * 1000) / 10,
        avg_interruptions: Math.round(a.intSum  / a.total * 10) / 10,
      }))
      .sort((a, b) => b.success_rate - a.success_rate)
  }, [insights])

  if (agentStats.length === 0) return null

  const agentNames  = agentStats.map(a => a.name)
  const selectedStat = selected === 'all' ? null : agentStats.find(a => a.name === selected)

  const compareData = agentStats.map(a => ({
    name:               a.name,
    'Success Rate (%)': a.success_rate,
    'Avg Engagement':   a.avg_engagement,
    calls:              a.total_calls,
  }))

  const metricBars = selectedStat ? [
    {
      label: 'Success Rate', value: selectedStat.success_rate, max: 100, unit: '%',
      color: selectedStat.success_rate >= 70 ? '#6ee7b7' : selectedStat.success_rate >= 40 ? '#fb923c' : '#f87171',
    },
    {
      label: 'Avg Engagement', value: selectedStat.avg_engagement, max: 100, unit: '/100',
      color: selectedStat.avg_engagement >= 70 ? '#6ee7b7' : selectedStat.avg_engagement >= 45 ? '#818cf8' : '#f87171',
    },
    {
      label: 'Avg Silence', value: selectedStat.avg_silence_pct, max: 100, unit: '%',
      color: selectedStat.avg_silence_pct <= 15 ? '#6ee7b7' : selectedStat.avg_silence_pct <= 35 ? '#fb923c' : '#f87171',
    },
    {
      label: 'Hesitations / call', value: selectedStat.avg_hesitations, max: 25, unit: '',
      color: selectedStat.avg_hesitations <= 5 ? '#6ee7b7' : selectedStat.avg_hesitations <= 12 ? '#fb923c' : '#f87171',
    },
    {
      label: 'Interruptions / call', value: selectedStat.avg_interruptions, max: 10, unit: '',
      color: selectedStat.avg_interruptions <= 2 ? '#6ee7b7' : selectedStat.avg_interruptions <= 5 ? '#fb923c' : '#f87171',
    },
  ] : []

  return (
    <motion.div
      className="card"
      variants={fadeUp}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: '-40px' }}
      style={{ marginTop: 8, marginBottom: 0 }}
    >
      <div className="card-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="card-title">Agent Performance</div>
          <div className="card-desc">
            {selected === 'all'
              ? 'success rate and engagement across all agents'
              : `${selected} — ${selectedStat?.total_calls ?? 0} calls`}
          </div>
        </div>
        <span className="tag tag-purple">AGENTS</span>
      </div>

      {/* Selector pills */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
        {['all', ...agentNames].map(name => (
          <button
            key={name}
            onClick={() => setSelected(name)}
            style={{
              padding: '5px 14px',
              borderRadius: 20,
              border: '1px solid',
              fontSize: 12,
              cursor: 'pointer',
              fontFamily: "'DM Mono', monospace",
              transition: 'all 0.15s ease',
              borderColor: selected === name ? 'var(--accent2)' : 'var(--border2)',
              background:  selected === name ? 'rgba(129,140,248,0.15)' : 'transparent',
              color:       selected === name ? 'var(--accent2)' : 'var(--muted)',
            }}
          >
            {name === 'all' ? 'All Agents' : name}
          </button>
        ))}
      </div>

      {/* All-agents: grouped bar chart */}
      {selected === 'all' && (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={compareData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
            <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }}/>
            <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 11 }}/>
            <Tooltip
              {...TT}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const d = compareData.find(x => x.name === label)
                return (
                  <div style={{ ...TT.contentStyle, padding: '10px 14px' }}>
                    <div style={{ color: '#f1f5f9', fontWeight: 600, marginBottom: 4, fontSize: 13 }}>{label}</div>
                    <div style={{ color: '#64748b', fontSize: 11, marginBottom: 6 }}>{d?.calls} calls</div>
                    {payload.map(p => (
                      <div key={p.name} style={{ color: p.color, fontSize: 12, lineHeight: 1.6 }}>
                        {p.name}: <strong>{p.value}{p.name === 'Success Rate (%)' ? '%' : '/100'}</strong>
                      </div>
                    ))}
                  </div>
                )
              }}
            />
            <Legend iconSize={10} formatter={v => <span style={{ color: '#94a3b8', fontSize: 11 }}>{v}</span>}/>
            <Bar dataKey="Success Rate (%)" fill="#6ee7b7" radius={[4, 4, 0, 0]} maxBarSize={52}/>
            <Bar dataKey="Avg Engagement"   fill="#818cf8" radius={[4, 4, 0, 0]} maxBarSize={52}/>
          </BarChart>
        </ResponsiveContainer>
      )}

      {/* Individual agent: KPI row + progress bars */}
      {selected !== 'all' && selectedStat && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Mini KPI strip */}
          <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', paddingBottom: 16, borderBottom: '1px solid var(--line-faint)' }}>
            {[
              { val: selectedStat.total_calls,     label: 'total calls',  color: '#f1f5f9' },
              { val: `${selectedStat.success_rate}%`, label: 'success rate',
                color: selectedStat.success_rate >= 70 ? '#6ee7b7' : selectedStat.success_rate >= 40 ? '#fb923c' : '#f87171' },
              { val: `${selectedStat.avg_engagement}/100`, label: 'avg engagement', color: 'var(--accent2)' },
            ].map(({ val, label, color }) => (
              <div key={label} style={{ fontSize: 11, color: 'var(--muted)' }}>
                <span style={{ color, fontSize: 18, fontWeight: 700, display: 'block', lineHeight: 1.2 }}>{val}</span>
                {label}
              </div>
            ))}
          </div>

          {/* Metric progress bars */}
          {metricBars.map(m => {
            const pct = Math.min(m.value / m.max * 100, 100)
            return (
              <div key={m.label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>{m.label}</span>
                  <span style={{ fontSize: 12, fontFamily: "'DM Mono'", color: '#f1f5f9' }}>
                    {m.value}{m.unit}
                  </span>
                </div>
                <div style={{ height: 6, background: 'var(--track-bg)', borderRadius: 3, overflow: 'hidden' }}>
                  <motion.div
                    style={{ height: '100%', borderRadius: 3, background: m.color }}
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.55, ease: 'easeOut' }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </motion.div>
  )
}

// ── Export helpers ────────────────────────────────────────────────────────────
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
  const res  = await api.get(`/export/report/${clientId}`, { responseType: 'blob' })
  const url  = URL.createObjectURL(new Blob([res.data], { type: 'text/html' }))
  window.open(url, '_blank')
}

const PRIORITY_META = {
  critical: { color: 'var(--warn)',    bg: '#f8717112', border: '#f8717130', label: 'CRITICAL' },
  warning:  { color: 'var(--accent3)', bg: '#fb923c12', border: '#fb923c30', label: 'WARNING'  },
  info:     { color: 'var(--accent2)', bg: '#818cf812', border: '#818cf830', label: 'INFO'     },
}

const TREND_META = {
  worsening: { icon: '↓', color: 'var(--warn)'    },
  stable:    { icon: '→', color: 'var(--muted)'   },
  improving: { icon: '↑', color: 'var(--accent)'  },
}

export default function Home() {
  const { user } = useAuth()
  const { stats, insights: allInsights, loading, clientId } = useClientData()
  const { applyTo, hasActiveFilters } = useFilters()
  const navigate = useNavigate()

  const insights = applyTo(allInsights)

  const [recs,        setRecs]        = useState([])
  const [recsLoading, setRecsLoading] = useState(false)
  const [expanded,    setExpanded]    = useState(null)

  useEffect(() => {
    if (!clientId) return
    setRecsLoading(true)
    api.get(`/client-alerts/${clientId}`)
      .then(r => setRecs(r.data.alerts || []))
      .catch(() => setRecs([]))
      .finally(() => setRecsLoading(false))
  }, [clientId])

  const n             = insights.length
  const avgEngagement = mean(insights, 'engagement_score')
  const avgSilence    = mean(insights, 'silence_ratio')

  // When filters are active, derive KPIs from the filtered set so story cards
  // stay consistent with the charts below them.
  const filteredSuccessCount = insights.filter(r => r.call_successful === true).length
  const successRateDisplay   = hasActiveFilters
    ? (n ? Math.round(filteredSuccessCount / n * 100) : 0)
    : (stats?.success_rate ?? '—')
  const totalCallsDisplay    = hasActiveFilters ? n : (stats?.total_calls ?? n)

  const flowCounts = { smooth: 0, moderate: 0, poor: 0 }
  const trajCounts = { improving: 0, stable: 0, deteriorating: 0 }
  insights.forEach(r => {
    if (r.conversation_flow)     flowCounts[r.conversation_flow]     = (flowCounts[r.conversation_flow]     || 0) + 1
    if (r.sentiment_trajectory)  trajCounts[r.sentiment_trajectory]  = (trajCounts[r.sentiment_trajectory]  || 0) + 1
  })
  const dominated = Object.entries(flowCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || '—'

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const clientName = CLIENT_DISPLAY_NAMES[stats?.client_id]
    || CLIENT_DISPLAY_NAMES[user?.client_id]
    || user?.name
    || 'there'

  const recent = [...insights]
    .sort((a, b) => (b.start_timestamp || 0) - (a.start_timestamp || 0))
    .slice(0, 6)

  const histData = buildHistogram(insights)
  const flowPieData = [
    { name: 'Smooth',   value: flowCounts.smooth,   color: '#6ee7b7' },
    { name: 'Moderate', value: flowCounts.moderate, color: '#fb923c' },
    { name: 'Poor',     value: flowCounts.poor,     color: '#f87171' },
  ].filter(d => d.value > 0)

  const trajData = [
    { name: 'Improving',     value: trajCounts.improving     || 0, fill: '#6ee7b7' },
    { name: 'Stable',        value: trajCounts.stable        || 0, fill: '#818cf8' },
    { name: 'Deteriorating', value: trajCounts.deteriorating || 0, fill: '#f87171' },
  ]

  const outcomeData = [
    { name: 'Successful',   value: filteredSuccessCount,                                            fill: '#6ee7b7' },
    { name: 'Unsuccessful', value: insights.filter(r => r.call_successful === false).length,        fill: '#f87171' },
  ]

  const timeData = useMemo(() => {
    const timeMap = {}
    insights.forEach(r => {
      if (r.start_timestamp) {
        const d   = new Date(r.start_timestamp)
        const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
        if (!timeMap[key]) timeMap[key] = {
          dateKey: key,
          label: d.toLocaleDateString('en-AU', { day:'2-digit', month:'short' }),
          count: 0,
        }
        timeMap[key].count++
      }
    })
    return Object.values(timeMap).sort((a, b) => a.dateKey.localeCompare(b.dateKey))
  }, [insights])

  const SENT_COLORS = { positive: '#6ee7b7', neutral: '#818cf8', negative: '#f87171' }
  const sentCounts = {}
  insights.forEach(r => {
    const s = (r.user_sentiment || 'unknown').toLowerCase()
    sentCounts[s] = (sentCounts[s] || 0) + 1
  })
  const sentPieData = Object.entries(sentCounts)
    .map(([name, value]) => ({
      name:  name.charAt(0).toUpperCase() + name.slice(1),
      value,
      color: SENT_COLORS[name] || '#64748b',
    }))
    .filter(d => d.value > 0)
    .sort((a, b) => b.value - a.value)

  return (
    <div>
      {loading && <div className="loading-bar" />}

      {/* Greeting + export actions */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div className="home-greeting" style={{ marginBottom: 0 }}>
          <div className="home-greeting-text">
            {greeting}, <span style={{ color: 'var(--accent2)' }}>{clientName}</span>
          </div>
          <div className="home-greeting-sub">
            {hasActiveFilters
              ? `Showing ${n} of ${allInsights.length} calls · filtered view`
              : 'Here is your call intelligence overview'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
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
        </div>
      </div>

      {/* Narrative story cards */}
      <motion.div
        className="story-grid"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
        initial="hidden"
        animate="show"
      >
        <StoryCard
          headline={`${totalCallsDisplay} total calls`}
          sub={hasActiveFilters ? `${n} match active filters` : `${n} with full audio insights`}
          color="var(--accent2)"
        />
        <StoryCard
          headline={`${successRateDisplay}% success rate`}
          sub={hasActiveFilters ? `${filteredSuccessCount} of ${n} filtered calls` : 'calls completed successfully'}
          color="var(--accent)"
        />
        <StoryCard
          headline={`${avgEngagement.toFixed(1)} / 100 avg engagement`}
          sub={
            stats?.engagement_benchmark?.label
              ? `${stats.engagement_benchmark.label} · Voice AI industry baseline 62.0`
              : avgEngagement >= 70 ? 'Callers are well engaged' : avgEngagement >= 50 ? 'Room for improvement' : 'Engagement needs attention'
          }
          color={avgEngagement >= 70 ? 'var(--accent)' : avgEngagement >= 50 ? 'var(--accent3)' : 'var(--warn)'}
        />
        <StoryCard
          headline={`Most calls are ${dominated} flow`}
          sub={`${flowCounts.smooth} smooth  ·  ${flowCounts.moderate} moderate  ·  ${flowCounts.poor} poor`}
          color={flowColor(dominated)}
        />
        <StoryCard
          headline={`${trajCounts.improving} calls improving`}
          sub={`${trajCounts.deteriorating} deteriorating  ·  ${trajCounts.stable} stable`}
          color="var(--accent)"
        />
        <StoryCard
          headline={`${(avgSilence * 100).toFixed(1)}% avg silence`}
          sub={avgSilence < 0.1 ? 'Conversations are active' : avgSilence < 0.2 ? 'Some dead air detected' : 'High silence — check call quality'}
          color={avgSilence < 0.1 ? 'var(--accent)' : avgSilence < 0.2 ? 'var(--accent3)' : 'var(--warn)'}
        />
      </motion.div>

      {/* Agent Performance Chart */}
      {insights.some(r => r.agent_name) && (
        <AgentPerformanceChart insights={insights} />
      )}

      {/* Charts — engagement distribution + flow breakdown */}
      {n > 0 && (
        <motion.div
          className="chart-grid"
          style={{ marginTop: 8, marginBottom: 8 }}
          variants={stagger}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-40px' }}
        >
          <motion.div className="card" variants={fadeUp}>
            <div className="card-header">
              <div>
                <div className="card-title">Engagement Distribution</div>
                <div className="card-desc">calls per score band (out of 100)</div>
              </div>
              <span className="tag tag-purple">HISTOGRAM</span>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={histData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                  <defs>
                    <linearGradient id="hg-home" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#818cf8"/>
                      <stop offset="100%" stopColor="#6ee7b7" stopOpacity={0.6}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                  <XAxis dataKey="range" tick={{ fill: '#64748b', fontSize: 11 }}/>
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }}/>
                  <Tooltip {...TT} formatter={v => [v, 'calls']}/>
                  <Bar dataKey="count" fill="url(#hg-home)" radius={[4, 4, 0, 0]}/>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          <motion.div className="card" variants={fadeUp}>
            <div className="card-header">
              <div>
                <div className="card-title">Caller Sentiment</div>
                <div className="card-desc">positive / neutral / negative breakdown</div>
              </div>
              <span className="tag tag-green">SENTIMENT</span>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={sentPieData} cx="50%" cy="50%" innerRadius={52} outerRadius={78} dataKey="value" paddingAngle={3}>
                    {sentPieData.map((d, i) => <Cell key={i} fill={d.color}/>)}
                  </Pie>
                  <Tooltip {...TT} formatter={(v, name) => [v + ' calls', name]}/>
                  <Legend iconSize={10} formatter={v => <span style={{ color:'#94a3b8', fontSize:11 }}>{v}</span>}/>
                </PieChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          <motion.div className="card" variants={fadeUp}>
            <div className="card-header">
              <div>
                <div className="card-title">Calls Over Time</div>
                <div className="card-desc">daily call volume</div>
              </div>
              <span className="tag tag-green">TIMELINE</span>
            </div>
            <div className="chart-wrap">
              {timeData.length > 1 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={timeData} margin={{ top:4, right:8, left:-24, bottom:0 }}>
                    <defs>
                      <linearGradient id="time-grad-home" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%"   stopColor="#6ee7b7" stopOpacity={0.4}/>
                        <stop offset="100%" stopColor="#6ee7b7" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                    <XAxis dataKey="label" tick={{ fill:'#64748b', fontSize:10 }} interval="preserveStartEnd"/>
                    <YAxis allowDecimals={false} tick={{ fill:'#64748b', fontSize:10 }}/>
                    <Tooltip {...TT} formatter={v => [v, 'calls']}/>
                    <Area type="monotone" dataKey="count" stroke="#6ee7b7" strokeWidth={2} fill="url(#time-grad-home)"/>
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height:200, display:'flex', alignItems:'center', justifyContent:'center', color:'var(--muted)', fontSize:12 }}>
                  {timeData.length === 1 ? `All ${n} calls on ${timeData[0].label}` : 'No timestamp data'}
                </div>
              )}
            </div>
          </motion.div>

          <motion.div className="card" variants={fadeUp}>
            <div className="card-header">
              <div>
                <div className="card-title">Call Flow</div>
                <div className="card-desc">smooth / moderate / poor</div>
              </div>
              <span className="tag tag-green">FLOW</span>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={flowPieData} cx="50%" cy="50%" innerRadius={52} outerRadius={78} dataKey="value" paddingAngle={3}>
                    {flowPieData.map((d, i) => <Cell key={i} fill={d.color}/>)}
                  </Pie>
                  <Tooltip {...TT} formatter={(v, name) => [v + ' calls', name]}/>
                  <Legend iconSize={10} formatter={v => <span style={{ color:'#94a3b8', fontSize:11 }}>{v}</span>}/>
                </PieChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

          <motion.div className="card" variants={fadeUp}>
            <div className="card-header">
              <div>
                <div className="card-title">Trajectory &amp; Outcome</div>
                <div className="card-desc">sentiment trend + call success</div>
              </div>
              <span className="tag tag-purple">BREAKDOWN</span>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={[
                    ...trajData,
                    { name: '', value: 0, fill: 'transparent' },
                    ...outcomeData,
                  ]}
                  margin={{ top:4, right:8, left:-24, bottom:0 }}
                  layout="vertical"
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" horizontal={false}/>
                  <XAxis type="number" allowDecimals={false} tick={{ fill:'#64748b', fontSize:10 }}/>
                  <YAxis type="category" dataKey="name" tick={{ fill:'#94a3b8', fontSize:10 }} width={84}/>
                  <Tooltip {...TT} formatter={v => [v, 'calls']}/>
                  <Bar dataKey="value" radius={[0,4,4,0]}>
                    {[...trajData, { fill:'transparent' }, ...outcomeData].map((d, i) => (
                      <Cell key={i} fill={d.fill || 'transparent'}/>
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </motion.div>

        </motion.div>
      )}

      {/* Call Alerts */}
      <div className="section-label" style={{ marginTop: 36 }}>
        Call Alerts
        {recs.filter(r => r.priority === 'critical').length > 0 && (
          <span className="rec-critical-badge">
            {recs.filter(r => r.priority === 'critical').length} critical
          </span>
        )}
      </div>

      {recsLoading ? (
        <div className="rec-loading">Scanning calls for issues...</div>
      ) : recs.length === 0 ? (
        <div className="card" style={{ padding: 24, color: 'var(--muted)', fontFamily:"'DM Mono'", fontSize: 12 }}>
          No alerts — no flagged patterns detected in your call data.
        </div>
      ) : (
        <div className="rec-list">
          {recs.map(rec => {
            const meta   = PRIORITY_META[rec.priority] || PRIORITY_META.info
            const trend  = TREND_META[rec.trend]       || TREND_META.stable
            const isOpen = expanded === rec.id

            return (
              <div
                key={rec.id}
                className="rec-card"
                style={{ borderColor: meta.border, background: meta.bg }}
              >
                <div className="rec-header">
                  <div className="rec-header-left">
                    <span className="rec-priority-tag" style={{ color: meta.color, borderColor: meta.border }}>
                      {meta.label}
                    </span>
                    <span className="rec-title">{rec.title}</span>
                  </div>
                  <div className="rec-header-right">
                    {rec.affected_calls > 0 && (
                      <span className="rec-count" style={{ color: meta.color }}>
                        {rec.affected_calls} calls
                      </span>
                    )}
                    <span className="rec-trend" style={{ color: trend.color }}>
                      {trend.icon} {rec.trend}
                    </span>
                  </div>
                </div>

                <p className="rec-insight">{rec.insight}</p>

                <div className="rec-metric" style={{ borderColor: meta.border, color: meta.color }}>
                  {rec.metric}
                </div>

                <button
                  className="rec-action-toggle"
                  style={{ color: meta.color }}
                  onClick={() => setExpanded(isOpen ? null : rec.id)}
                >
                  {isOpen ? '▲ Hide action' : '▼ Recommended action'}
                </button>

                <AnimatePresence>
                  {isOpen && (
                    <motion.div
                      className="rec-action"
                      style={{ borderColor: meta.border, overflow: 'hidden' }}
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.22, ease: 'easeOut' }}
                    >
                      {rec.action}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      )}

      {/* Recent calls */}
      <div className="section-label" style={{ marginTop: 36 }}>Recent Calls</div>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Latest Activity</div>
            <div className="card-desc">most recently processed calls</div>
          </div>
          <motion.button className="view-all-btn" onClick={() => navigate('/dashboard/calls')}
            whileHover={{ scale: 1.04, x: 2 }} whileTap={{ scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}>
            View all →
          </motion.button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Call ID</th>
                <th>Date &amp; Time</th>
                <th>Direction</th>
                <th>Flow</th>
                <th>Trajectory</th>
                <th>Engagement</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted)', padding: 20 }}>
                  {loading ? 'Loading...' : 'No calls yet'}
                </td></tr>
              ) : recent.map((r, i) => (
                <motion.tr key={r.call_id} onClick={() => navigate('/dashboard/calls')}
                  style={{ cursor: 'pointer' }}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05, duration: 0.25, ease: 'easeOut' }}
                  whileHover={{ backgroundColor: 'var(--hover-bg)' }}>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{r.call_id}</td>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 11, whiteSpace: 'nowrap' }}>
                    {r.start_timestamp
                      ? new Date(r.start_timestamp).toLocaleString('en-AU', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })
                      : '—'}
                  </td>
                  <td>
                    <span className={`tag ${r.direction === 'inbound' ? 'tag-green' : 'tag-purple'}`} style={{ fontSize: 10, padding: '2px 7px' }}>
                      {r.direction || '—'}
                    </span>
                  </td>
                  <td><span className={`flow-chip chip-${r.conversation_flow}`}>{r.conversation_flow || '—'}</span></td>
                  <td>
                    <span className={`traj traj-${r.sentiment_trajectory}`}>
                      {r.sentiment_trajectory === 'improving' ? '↑' : r.sentiment_trajectory === 'deteriorating' ? '↓' : '→'}
                      {' '}{r.sentiment_trajectory || '—'}
                    </span>
                  </td>
                  <td style={{ fontFamily: "'DM Mono'", fontSize: 12 }}>
                    {parseFloat(r.engagement_score || 0).toFixed(1)}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
