# Heya AI — Local Network Hosting for Demo Day

## The Problem

The frontend has this hardcoded in `apiClient.js`:
```js
baseURL: 'http://localhost:8000'
```

When someone on **their own laptop** opens the app, `localhost` means **their machine** — not yours. API calls fail and they see a blank/broken app.

---

## What Needs to Change

### 1. `frontend/src/api/apiClient.js`

Change from hardcoded `localhost` to dynamic — use whatever hostname the browser is already pointing at:

```js
// Before
baseURL: 'http://localhost:8000'

// After
const BASE_URL = `http://${window.location.hostname}:8000`
```

**How it behaves:**
- You open it via `localhost:5173` → API goes to `localhost:8000` ✅ (normal dev flow unchanged)
- They open it via `192.168.1.x:5173` → API goes to `192.168.1.x:8000` ✅ (their browser, your server)

No hardcoding, no env files, works everywhere automatically.

---

### 2. `frontend/vite.config.js`

By default Vite only listens on `localhost` — other machines can't reach it. Add one line:

```js
server: { host: true }
```

This makes Vite listen on `0.0.0.0` (all network interfaces), same as the backend already does.

---

## How It Works on Demo Day

```
Your laptop
├── Backend  → 0.0.0.0:8000  (already network-accessible)
└── Frontend → 0.0.0.0:5173  (after the fix)

Everyone's laptop
└── Browser → http://192.168.x.x:5173  (your IP)
                  ↓
              sees your React app
                  ↓
              API calls → http://192.168.x.x:8000
                  ↓
              hits your FastAPI backend
                  ↓
              real data ✅
```

Everyone gets the full live experience — login, filters, RAG queries, everything.

---

## Steps on the Day

1. Connect everyone to the **same WiFi**
2. Find your laptop's local IP — run `ipconfig` in terminal, look for **WiFi IPv4 address** (usually `192.168.x.x`)
3. Start backend and frontend as normal
4. Share the URL: `http://<your-ip>:5173`
5. Everyone opens it in their browser — done

---

## Summary of Code Changes

| File | Change | Risk |
|---|---|---|
| `frontend/src/api/apiClient.js` | 1 line — dynamic hostname | Zero — works on localhost too |
| `frontend/vite.config.js` | 1 line — `server: { host: true }` | Zero — just network binding |

**Total: 2 lines changed. Fully reversible after the demo.**
