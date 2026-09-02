-- ═══════════════════════════════════════════════════════════════════════════════
-- migrate_agent_profiles.sql  —  Heya AI Voice Analytics
-- Adds persona metadata columns to the agents table and populates all 6 agents.
--
-- Run once:
--   psql -U postgres -d voice_ai -p 5435 -f migrate_agent_profiles.sql
--
-- Or paste directly into pgAdmin / DBeaver Query Tool.
--
-- Safe to re-run — ALTER TABLE uses IF NOT EXISTS, UPDATEs are idempotent.
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── 1. Add new columns to agents table ───────────────────────────────────────
ALTER TABLE agents
    ADD COLUMN IF NOT EXISTS persona_name  VARCHAR(100),
    ADD COLUMN IF NOT EXISTS description   TEXT,
    ADD COLUMN IF NOT EXISTS direction     VARCHAR(20),   -- inbound | outbound | both
    ADD COLUMN IF NOT EXISTS agent_role    VARCHAR(50);   -- concierge | receptionist | at_fault_collector | follow_up_emailer

-- ── 2. Populate agent profiles ────────────────────────────────────────────────

-- ── ARTEL APARTMENTS ─────────────────────────────────────────────────────────

-- Sasha — AI Concierge, Artel Apartments (370 calls)
UPDATE agents SET
    persona_name = 'Sasha',
    direction    = 'inbound',
    agent_role   = 'concierge',
    description  = 'AI concierge for Artel Apartments (Brunswick, Melbourne). Handles inbound calls from guests and prospective tenants. Assists with check-in instructions (access codes, key safes, parking), booking inquiries, property FAQs, amenities, and general building questions. Can verify guest identity against booking records, send secure forms and links via SMS, and escalate to human reception when needed. Operates 24/7 with after-hours logic for urgent issues including lockouts and emergencies.'
WHERE id = 'agent_28ebdecbf16cbb5dfc96589d32';

-- ── MVAA LEGAL ────────────────────────────────────────────────────────────────

-- Justine — AI Receptionist, MVAA Legal (357 calls)
UPDATE agents SET
    persona_name = 'Justine',
    direction    = 'inbound',
    agent_role   = 'receptionist',
    description  = 'AI receptionist for MVAA Legal (Melbourne motor vehicle accident law firm). Handles all inbound calls — answers general inquiries about the firm''s services, helps callers with case updates, and routes callers to the appropriate team member. Acts as the front door for the practice and is the highest-volume agent at MVAA.'
WHERE id = 'agent_fa08e43585c6579d3ef76fe6ba';

-- Sarah (Outbound) — At Fault Driver Caller, MVAA Legal (46 calls)
UPDATE agents SET
    persona_name = 'Sarah',
    direction    = 'outbound',
    agent_role   = 'at_fault_collector',
    description  = 'Makes outbound courtesy calls to at-fault drivers after a motor vehicle collision on behalf of MVAA Legal. Goal is to collect the driver''s insurance details (insurer name, claim/policy number) and their account of the accident, in a warm and non-confrontational tone. Tracks whether a claim has been lodged and the driver''s perception of fault. Outbound variant has a strong 89.1% success rate.'
WHERE id = 'agent_8fb2cb8871f7bf640534f0607a';

-- Sarah (Inbound) — At Fault Driver Caller return calls, MVAA Legal (7 calls)
UPDATE agents SET
    persona_name = 'Sarah',
    direction    = 'inbound',
    agent_role   = 'at_fault_collector',
    description  = 'Handles return calls from at-fault drivers who missed or are following up on the outbound Sarah call. Same objective — collect insurance details (insurer name, claim/policy number) and the driver''s account of the accident. Inbound return variant has lower success rate (14.3%) as callers are often defensive or calling to dispute fault. Same persona as outbound Sarah.'
WHERE id = 'agent_da956ae9f9a5e5b1ffd122f44d';

-- Julia (Outbound) — Welcome Pack Follow-up, MVAA Legal (8 calls)
UPDATE agents SET
    persona_name = 'Julia',
    direction    = 'outbound',
    agent_role   = 'follow_up_emailer',
    description  = 'Makes outbound follow-up calls to MVAA''s own clients to check whether they have signed the Welcome Pack (engagement/retainer documents) that was emailed after their initial consultation. Walks clients through finding and signing the pack, offers to resend via email or physical mail, and handles objections or technology difficulties. Currently has a low 25% success rate — most calls do not result in confirmed sign-off.'
WHERE id = 'agent_96d980070eca5838e58a5b505f';

-- Julia (Inbound) — Welcome Pack return calls, MVAA Legal (3 calls)
UPDATE agents SET
    persona_name = 'Julia',
    direction    = 'inbound',
    agent_role   = 'follow_up_emailer',
    description  = 'Handles return calls from MVAA clients who missed or are following up on the outbound Julia Welcome Pack call. Same objective — confirm Welcome Pack signature status and assist if needed. Very low call volume (3 calls) and 0% success rate to date, likely due to calls being very short (possible voicemails or disconnects). Same persona as outbound Julia.'
WHERE id = 'agent_68e9c67435f72930e32b668b6a';

-- ── Test / Placeholder ────────────────────────────────────────────────────────

-- agent_001 — Heya test agent (1 call, not used in production)
UPDATE agents SET
    persona_name = 'Heya Test Agent',
    direction    = 'inbound',
    agent_role   = 'test',
    description  = 'Placeholder test agent used during initial development and demonstration of the Heya AI platform. Not used in production. Only 1 call on record.'
WHERE id = 'agent_001';


-- ── 3. Verify ────────────────────────────────────────────────────────────────
-- Run this SELECT after the migration to confirm all rows are populated correctly.

SELECT
    id,
    client_id,
    persona_name,
    direction,
    agent_role,
    LEFT(description, 80) AS description_preview
FROM agents
ORDER BY client_id, agent_role, direction;
