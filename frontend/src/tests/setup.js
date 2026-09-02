import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Provide a complete localStorage mock — jsdom 29 with vitest may not expose
// .clear() reliably across environments.
const _store = {}
const localStorageMock = {
  getItem:    (k)    => Object.prototype.hasOwnProperty.call(_store, k) ? _store[k] : null,
  setItem:    (k, v) => { _store[k] = String(v) },
  removeItem: (k)    => { delete _store[k] },
  clear:      ()     => { Object.keys(_store).forEach(k => delete _store[k]) },
  get length() { return Object.keys(_store).length },
  key: (i) => Object.keys(_store)[i] ?? null,
}

Object.defineProperty(globalThis, 'localStorage', {
  value:    localStorageMock,
  writable: true,
})
