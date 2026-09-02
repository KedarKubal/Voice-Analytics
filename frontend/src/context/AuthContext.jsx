import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user,  setUser]  = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('heya_token'))
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        if (payload.exp * 1000 > Date.now()) {
          setUser(payload)
        } else {
          // Token expired — clear it
          localStorage.removeItem('heya_token')
          setToken(null)
        }
      } catch {
        localStorage.removeItem('heya_token')
        setToken(null)
      }
    }
    setReady(true)
  }, [token])

  function login(newToken, meta = {}) {
    localStorage.setItem('heya_token', newToken)
    setToken(newToken)
    const payload = JSON.parse(atob(newToken.split('.')[1]))
    setUser({ ...payload, ...meta })
  }

  function logout() {
    localStorage.removeItem('heya_token')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout, ready }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
