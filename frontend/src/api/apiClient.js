/**
 * apiClient.js  —  Axios instance with automatic JWT injection.
 *
 * WHY: Every API request needs  Authorization: Bearer <token>
 * Rather than adding it manually in every component, we configure
 * it once here in an interceptor. Every axios call through this
 * client will automatically have the right header.
 *
 * Usage:
 *   import api from '../api/apiClient'
 *   const res = await api.get('/insights/client_heya_001')
 */

import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 15000,
})

// Attach JWT to every outgoing request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('heya_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Global 401 handler — token expired or invalid, send to login
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('heya_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
