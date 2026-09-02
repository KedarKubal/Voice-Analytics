import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'

export default function AudioPlayer({ callId }) {
  const audioRef               = useRef(null)
  const [blobUrl,  setBlobUrl] = useState(null)
  const [status,   setStatus]  = useState('idle')   // idle | loading | ready | error
  const [playing,  setPlaying] = useState(false)
  const [current,  setCurrent] = useState(0)
  const [duration, setDuration]= useState(0)

  const loadAudio = useCallback(async () => {
    if (status !== 'idle') return
    setStatus('loading')
    try {
      const token = localStorage.getItem('heya_token')
      const res   = await fetch(`http://localhost:8000/audio/${callId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const blob = await res.blob()
      setBlobUrl(URL.createObjectURL(blob))
      setStatus('ready')
    } catch {
      setStatus('error')
    }
  }, [callId, status])

  useEffect(() => () => { if (blobUrl) URL.revokeObjectURL(blobUrl) }, [blobUrl])

  useEffect(() => {
    setBlobUrl(null); setStatus('idle'); setPlaying(false); setCurrent(0); setDuration(0)
  }, [callId])

  function togglePlay() {
    const a = audioRef.current; if (!a) return
    if (playing) { a.pause(); setPlaying(false) }
    else         { a.play();  setPlaying(true)  }
  }
  function seek(e) {
    if (!audioRef.current || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    audioRef.current.currentTime = ((e.clientX - rect.left) / rect.width) * duration
  }
  function fmt(sec) {
    if (!sec || isNaN(sec)) return '0:00'
    return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
  }

  const pct = duration ? (current / duration) * 100 : 0

  return (
    <div>
      {blobUrl && (
        <audio ref={audioRef} src={blobUrl}
          onTimeUpdate={() => setCurrent(audioRef.current?.currentTime || 0)}
          onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
          onEnded={() => { setPlaying(false); setCurrent(0) }}
          style={{ display: 'none' }}
        />
      )}

      {status === 'idle' && (
        <motion.button
          onClick={loadAudio}
          whileHover={{ opacity: 0.85, scale: 1.01 }}
          whileTap={{ scale: 0.97 }}
          style={{
            display: 'flex', alignItems: 'center', gap: 10, width: '100%',
            background: 'var(--surface2)', border: '1px solid var(--border2)',
            borderRadius: 10, padding: '12px 16px', cursor: 'pointer',
            color: 'var(--accent2)', fontFamily: "'DM Mono'", fontSize: 11,
            letterSpacing: '0.06em', transition: 'border-color 0.2s',
          }}
        >
          <span style={{
            width: 30, height: 30, borderRadius: '50%', background: '#818cf820',
            border: '1px solid #818cf840', display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontSize: 12, flexShrink: 0,
          }}>▶</span>
          Load &amp; play recording
        </motion.button>
      )}

      {status === 'loading' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          background: 'var(--surface2)', border: '1px solid var(--border2)',
          borderRadius: 10, padding: '12px 16px',
          fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--muted)',
        }}>
          <span style={{
            width: 16, height: 16, border: '2px solid var(--border2)',
            borderTop: '2px solid var(--accent2)', borderRadius: '50%',
            animation: 'spin 0.8s linear infinite', display: 'inline-block', flexShrink: 0,
          }} />
          Loading audio...
        </div>
      )}

      {status === 'error' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: '#f8717110', border: '1px solid #f8717130',
          borderRadius: 10, padding: '12px 16px',
          fontFamily: "'DM Mono'", fontSize: 11, color: 'var(--warn)',
        }}>
          <span style={{ fontSize: 14 }}>⚠</span>
          Audio file not available for this call
        </div>
      )}

      {status === 'ready' && (
        <div style={{
          background: 'var(--surface2)', border: '1px solid var(--border2)',
          borderRadius: 12, padding: '14px 16px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <motion.button
              onClick={togglePlay}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.93 }}
              style={{
                width: 38, height: 38, borderRadius: '50%',
                background: playing
                  ? 'linear-gradient(135deg, #818cf8, #6ee7b7)'
                  : 'var(--accent2)',
                border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 13, flexShrink: 0,
                boxShadow: playing ? '0 0 20px #818cf850' : 'none',
                transition: 'box-shadow 0.3s',
              }}
            >
              {playing ? '⏸' : '▶'}
            </motion.button>

            <div style={{ flex: 1 }}>
              {/* Waveform progress bar */}
              <div
                onClick={seek}
                style={{
                  height: 6, background: 'var(--surface)',
                  borderRadius: 3, cursor: 'pointer', overflow: 'hidden', marginBottom: 8,
                  position: 'relative',
                }}
              >
                <motion.div
                  style={{
                    height: '100%', borderRadius: 3,
                    background: 'linear-gradient(90deg, var(--accent2), var(--accent))',
                    width: `${pct}%`,
                  }}
                  transition={{ duration: 0.1 }}
                />
                {/* Thumb */}
                <div style={{
                  position: 'absolute', top: '50%', left: `${pct}%`,
                  transform: 'translate(-50%, -50%)',
                  width: 12, height: 12, borderRadius: '50%',
                  background: 'var(--accent2)', boxShadow: '0 0 6px var(--accent2)',
                  transition: 'left 0.1s linear',
                }} />
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between',
                fontFamily: "'DM Mono'", fontSize: 10, color: 'var(--muted)',
              }}>
                <span style={{ color: playing ? 'var(--accent2)' : 'var(--muted)' }}>{fmt(current)}</span>
                <span>{fmt(duration)}</span>
              </div>
            </div>
          </div>

          {/* Mini live waveform when playing */}
          {playing && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 2,
              height: 16, marginTop: 10, justifyContent: 'center',
            }}>
              {Array.from({ length: 20 }).map((_, i) => (
                <motion.div
                  key={i}
                  style={{
                    width: 2, borderRadius: 1,
                    background: 'linear-gradient(to top, var(--accent2), var(--accent))',
                  }}
                  animate={{ scaleY: [0.2, 1, 0.3, 0.9, 0.2] }}
                  transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.05, ease: 'easeInOut' }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
