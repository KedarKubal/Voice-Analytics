import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useClientData } from '../../hooks/useClientData'
import { useFilters } from '../../context/FilterContext'

const cardIn = {
  hidden: { opacity: 0, y: 24 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
}
const rowStagger = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.1 } },
}
const kpiItem = {
  hidden: { opacity: 0, y: 16 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
}
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts'
import '../../App.css'

const TT = {
  contentStyle: { background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 8 },
  labelStyle:   { color: 'var(--tooltip-text)' },
  itemStyle:    { color: 'var(--tooltip-item)' },
}

function mean(arr, key) {
  const vals = arr.map(r => parseFloat(r[key]) || 0).filter(v => v > 0)
  return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0
}

export default function Trends() {
  const { insights: allInsights, loading } = useClientData()
  const { applyTo, hasActiveFilters } = useFilters()
  const insights = applyTo(allInsights)

  // Group by week (based on created_at)
  const weeklyData = useMemo(() => {
    if (!insights.length) return []

    const byWeek = {}
    insights.forEach(r => {
      if (!r.created_at) return
      const d    = new Date(r.created_at)
      const week = `${d.getFullYear()}-W${String(Math.ceil((d.getDate() + new Date(d.getFullYear(), d.getMonth(), 1).getDay()) / 7)).padStart(2,'0')}`
      if (!byWeek[week]) byWeek[week] = []
      byWeek[week].push(r)
    })

    return Object.entries(byWeek)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-12)
      .map(([week, rows]) => ({
        week,
        calls:      rows.length,
        engagement: mean(rows, 'engagement_score'),
        silence:    mean(rows, 'silence_ratio') * 100,
        interrupts: mean(rows, 'interruption_count'),
      }))
  }, [insights])

  // Engagement trend (cumulative moving avg)
  const engTrend = useMemo(() => {
    const sorted = [...insights]
      .filter(r => r.created_at && r.engagement_score)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
      .slice(-50)

    let sum = 0
    return sorted.map((r, i) => {
      sum += parseFloat(r.engagement_score) || 0
      return {
        idx:        i + 1,
        engagement: parseFloat(r.engagement_score) || 0,
        movingAvg:  Math.round((sum / (i + 1)) * 10) / 10,
      }
    })
  }, [insights])

  // Flow distribution trend by week
  const flowTrend = useMemo(() => {
    return weeklyData.map(w => {
      const rows = insights.filter(r => {
        if (!r.created_at) return false
        const d    = new Date(r.created_at)
        const week = `${d.getFullYear()}-W${String(Math.ceil((d.getDate()+new Date(d.getFullYear(),d.getMonth(),1).getDay())/7)).padStart(2,'0')}`
        return week === w.week
      })
      return {
        week:     w.week,
        smooth:   rows.filter(r => r.conversation_flow === 'smooth').length,
        moderate: rows.filter(r => r.conversation_flow === 'moderate').length,
        poor:     rows.filter(r => r.conversation_flow === 'poor').length,
      }
    })
  }, [weeklyData, insights])

  // Sentiment breakdown per week
  const sentTrend = useMemo(() => {
    return weeklyData.map(w => {
      const rows = insights.filter(r => {
        if (!r.created_at) return false
        const d    = new Date(r.created_at)
        const week = `${d.getFullYear()}-W${String(Math.ceil((d.getDate()+new Date(d.getFullYear(),d.getMonth(),1).getDay())/7)).padStart(2,'0')}`
        return week === w.week
      })
      return {
        week:     w.week,
        positive: rows.filter(r => r.user_sentiment === 'positive').length,
        neutral:  rows.filter(r => r.user_sentiment === 'neutral').length,
        negative: rows.filter(r => r.user_sentiment === 'negative').length,
      }
    })
  }, [weeklyData, insights])

  const totalCalls = insights.length
  const avgEng     = mean(insights, 'engagement_score')
  const improving  = insights.filter(r => r.sentiment_trajectory === 'improving').length

  // Overall sentiment counts for KPI
  const totalPositive = insights.filter(r => r.user_sentiment === 'positive').length
  const totalNegative = insights.filter(r => r.user_sentiment === 'negative').length
  const totalNeutral  = insights.filter(r => r.user_sentiment === 'neutral').length

  return (
    <div>
      {loading && <div className="loading-bar" />}

      <div className="page-header">
        <div>
          <h2 className="page-title">Trends</h2>
          <div className="page-sub">
            {hasActiveFilters
              ? `Filtered view · ${totalCalls} of ${allInsights.length} calls`
              : `Patterns across ${totalCalls} calls`}
          </div>
        </div>
      </div>

      {/* Summary KPIs */}
      <motion.div
        className="kpi-row"
        style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: 28 }}
        variants={rowStagger}
        initial="hidden"
        animate="show"
      >
        <motion.div className="kpi" variants={kpiItem}>
          <div className="kpi-label">Total Calls Analysed</div>
          <div className="kpi-value kpi-accent2">{totalCalls}</div>
          <div className="kpi-sub">with full audio insights</div>
        </motion.div>
        <motion.div className="kpi" variants={kpiItem}>
          <div className="kpi-label">Platform Avg Engagement</div>
          <div className="kpi-value kpi-accent">{avgEng.toFixed(1)}</div>
          <div className="kpi-sub">out of 100</div>
        </motion.div>
        <motion.div className="kpi" variants={kpiItem}>
          <div className="kpi-label">Improving Trajectories</div>
          <div className="kpi-value kpi-accent">{improving}</div>
          <div className="kpi-sub">{totalCalls ? ((improving/totalCalls)*100).toFixed(1) : 0}% of all calls</div>
        </motion.div>
      </motion.div>

      {/* Weekly call volume */}
      {weeklyData.length > 0 && (
        <>
          <motion.div
            className="chart-grid"
            variants={rowStagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-40px' }}
          >
            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div><div className="card-title">Call Volume by Week</div><div className="card-desc">number of calls processed per week</div></div>
                <span className="tag tag-purple">WEEKLY</span>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={weeklyData} margin={{ top:5, right:10, left:-20, bottom:5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                    <XAxis dataKey="week" tick={{ fill:'#64748b', fontSize:9 }}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }}/>
                    <Tooltip {...TT} formatter={v=>[v,'calls']}/>
                    <Bar dataKey="calls" fill="#818cf8" radius={[4,4,0,0]}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div><div className="card-title">Avg Engagement by Week</div><div className="card-desc">how engagement changes over time</div></div>
                <span className="tag tag-green">TREND</span>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={weeklyData} margin={{ top:5, right:10, left:-20, bottom:5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                    <XAxis dataKey="week" tick={{ fill:'#64748b', fontSize:9 }}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} domain={[0,100]}/>
                    <Tooltip {...TT} formatter={v=>[v.toFixed(1),'Engagement']}/>
                    <Line type="monotone" dataKey="engagement" stroke="#6ee7b7" strokeWidth={2} dot={{ r:3, fill:'#6ee7b7' }}/>
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </motion.div>

          <motion.div
            className="chart-grid"
            variants={rowStagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-40px' }}
          >
            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div><div className="card-title">Engagement Moving Average</div><div className="card-desc">last 50 calls — rolling average trend</div></div>
                <span className="tag tag-green">MOVING AVG</span>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={engTrend} margin={{ top:5, right:10, left:-20, bottom:5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                    <XAxis dataKey="idx" tick={{ fill:'#64748b', fontSize:10 }}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} domain={[0,100]}/>
                    <Tooltip {...TT} formatter={(v,n)=>[v.toFixed(1), n==='movingAvg'?'Moving Avg':'Score']}/>
                    <Line type="monotone" dataKey="engagement" stroke="#818cf840" strokeWidth={1} dot={false}/>
                    <Line type="monotone" dataKey="movingAvg"  stroke="#6ee7b7"   strokeWidth={2} dot={false}/>
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            <motion.div className="card" variants={cardIn}>
              <div className="card-header">
                <div><div className="card-title">Avg Silence Ratio by Week</div><div className="card-desc">lower is better — active conversations</div></div>
                <span className="tag tag-orange">SILENCE</span>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={weeklyData} margin={{ top:5, right:10, left:-20, bottom:5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                    <XAxis dataKey="week" tick={{ fill:'#64748b', fontSize:9 }}/>
                    <YAxis tick={{ fill:'#64748b', fontSize:11 }} unit="%"/>
                    <Tooltip {...TT} formatter={v=>[`${v.toFixed(1)}%`,'Silence']}/>
                    <Line type="monotone" dataKey="silence" stroke="#fb923c" strokeWidth={2} dot={{ r:3, fill:'#fb923c' }}/>
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}

      {/* Sentiment Analysis Section */}
      <div className="section-label" style={{ marginTop: 8 }}>Sentiment Analysis</div>
      <motion.div
        className="kpi-row"
        style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: 20 }}
        variants={rowStagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-40px' }}
      >
        <motion.div className="kpi" variants={kpiItem}>
          <div className="kpi-label">Positive Calls</div>
          <div className="kpi-value kpi-accent">{totalPositive}</div>
          <div className="kpi-sub">{totalCalls ? ((totalPositive/totalCalls)*100).toFixed(1) : 0}% of all calls</div>
        </motion.div>
        <motion.div className="kpi" variants={kpiItem}>
          <div className="kpi-label">Neutral Calls</div>
          <div className="kpi-value kpi-accent2">{totalNeutral}</div>
          <div className="kpi-sub">{totalCalls ? ((totalNeutral/totalCalls)*100).toFixed(1) : 0}% of all calls</div>
        </motion.div>
        <motion.div className="kpi" variants={kpiItem}>
          <div className="kpi-label">Negative Calls</div>
          <div className="kpi-value kpi-warn">{totalNegative}</div>
          <div className="kpi-sub">{totalCalls ? ((totalNegative/totalCalls)*100).toFixed(1) : 0}% of all calls</div>
        </motion.div>
      </motion.div>

      {sentTrend.length > 0 && (
        <motion.div
          className="card"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-40px' }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
        >
          <div className="card-header">
            <div>
              <div className="card-title">Sentiment by Week</div>
              <div className="card-desc">positive / neutral / negative call counts per week</div>
            </div>
            <span className="tag tag-green">SENTIMENT TREND</span>
          </div>
          <div className="chart-wrap" style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={sentTrend} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08"/>
                <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 9 }}/>
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }}/>
                <Tooltip {...TT} formatter={(v, name) => [v + ' calls', name.charAt(0).toUpperCase() + name.slice(1)]}/>
                <Legend iconSize={10} formatter={v => <span style={{ color:'#94a3b8', fontSize:11 }}>{v.charAt(0).toUpperCase() + v.slice(1)}</span>}/>
                <Bar dataKey="positive" stackId="s" fill="#6ee7b7" radius={[0, 0, 0, 0]}/>
                <Bar dataKey="neutral"  stackId="s" fill="#818cf8" radius={[0, 0, 0, 0]}/>
                <Bar dataKey="negative" stackId="s" fill="#f87171" radius={[4, 4, 0, 0]}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}

      {!weeklyData.length && !loading && (
        <motion.div
          className="card"
          style={{ textAlign: 'center', padding: 40, color: 'var(--muted)' }}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}
        >
          No trend data yet — time-based charts appear after calls span multiple weeks.
        </motion.div>
      )}
    </div>
  )
}
