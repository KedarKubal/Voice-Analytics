import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useClientData } from '../hooks/useClientData'
import { useTheme } from '../context/ThemeContext'
import './Sidebar.css'

const NAV = [
  { to: '/dashboard',          label: 'Home',           end: true },
  { to: '/dashboard/calls',    label: 'Calls'                     },
  { to: '/dashboard/insights', label: 'Audio Insights'            },
  { to: '/dashboard/trends',   label: 'Trends'                    },
  { to: '/dashboard/chat',     label: 'Ask Your Data'             },
  { to: '/dashboard/search',   label: 'Search'                    },
]

const CLIENT_DISPLAY_NAMES = {
  'client_heya_001': 'Artel Apartments',
  'client_heya_002': 'MVAA Legal',
}

const navItem = {
  hidden: { opacity: 0, x: -14 },
  show:   { opacity: 1, x: 0, transition: { duration: 0.22, ease: 'easeOut' } },
}

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { lastUpdated, stats } = useClientData()
  const { theme, toggleTheme } = useTheme()

  function handleLogout() { logout(); navigate('/login') }

  const clientName = user?.name
    || CLIENT_DISPLAY_NAMES[user?.client_id]
    || user?.client_id
    || 'Client'

  const pendingAudio = stats?.pending_audio || 0

  function formatTime(date) {
    if (!date) return null
    return date.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  return (
    <motion.aside
      className="sidebar"
      initial={{ x: -30, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.38, ease: 'easeOut' }}
    >
      {/* Logo */}
      <div className="sb-logo">
        <motion.div
          className="sb-logo-mark"
          whileHover={{ rotate: 10, scale: 1.1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 16 }}
        >
          🎙
        </motion.div>
        <div>
          <div className="sb-logo-text">Heya AI</div>
          <div className="sb-logo-sub">Voice Analytics</div>
        </div>
      </div>

      {/* Client badge */}
      <div className="sb-client">
        <div className="sb-client-dot" />
        <div className="sb-client-name">{clientName}</div>
      </div>

      {/* Live data indicator */}
      {lastUpdated && (
        <div className="sb-live">
          <span className="sb-live-dot" />
          <span className="sb-live-text">Live · {formatTime(lastUpdated)}</span>
        </div>
      )}

      {/* Pending pipeline badge */}
      {pendingAudio > 0 && (
        <motion.div
          className="sb-pending"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
        >
          <span className="sb-pending-dot" />
          <span className="sb-pending-text">{pendingAudio} calls processing</span>
        </motion.div>
      )}

      {/* Nav links — staggered mount */}
      <motion.nav
        className="sb-nav"
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.055, delayChildren: 0.12 } } }}
      >
        {NAV.map(({ to, label, end }) => (
          <motion.div key={to} variants={navItem} whileHover={{ x: 3 }} transition={{ type: 'spring', stiffness: 380, damping: 22 }}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) => `sb-link ${isActive ? 'active' : ''}`}
            >
              <span className="sb-label">{label}</span>
            </NavLink>
          </motion.div>
        ))}
      </motion.nav>

      {/* Theme toggle */}
      <motion.button
        className="sb-theme-btn"
        onClick={toggleTheme}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.96 }}
        transition={{ type: 'spring', stiffness: 400, damping: 20 }}
        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        <span className="sb-theme-icon">{theme === 'dark' ? '☀' : '🌙'}</span>
        <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
      </motion.button>

      {/* Sign out */}
      <motion.button
        className="sb-signout"
        onClick={handleLogout}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.96 }}
        transition={{ type: 'spring', stiffness: 400, damping: 20 }}
      >
        Sign out
      </motion.button>
    </motion.aside>
  )
}
