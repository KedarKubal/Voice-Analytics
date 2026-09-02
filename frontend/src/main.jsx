import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { FilterProvider } from './context/FilterContext'
import { ThemeProvider } from './context/ThemeContext'
import './index.css'

import Login          from './pages/Login'
import AdminApp       from './pages/AdminApp'
import ClientLayout   from './pages/client/ClientLayout'
import Home           from './pages/client/Home'
import Calls          from './pages/client/Calls'
import AudioInsights  from './pages/client/AudioInsights'
import Trends         from './pages/client/Trends'
import AskYourData    from './pages/client/AskYourData'
import Search         from './pages/client/Search'

// Shows a full-screen dark spinner while the auth state is resolving from localStorage.
// Prevents any flash of the wrong page before we know if the user is logged in.
function Loading() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg)',
    }}>
      <div style={{
        width: 32, height: 32,
        border: '3px solid var(--border2)',
        borderTop: '3px solid var(--accent2)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// Route guard — redirects based on role, shows spinner while auth is loading.
function ProtectedRoute({ children, requireRole }) {
  const { user, ready } = useAuth()
  if (!ready) return <Loading />
  if (!user)  return <Navigate to="/login" replace />
  if (requireRole && user.role !== requireRole) {
    return <Navigate to={user.role === 'heya_admin' ? '/admin' : '/dashboard'} replace />
  }
  return children
}

// Root path redirect — sends logged-in users to the right dashboard.
function RootRedirect() {
  const { user, ready } = useAuth()
  if (!ready) return <Loading />
  if (!user)  return <Navigate to="/login" replace />
  return <Navigate to={user.role === 'heya_admin' ? '/admin' : '/dashboard'} replace />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<Login />} />

          {/* Heya AI admin — God View */}
          <Route path="/admin" element={
            <ProtectedRoute requireRole="heya_admin"><AdminApp /></ProtectedRoute>
          } />

          {/* Client dashboard — sidebar layout with nested pages */}
          <Route path="/dashboard" element={
            <ProtectedRoute requireRole="client"><FilterProvider><ClientLayout /></FilterProvider></ProtectedRoute>
          }>
            <Route index            element={<Home />} />
            <Route path="calls"     element={<Calls />} />
            <Route path="insights"  element={<AudioInsights />} />
            <Route path="trends"    element={<Trends />} />
            <Route path="chat"      element={<AskYourData />} />
            <Route path="search"    element={<Search />} />
          </Route>

          {/* Catch-all — redirect to correct home */}
          <Route path="*" element={<RootRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
    </ThemeProvider>
  </StrictMode>
)
