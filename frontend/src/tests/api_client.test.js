/**
 * api_client.test.js — apiClient.js unit tests
 *
 * Covers:
 *  • baseURL is set to http://localhost:8000
 *  • Authorization header is injected when heya_token is in localStorage
 *  • No Authorization header when localStorage is empty
 *  • 401 response triggers localStorage.removeItem('heya_token')
 *  • Non-401 errors are re-thrown (not swallowed)
 *  • timeout is set to 15000ms
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios from 'axios'

// jsdom doesn't implement window.location.href assignment — shim it
Object.defineProperty(window, 'location', {
  writable: true,
  value: { href: 'http://localhost:5173/dashboard' },
})

// We need to import the module fresh for each test to re-run interceptors.
// Use dynamic import after setting localStorage state.
async function loadApiClient() {
  vi.resetModules()
  const mod = await import('../api/apiClient')
  return mod.default
}

beforeEach(() => {
  localStorage.clear()
  window.location.href = 'http://localhost:5173/dashboard'
})
afterEach(() => {
  localStorage.clear()
  vi.resetModules()
  vi.restoreAllMocks()
})


describe('apiClient', () => {
  it('is an axios instance', async () => {
    const api = await loadApiClient()
    expect(api).toBeDefined()
    expect(typeof api.get).toBe('function')
    expect(typeof api.post).toBe('function')
  })

  it('baseURL is http://localhost:8000', async () => {
    const api = await loadApiClient()
    expect(api.defaults.baseURL).toBe('http://localhost:8000')
  })

  it('timeout is 15000', async () => {
    const api = await loadApiClient()
    expect(api.defaults.timeout).toBe(15000)
  })

  it('request interceptor attaches Bearer token from localStorage', async () => {
    localStorage.setItem('heya_token', 'test.token.value')
    const api = await loadApiClient()

    // Run the first request interceptor manually
    const interceptor = api.interceptors.request.handlers[0]
    const config = await interceptor.fulfilled({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer test.token.value')
  })

  it('request interceptor does NOT add Authorization when token is absent', async () => {
    const api = await loadApiClient()

    const interceptor = api.interceptors.request.handlers[0]
    const config = await interceptor.fulfilled({ headers: {} })
    expect(config.headers.Authorization).toBeUndefined()
  })

  it('response error interceptor removes token from localStorage on 401', async () => {
    localStorage.setItem('heya_token', 'some.valid.token')
    const api = await loadApiClient()

    const interceptor = api.interceptors.response.handlers[0]
    const fakeError = { response: { status: 401 } }

    try {
      await interceptor.rejected(fakeError)
    } catch { /* expected rejection */ }

    expect(localStorage.getItem('heya_token')).toBeNull()
  })

  it('response error interceptor redirects to /login on 401', async () => {
    const api = await loadApiClient()

    const interceptor = api.interceptors.response.handlers[0]
    const fakeError = { response: { status: 401 } }

    try {
      await interceptor.rejected(fakeError)
    } catch { /* expected */ }

    expect(window.location.href).toBe('/login')
  })

  it('response error interceptor re-throws non-401 errors', async () => {
    const api = await loadApiClient()

    const interceptor = api.interceptors.response.handlers[0]
    const fakeError = { response: { status: 500 }, message: 'Server Error' }

    await expect(interceptor.rejected(fakeError)).rejects.toEqual(fakeError)
  })

  it('response error interceptor re-throws 403 errors', async () => {
    const api = await loadApiClient()

    const interceptor = api.interceptors.response.handlers[0]
    const fakeError = { response: { status: 403 }, message: 'Forbidden' }

    await expect(interceptor.rejected(fakeError)).rejects.toEqual(fakeError)
    // Token must NOT be removed for 403
    localStorage.setItem('heya_token', 'keep.this.token')
    await expect(interceptor.rejected(fakeError)).rejects.toEqual(fakeError)
    expect(localStorage.getItem('heya_token')).toBe('keep.this.token')
  })

  it('successful responses are passed through unchanged', async () => {
    const api = await loadApiClient()

    const interceptor = api.interceptors.response.handlers[0]
    const fakeResponse = { status: 200, data: { ok: true } }

    const result = await interceptor.fulfilled(fakeResponse)
    expect(result).toEqual(fakeResponse)
  })
})
