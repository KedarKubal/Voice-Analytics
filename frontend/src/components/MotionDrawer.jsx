import { motion, AnimatePresence } from 'framer-motion'

// children must be a render function: {() => <JSX />}
// Prevents evaluation of children referencing selected state when drawer is closed.
export default function MotionDrawer({ open, onClose, children }) {
  return (
    <>
      {/* Overlay — separate AnimatePresence so framer-motion tracks it independently */}
      <AnimatePresence>
        {open && (
          <motion.div
            key="drawer-overlay"
            className="drawer-overlay"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
        )}
      </AnimatePresence>

      {/* Drawer panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            key="drawer-panel"
            className="drawer"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 280 }}
          >
            {typeof children === 'function' ? children() : children}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
