import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'

import Sidebar from '../../components/Sidebar'
import { useFilters } from '../../context/FilterContext'
import './ClientLayout.css'

const pageVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -8 },
}

const TRAJ_LABELS = { improving: '↑ Improving', stable: '→ Stable', deteriorating: '↓ Deteriorating' }
const TOPIC_LABELS = {
  booking: 'Booking', cancellation: 'Cancellation', complaint: 'Complaint',
  payment: 'Payment', enquiry: 'Enquiry', technical_support: 'Tech Support',
  emergency: 'Emergency', follow_up: 'Follow Up', general: 'General',
}

export default function ClientLayout() {
  const location = useLocation()
  const {
    hasActiveFilters, dateFrom, dateTo,
    filterFlow, filterDir, filterTraj, filterTopic, clearFilters,
  } = useFilters()

  const pills = [
    dateFrom                && `From ${dateFrom}`,
    dateTo                  && `To ${dateTo}`,
    filterFlow  !== 'all'   && filterFlow.charAt(0).toUpperCase() + filterFlow.slice(1) + ' flow',
    filterDir   !== 'all'   && filterDir.charAt(0).toUpperCase() + filterDir.slice(1),
    filterTraj  !== 'all'   && TRAJ_LABELS[filterTraj],
    filterTopic !== 'all'   && TOPIC_LABELS[filterTopic],
  ].filter(Boolean)

  return (
    <div className="client-layout">
      <Sidebar />
      <main className="client-main">
        <AnimatePresence>
          {hasActiveFilters && (
            <motion.div
              className="global-filter-banner"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <span className="gfb-label">Filters active:</span>
              {pills.map(p => (
                <motion.span
                  key={p}
                  className="gfb-pill"
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ type: 'spring', stiffness: 360, damping: 22 }}
                >{p}</motion.span>
              ))}
              <motion.button
                className="gfb-clear"
                onClick={clearFilters}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >× Clear all</motion.button>
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={{ duration: 0.18, ease: 'easeOut' }}
            style={{ minHeight: '100%' }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
