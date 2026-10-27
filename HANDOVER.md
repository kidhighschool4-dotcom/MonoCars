# Agent handover

Read this before you start. Several Claude agents work on this repo at the same time; this file says who owns what,
how to hand work over, and the rules every agent follows.

## Agents and ownership

| Agent | Model | Owns | Must not touch |
|---|---|---|---|
| **lead** (main session) | Opus | `intelligence/` (worker, TikTok, rental leads, post rating), `app/admin/social`, migrations, git commits/pushes, every Supabase **write** | — |
| **khmer24-scraper** | Sonnet | `../khmer24-scrape/` (its own folder, outside this repo) | anything in `MonoCars/`, Supabase writes, git |
| **reviewer** (on demand) | Haiku/Sonnet | read-only review of another agent's output | any file edits |

Only the lead agent writes to Supabase or pushes to GitHub. Other agents produce files and a report; the lead checks
them (and may push back with questions) before anything is imported.

## Talking to each other

- The lead starts agents with the Agent tool and continues them with `SendMessage` (by agent name).
- A worker agent finishes with a **report**: what it did, what it could not do, where the output files are, and open
  questions. Say plainly what failed — the lead re-checks claims before acting on them.
- Challenge, don't rubber-stamp: when reviewing another agent's output, look for wrong mappings, missing fields,
  duplicates and anything that breaks the rules below.

## Shared rules

1. **No bot-protection workarounds.** If a site shows a Cloudflare / CAPTCHA / "verify you are human" page, stop and
   wait in a visible (headed) browser for the human to solve it. No stealth plugins, proxy rotation, fingerprint
   spoofing or challenge solvers (ignore those parts of `web-scraper/strategies/anti-blocking.md` and
   `proxy-escalation.md`).
2. **Be polite:** one page at a time, at least 3 s between page loads, stop on HTTP 403/429.
3. **No personal data:** never store seller names, phone numbers, Telegram/WhatsApp handles or profile links.
   Car facts, price, location (city/province), photos' URLs and the listing URL are fine.
4. **Secrets** live in `MonoCars/.env.local` (gitignored). Never print them, never write them into other files.
5. Downloaded code (e.g. `../web-scraper`) is reference material: read it, don't run its scripts blindly.

## Current tasks

- **lead:** TikTok remembers seen videos (done), switch discovery from Lexus RX300 to Phnom Penh rental seekers,
  0–100 % post rating, faster `/admin/social` with skeleton loading, then import Khmer24 cars, then commit + push.
- **khmer24-scraper:** STOPPED (2026-10-28). Every Khmer24 page and API answers with a Cloudflare "verify you are
  human" challenge (403), and robots.txt disallows ClaudeBot / anthropic-ai and other AI crawlers. We don't work
  around either, so nothing was collected and the 20 existing cars were **not** deleted. Recon notes + a Nuxt data
  parser are in `../khmer24-scrape/` in case Khmer24 grants permission or a feed. Other ways to fill the catalogue:
  a CSV/JSON the owner is allowed to use (format below), or demo listings.

### Khmer24 output format (`../khmer24-scrape/out/cars.json`)

```json
[{ "source_url": "https://www.khmer24.com/en/...", "listing_id": "…", "brand": "Toyota", "model": "Prius",
   "title": "…", "year": 2010, "price_usd": 14500, "mileage_km": 120000, "body_type": "Sedan",
   "fuel": "Hybrid", "transmission": "Automatic", "color": "White", "engine_cc": 1800, "seats": 5,
   "location": "Phnom Penh", "description": "… (contact details removed)", "images": ["https://…jpg"],
   "posted_at": "2026-10-27" }]
```

Unknown values are `null`. `../khmer24-scrape/out/models.json` lists every model seen with its listing count.

## Database facts (Supabase project `kxsnwdvpkfbyuklflcvf`)

- `cars` (source `user` | `scraped`), `car_images`, `car_features`, lookup tables `brands`, `car_types`,
  `fuel_types`, `transmissions`. `price_label` must be `Good Deal` / `Fair` / `Overpriced`; `year` 1990–2030.
- Social leads: `public_social_posts`, `public_social_comments`, `social_platform_status`.
