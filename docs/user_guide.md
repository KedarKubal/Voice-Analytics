# Heya AI — User Guide
**For client users and administrators**

---

## Getting Started

### Logging In

1. Open your browser and go to: `http://localhost:5173`
2. Enter your email and password on the login screen
3. You will be redirected to your dashboard automatically

**Demo accounts:**

| Email | Password | Role |
|---|---|---|
| admin@heya.au | heya_admin_2026 | Platform Admin (all clients) |
| admin@artel.com | artel_2026 | Artel Apartments |
| admin@mvaallegal.com | mvaa_2026 | MVAA Legal |

---

## Client Dashboard

### Overview Page

The Overview page is the first thing you see after login. It shows:

- **Total Calls** — number of calls processed for your account
- **Average Engagement Score** — 0–100 composite score across all calls
- **Average Quality Grade** — overall call quality (A / B / C / D)
- **Active Agents** — number of AI agents associated with your account

Scroll down to see a summary of recent call activity and top-level trends.

---

### Analytics Page

The Analytics page provides seven sections of visual metrics:

| Section | What it shows |
|---|---|
| **Engagement Distribution** | Histogram of engagement scores across all calls |
| **Flow Breakdown** | Proportion of calls by flow label (smooth / hesitant / interrupted / abandoned) |
| **Sentiment Trajectory** | How customer sentiment evolves over calls (improving / declining / stable / volatile) |
| **Silence Ratios** | Distribution of silence percentage per call |
| **Interruptions** | Frequency of agent/customer cross-talk events |
| **Emotion Heatmap** | Dominant emotion detected per call, by agent and time period |
| **Topic Frequency** | Most common call topics |

**Using filters:** All analytics respond to the filter bar at the top. You can filter by date range, agent, direction (inbound/outbound), flow label, topic, sentiment, and trajectory. Click **Clear** to reset all filters.

---

### Calls Page

The Calls page shows every processed call in a filterable table.

**Available filters:**
- Date From / Date To
- Agent (dropdown — only shows agents active for your account)
- Direction: Inbound / Outbound / All
- Flow: Smooth / Hesitant / Interrupted / Abandoned
- Topic
- Sentiment: Positive / Neutral / Negative
- Trajectory: Improving / Declining / Stable / Volatile

**Table columns:**
Status · Call ID · Agent · Direction · Date/Time · Duration · Quality Grade · Quality Score · Engagement · Silence % · Interruptions · Flow · Trajectory · Sentiment · Emotion · Topic · Outcome

Click any row to view the full detail for that call.

---

### Ask Your Data Page

The Ask Your Data page has two sections:

#### RAG Chat (General Questions)

Type any question about your calls in the chat box. Examples:
- *"What was the average engagement score last week?"*
- *"Which calls had the highest silence ratios?"*
- *"Show me calls where customer sentiment declined."*
- *"Which topic comes up most often in outbound calls?"*

Suggestion pills are shown below the chat — click any to run a pre-built query.

#### Agent Analysis

Below the chat, you will see cards for each AI agent active on your account. Click an agent card to select it, then:
- Type a question about that specific agent
- Or click one of the preset pills (e.g., "Summarise recent performance", "Which calls had low engagement?")

Agent answers show:
- The answer text
- A **confidence badge** (High / Medium / Low)
- **Tools used** during the analysis (shown as chips)
- Execution time and step count
- A **Show reasoning** link to see the full step-by-step analysis chain

---

### Theme Toggle

You can switch between dark mode and light mode at any time:
- **Client dashboard**: Click the ☀ / 🌙 button at the bottom of the left sidebar
- **Admin dashboard**: Click the theme button in the top header bar

Your preference is saved automatically and will be restored on your next visit.

---

## Admin Dashboard

The admin dashboard is available to users with the `heya_admin` role only.

### Overview

Shows platform-wide totals:
- Total calls across all clients
- All active clients and agents
- Platform-level engagement and quality averages
- Per-client breakdown table

---

### Feed (Live Call Monitor)

The Feed page shows every call across all clients in a live-updating table.

**Filter bar (left to right):**
1. **Client** — select a client to filter (or leave blank for all)
2. **Agent** — select an agent (only available after selecting a client)
3. **Date From / Date To**
4. **Direction** — Inbound / Outbound
5. **Flow** — Smooth / Hesitant / Interrupted / Abandoned
6. **Trajectory** — Improving / Declining / Stable / Volatile
7. **Sentiment** — Positive / Neutral / Negative
8. **Topic**
9. **× Clear** — resets all filters

**LIVE indicator**: The table auto-refreshes every 5 seconds with any new calls. The LIVE badge flashes when active.

**Export CSV**: Click the `↓ Export CSV` button to download all currently filtered rows as a CSV file (UTF-8 BOM, compatible with Excel). The export includes 23 columns of call data.

---

### Intelligence (RAG — Cross-Client)

The Intelligence tab works like the client Ask Your Data page, but with cross-client capability.

In the dropdown above the chat box:
- Select a specific client to query their data
- Select **"Platform Overview (All Clients)"** to ask questions that compare across clients

Cross-client responses are marked with a **CROSS-CLIENT** badge.

Example cross-client queries:
- *"Which client has higher average engagement scores?"*
- *"Compare MVAA and Artel on call flow quality."*
- *"Which agent across all clients has the best performance?"*

---

## Frequently Asked Questions

**Q: My dashboard shows no data after login.**  
A: Sign out and sign back in. This refreshes your authentication token and resolves a known issue where the `name` field is missing after a backend restart.

**Q: The theme I selected disappeared.**  
A: Themes are saved in your browser's local storage. If you cleared browser data, the preference will be reset to dark mode.

**Q: Can I export my call data?**  
A: Currently, CSV export is available in the Admin Feed page. Client-level export is on the roadmap.

**Q: Why are some calls missing an emotion label?**  
A: The emotion detection step runs as a separate offline process. If emotion data is missing, the system administrator will need to run the emotion processor.

**Q: What do the flow labels mean?**

| Label | Meaning |
|---|---|
| Smooth | Natural, balanced conversation — good turn-taking, low interruptions |
| Hesitant | Long pauses, low customer engagement — may indicate confusion or reluctance |
| Interrupted | Frequent cross-talk — agent and customer talking over each other |
| Abandoned | Call ended early without reaching a resolution |

**Q: What is the engagement score?**  
A: A composite 0–100 score derived from turn balance, energy variance, pauses, and speaking rate. Scores above 70 indicate a high-quality, engaged conversation. Scores below 40 suggest the customer was disengaged.

---

*Heya AI | Platform version 2026.06 | Support: admin@heya.au*
