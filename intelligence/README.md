# FBM Listing Intelligence

Implementation of `../PUBLIC_LISTING_INTELLIGENCE_ARCHITECTURE.md`: discover public car listings, capture a focused
screenshot, evaluate it with OpenClaw's vision model, and rank candidates with deterministic Python rules. Every
result is stored in Supabase with full audit history, and a human approves every recommendation at
`/admin/intelligence`.

```
approved search terms → Playwright adapter → dedupe + prefilter → focused screenshot (private bucket)
  → OpenClaw vision (tool-less agent, pinned function call) → Python validation + routing
  → eligibility gates + composite score → ranking with minimum-score gate → human review
```

## Setup (once)

```bash
cd intelligence
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m playwright install chromium
```

It reads Supabase credentials from `../.env.local` and the OpenClaw gateway token from `~/.openclaw/openclaw.json`.
Nothing secret is stored in this folder.

OpenClaw needs its OpenAI-compatible endpoint turned on, plus an evaluator agent that has no tools, so a malicious
screenshot can't make it do anything. This is already configured on this Mac:

```bash
openclaw config set gateway.http.endpoints.chatCompletions.enabled true
openclaw config set agents.entries.listing-eval '{"model":{"primary":"openai/gpt-5.5","fallbacks":[]},"tools":{"profile":"minimal","deny":["*"]}}' --strict-json
openclaw gateway restart
```

Use `openai/gpt-5.5`. `gpt-5.4-mini` is **not** available through a ChatGPT (Codex) login.

Apply the database schema once:
`../supabase/migrations/20260930_listing_intelligence.sql` and `20260930_account_roles.sql`.

## Commands

| Command | What it does |
|---|---|
| `.venv/bin/fbm-intel init` | Save the product brief + search profile from `config/default.json` and the reviewed seed search terms |
| `.venv/bin/fbm-intel run --limit 25` | Crawl → capture → prefilter → vision → score → rank |
| `.venv/bin/fbm-intel plan --llm` then `approve-plan --by NAME` | AI-generated Khmer/English/mixed search terms; stored **unapproved** until a person reviews the Khmer terms |
| `.venv/bin/fbm-intel run --planner llm` | Run using the approved AI plan |
| `.venv/bin/fbm-intel submit-url https://…` | Capture and evaluate one listing URL from an approved host (§13 fallback) |
| `.venv/bin/fbm-intel reprocess` | After changing a policy (new profile version), re-run the prefilter on stored evidence, then evaluate, score and rank |
| `.venv/bin/fbm-intel status` | Counts per state and the latest ranking |
| `.venv/bin/fbm-intel grant-admin you@email` | Let an FBM account open `/admin/intelligence` (sign up on the site first, then sign out and back in) |

Re-running is safe. The same screenshot with the same prompt, rubric and model is never evaluated or paid for twice,
and the same candidate set never creates a second ranking run.

## Tests

```bash
.venv/bin/python -m pytest              # 131 offline tests: unit, adapter contract (real Chromium + fixtures), end-to-end
.venv/bin/python -m pytest -m live -v   # 29 live tests: RLS/security against Supabase + real vision on labeled screenshots
```

## Sources

| Source | Status |
|---|---|
| `fbm` (fbm-pied.vercel.app) | ✅ First approved source. First-party, so automated collection is authorized |
| `manual_url` | ✅ One page at a time, only hosts in `MANUAL_URL_HOSTS` |
| Khmer24 | ⛔ Every page, including robots and terms, answers with a Cloudflare bot challenge. The spec forbids working around this, so the adapter stops. Use it only with written permission or an official API |
| Facebook | ⛔ Not built. Needs a separate policy approval (§13) |

## Defaults chosen for the open decisions (§21). Please confirm or change them

| # | Decision | Default in `config/default.json` / code |
|---|---|---|
| 1 | Product matched | "FBM curated used-car listings": clear, fairly presented used cars worth surfacing to buyers |
| 2 | First marketplace | FBM itself (Khmer24 blocks automation) |
| 3 | Locations | Phnom Penh, Kandal, Siem Reap, Battambang, Sihanoukville, Kampot |
| 4 | Categories | sedan, SUV, pickup, hatchback, MPV. No year or price limits yet |
| 6 | Hard rejections | Rental only, parts only, wanted-to-buy, outside geography, sold, not a vehicle |
| 7 | Retention | Not enforced yet. Screenshots are kept in the private bucket |
| 8 | Human approval | **Required for every recommendation** |
| 9 | Budgets | 12 queries, 1 page each, at most 40 listings per run; at least 1 s between page loads on FBM |
| 11 | Seller contact info | **Excluded.** Not stored, and not inside the screenshot crop |
| 12 | Accuracy before auto-approve | Not enabled. Thresholds in `scoring.py` are starting hypotheses (§11) |

Thresholds (`VisionRoutingPolicy`, `ScoringPolicy`, `RankingPolicy` in `fbm_intel/scoring.py`) must be recalibrated
on labeled Cambodian listings before any recommendation is automated.
