# Public Listing Intelligence System

## Architecture and Implementation Specification for an LLM Coding Agent

**Document status:** Design only. Do not implement until the owner explicitly approves an implementation phase.

**Primary use case:** Discover public product listings in Cambodia, beginning with vehicles, evaluate listing screenshots against a configurable product brief, compare qualified candidates, and store auditable results in Supabase.

**Core stack for the first release:** Python, Playwright, an OpenAI vision-capable model through OpenClaw, and Supabase.

**Current architecture decision:** TypeSafe/Jev is deferred. The MVP and initial production candidate must have no runtime, API, schema, queue, or deployment dependency on Jev. A future optional integration may be evaluated only after the base pipeline has labeled data and measured performance.

---

## 1. Instructions to the implementation LLM

Treat this document as the architectural source of truth.

Before writing code:

1. Restate the intended scope and identify any unresolved product decisions.
2. Do not assume that every website permits automated collection.
3. Review each target platform's current terms, robots guidance, API availability, and rate limits.
4. Do not automate CAPTCHA solving, anti-bot bypasses, account creation, private-group access, messaging, commenting, purchasing, or other representational actions.
5. Keep deterministic work in code. Use AI only for semantic tasks that ordinary rules cannot perform reliably.
6. Keep OpenAI, Supabase service-role, and platform credentials server-side.
7. Use strict schemas for every boundary between services.
8. Make every job idempotent, retryable, observable, and auditable.
9. Preserve the source URL and evidence used for every decision.
10. Do not treat an AI score or confidence value as proof. Validate thresholds on labeled examples from the actual target domain.

The first implementation should be a narrow vertical slice on one automation-friendly marketplace. Facebook should be a separate adapter and should not be required for the first successful release.

---

## 2. Product objective

The system accepts a search intent such as:

> Find sedan cars for sale in Cambodia that are good candidates for our product.

It then:

1. Expands the intent into controlled Khmer, English, mixed-language, model, location, and spelling variations.
2. Searches approved public sources through source-specific Playwright adapters.
3. Captures normalized listing metadata and a focused screenshot of each listing.
4. Removes duplicates and obvious non-matches using deterministic rules.
5. Sends only the screenshot and a compact product rubric to OpenClaw's vision model.
6. Receives a strict structured evaluation: good, review, reject, rubric score, evidence quality, visible risks, and missing information.
7. Uses Python to validate and persist the result in Supabase.
8. Uses deterministic Python rules and configurable weighted scores to rank qualified candidates.
9. Presents high-quality candidates for human review or a later approved action.

The system discovers and evaluates public listings. It does **not** contact sellers, post comments, send messages, buy products, or publish listings.

---

## 3. Non-goals

The initial system must not:

- Scrape private profiles, private groups, private messages, or content unavailable to the authorized account.
- Circumvent authentication controls, CAPTCHAs, rate limits, paywalls, or anti-bot protections.
- Infer sensitive personal traits from names, faces, photos, or profiles.
- Store unnecessary seller personal information.
- Let an LLM generate and execute arbitrary browser code at runtime.
- Let an AI response directly write to production tables without Python validation.
- Interpret `best candidate` as `acceptable candidate`; the system must support `none are good enough`.
- Make irreversible or externally visible actions without a separate approval workflow.

---

## 4. Architectural principles

### 4.1 Code owns the workflow

Python owns state transitions, validation, retries, deduplication, threshold enforcement, and database writes. AI returns judgments; it does not own control flow.

### 4.2 Strict outside, flexible inside

Each source has a strict adapter contract. AI may expand keywords or interpret a screenshot, but it cannot invent a source, exceed a query budget, or perform an unapproved action.

### 4.3 Separate observation from inference

Observed facts and inferred judgments must be stored separately.

- Observed: displayed price, visible text, source URL, screenshot, capture time.
- Inferred: vehicle type, apparent condition, product fit, risk, ranking.

### 4.4 Evidence before judgment

No evaluation may exist without an immutable evidence reference: screenshot checksum, capture timestamp, canonical URL, and prompt/rubric version.

### 4.5 Absolute quality before relative ranking

First decide whether a listing is independently acceptable. Only then compare qualified listings against one another.

### 4.6 Version everything that affects a decision

Store versions for:

- Search profile
- Keyword-planner prompt
- Platform adapter
- Screenshot policy
- Vision prompt and JSON schema
- Product brief and rubric
- Deterministic scoring weights
- Threshold policy

---

## 5. System context

```text
Owner / reviewer
       |
       v
Search profile and product brief
       |
       v
Keyword planner -----------> Search plan
       |                           |
       |                           v
       |                  Platform adapters
       |                    /      |      \
       |             Marketplace Dealer Facebook*
       |                    \      |      /
       |                           v
       |                   Playwright browser
       |                           |
       v                           v
Supabase <--- Python pipeline <--- Listings + screenshots
   |               |
   |               +----> OpenClaw vision evaluation
   |               |
   |               +----> Python eligibility and ranking policy
   |
   +----> Review UI, exports, monitoring, audit history

* Facebook is optional and policy-gated.
```

---

## 6. Inside-out domain model

### 6.1 Product brief

The product brief describes what the business offers and what makes a listing relevant.

```json
{
  "product_brief_id": "uuid",
  "name": "Vehicle inspection service",
  "summary": "A pre-purchase inspection service for used-car buyers in Cambodia.",
  "target_customer": "A person actively considering buying a used car in Cambodia.",
  "positive_signals": [
    "Vehicle is explicitly for sale",
    "Location is supported",
    "Listing has useful vehicle details",
    "Listing appears recent",
    "Price and photos are present"
  ],
  "hard_rejections": [
    "Rental only",
    "Spare parts only",
    "Wanted-to-buy post",
    "Outside supported geography",
    "Listing is no longer available"
  ],
  "supported_locations": ["Phnom Penh", "Kandal"],
  "supported_categories": ["sedan"],
  "version": 1
}
```

The brief is input to the keyword planner, the OpenClaw visual evaluator, and Python ranking policy. Keep it short enough to be reused consistently.

### 6.2 Search profile

The search profile is the deterministic configuration for one discovery campaign.

```json
{
  "search_profile_id": "uuid",
  "name": "Cambodia sedans",
  "intent": "Sedan cars for sale in Cambodia",
  "languages": ["km", "en", "mixed"],
  "locations": ["Phnom Penh", "Kandal"],
  "platforms": ["marketplace_a", "dealer_sites"],
  "max_queries_per_run": 20,
  "max_pages_per_query": 5,
  "max_listings_per_run": 500,
  "minimum_listing_age": null,
  "maximum_listing_age_days": 30,
  "enabled": true,
  "version": 1
}
```

### 6.3 Search plan

The keyword planner returns a proposal. Python validates, deduplicates, caps, and approves it before any browser work.

```json
{
  "intent": "sedan cars for sale in Cambodia",
  "queries": [
    {
      "text": "sedan for sale Phnom Penh",
      "language": "en",
      "category": "generic",
      "priority": 90
    },
    {
      "text": "ឡាន sedan លក់ ភ្នំពេញ",
      "language": "mixed",
      "category": "generic",
      "priority": 95
    },
    {
      "text": "Toyota Camry លក់ ភ្នំពេញ",
      "language": "mixed",
      "category": "model",
      "priority": 80
    }
  ],
  "negative_terms": ["rental", "ជួល", "spare parts", "គ្រឿងបន្លាស់"],
  "generated_at": "timestamp",
  "planner_version": "string"
}
```

The prompt must request Khmer, English, and common mixed forms, but generated Khmer terms should be sampled and reviewed by a fluent speaker before production use.

### 6.4 Raw listing observation

This record contains only observed or mechanically derived data.

```json
{
  "listing_id": "uuid",
  "source_platform": "marketplace_a",
  "source_listing_id": "platform identifier if available",
  "source_url": "https://example.com/listing/123",
  "canonical_url": "https://example.com/listing/123",
  "title_raw": "string or null",
  "description_raw": "string or null",
  "price_text_raw": "string or null",
  "location_text_raw": "string or null",
  "seller_display_name": "string or null",
  "published_at_observed": "timestamp or null",
  "captured_at": "timestamp",
  "adapter_version": "string",
  "content_hash": "sha256",
  "screenshot_asset_id": "uuid",
  "observation_payload": {},
  "collection_status": "captured"
}
```

Do not store phone numbers, emails, profile identifiers, or faces unless they are necessary, lawful, and explicitly approved. Prefer business listing facts over seller identity data.

### 6.5 Screenshot evidence

Screenshots should be reproducible and focused.

Store:

- Private object-storage path
- SHA-256 checksum
- Width and height
- MIME type
- Capture timestamp
- Browser viewport
- Source URL
- Crop policy version
- Whether the full listing card, description, price, location, and primary image were visible
- Optional redaction status

Preferred capture order:

1. Listing container screenshot.
2. Main image screenshot if materially useful.
3. Full-page screenshot only for debugging or if required by the rubric.

Avoid sending surrounding feeds, unrelated profiles, chat panels, notifications, or other unnecessary content to the vision model.

### 6.6 Vision evaluation

OpenClaw receives the screenshot plus a compact product brief and rubric. It should not browse, write to Supabase, compare the whole candidate set, or control Playwright in this stage.

The output must follow a strict schema:

```json
{
  "schema_version": "1.0",
  "listing_id": "uuid",
  "decision": "good",
  "fit_score_percent": 84,
  "evidence_quality_percent": 91,
  "visual_condition_level": 4,
  "information_quality_level": 3,
  "apparent_risk_level": 2,
  "visible_signals": [
    "Vehicle is clearly shown",
    "Price is visible",
    "The listing appears to offer the vehicle for sale"
  ],
  "risk_flags": ["Mileage is not visible"],
  "missing_information": ["Service history"],
  "short_reason": "The screenshot shows a relevant sedan sale with adequate details and no major visible concern.",
  "cannot_determine": [],
  "model": "model identifier",
  "prompt_version": "vision-eval-v1",
  "evaluated_at": "timestamp"
}
```

Allowed values:

- `decision`: `good`, `review`, `reject`, `insufficient_evidence`
- Levels: integers with rubric-defined anchors, not unexplained numbers
- Percentages: integers from 0 through 100

`fit_score_percent` is a rubric score, not a statistical probability that the listing is good.

`evidence_quality_percent` measures whether the screenshot contains enough clear evidence for the rubric. It is not a guarantee of correctness.

The vision model must:

- Judge only visible evidence.
- Use `cannot_determine` when a fact is not visible.
- Never invent mileage, year, service history, seller credibility, ownership, accident history, or authenticity.
- Distinguish image quality from vehicle condition.
- Return `insufficient_evidence` when the listing is cropped, blurred, blocked, or missing the material needed for a decision.

### 6.7 Normalized ranking record

Python consumes verified observations and the structured vision evaluation. The ranking input must be a stable, validated record so the scoring policy never reads raw model prose.

```json
{
  "goal": "Rank strong candidates for a vehicle inspection service.",
  "product": {
    "summary": "Pre-purchase inspection for used-car buyers in Cambodia.",
    "hard_rejections": ["rental", "parts only", "wanted to buy", "outside service area"]
  },
  "listing": {
    "id": "uuid",
    "title": "Toyota Prius 2012",
    "price_usd": 12800,
    "location": "Phnom Penh",
    "age_days": 2,
    "vision_decision": "good",
    "fit_score_percent": 84,
    "evidence_quality_percent": 91,
    "visible_signals": ["vehicle shown", "price shown"],
    "risk_flags": ["mileage missing"],
    "missing_information": ["service history"],
    "freshness_score_percent": 95,
    "duplicate_group_size": 1
  }
}
```

### 6.8 Ranking result

Ranking is a separate artifact from listing evaluation.

```json
{
  "ranking_run_id": "uuid",
  "search_profile_id": "uuid",
  "candidate_listing_ids": ["uuid-a", "uuid-b", "uuid-c"],
  "selected_listing_id": "uuid-c",
  "minimum_acceptable_score": 75,
  "selected_composite_score": 87.4,
  "component_scores": {
    "fit": 89,
    "evidence_quality": 82,
    "freshness": 95,
    "risk_penalty": 5
  },
  "ranking_policy_version": "rank-v1",
  "created_at": "timestamp"
}
```

If no candidate reaches `minimum_acceptable_score`, `selected_listing_id` must be `null`. The system must never select a winner merely because one candidate is better than other poor candidates.

---

## 7. Pipeline state machine

Use explicit states and append-only transition events.

```text
discovered
  -> captured
  -> duplicate | prefilter_rejected | vision_pending
  -> vision_processing
  -> vision_good | vision_review | vision_rejected | insufficient_evidence
  -> scoring_pending
  -> scored
  -> eligible | manual_review | rejected
  -> ranked
  -> approved | not_selected | expired

Any processing state
  -> retryable_error
  -> terminal_error
```

Rules:

- A duplicate points to the canonical listing and does not start a second vision job.
- `insufficient_evidence` may trigger one controlled recapture attempt.
- Retries must use an idempotency key.
- A changed screenshot, changed product brief, or changed rubric creates a new evaluation version rather than overwriting history.
- Ranking does not overwrite the listing's independent eligibility result.

---

## 8. Component architecture

### 8.1 Orchestrator

The Python orchestrator coordinates jobs and owns the state machine.

Responsibilities:

- Load an enabled search profile.
- Request or reuse a validated search plan.
- Schedule platform searches within budgets.
- Enqueue capture, deduplication, vision, scoring, and ranking jobs.
- Enforce concurrency and rate limits per platform and account.
- Validate every service response.
- Persist transitions and metrics.
- Stop a platform automatically after repeated blocks or policy errors.

The orchestrator must not contain platform selectors. Selectors belong inside adapters.

### 8.2 Keyword planner

Use an OpenAI text model with Structured Outputs to convert user intent into a bounded `SearchPlan` schema.

Input:

- Product brief
- Search intent
- Supported categories
- Supported locations
- Allowed languages
- Query budget
- Approved brand/model dictionary if available
- Negative keyword policy

Output:

- Search queries with language, category, and priority
- Negative keywords
- Optional rationale for human review, stored outside the runtime plan

Python validation:

- Reject empty queries.
- Normalize whitespace and Unicode.
- Deduplicate case-insensitively.
- Enforce maximum query count and maximum query length.
- Reject unsupported locations or categories.
- Reject prompts that request private data or disallowed actions.
- Allow a reviewer to approve and lock a search plan.

Do not regenerate search terms on every crawl unless the profile or planner version changes.

### 8.3 Platform adapter interface

Every platform adapter must implement the same conceptual contract:

```text
validate_access(context) -> AccessStatus
build_search_url(query, filters) -> URL | null
open_search(page, query, filters) -> SearchPageState
collect_result_refs(page) -> list[ResultRef]
open_listing(page, result_ref) -> ListingPageState
extract_observation(page) -> RawListingObservation
capture_evidence(page) -> ScreenshotEvidence
advance(page) -> AdvanceResult
detect_block(page) -> BlockStatus
```

Each adapter owns:

- Approved entry URLs
- Stable locators and fallback locators
- Expected page states
- Login requirements
- Pagination or scrolling rules
- Per-source rate and concurrency limits
- Screenshot crop target
- Block, CAPTCHA, consent, unavailable, and login-wall detection
- Adapter-specific normalization
- Fixtures and tests

Adapter rules:

- Prefer roles, labels, test IDs, and semantic locators over brittle CSS paths.
- Verify the result of every important browser action.
- Never use random AI-generated JavaScript or selectors in production.
- Runtime browser actions must remain deterministic for the MVP. If selectors become unreliable, repair the adapter rather than adding an AI browser controller.
- Stop immediately on CAPTCHA, explicit automation restriction, repeated login challenge, or access revocation.

### 8.4 Playwright browser worker

Responsibilities:

- Create isolated browser contexts per platform/account.
- Reuse authorized login state only where permitted.
- Apply viewport, locale, timezone, and language settings explicitly.
- Navigate, search, filter, scroll, paginate, extract, and capture screenshots.
- Emit Playwright traces only for errors or sampled debugging runs.
- Close contexts and release resources deterministically.

Operational controls:

- Low, human-scale concurrency by default.
- Per-platform token bucket or leaky-bucket rate limiter.
- Exponential backoff for transient failures.
- No automatic retry for CAPTCHA, access denied, account restriction, or policy block.
- Domain allowlist to prevent unintended navigation.
- Download and upload disabled unless a specific adapter requires and authorizes them.

### 8.5 Deterministic prefilter

Run this before any vision call.

Reject or flag:

- Exact or canonical URL duplicate
- Repeated source listing ID
- Duplicate content hash
- Duplicate screenshot perceptual hash above a tested threshold
- Blocked hard-rejection terms
- Unsupported geography when explicitly known
- Missing screenshot
- Listing marked sold, removed, or unavailable
- Stale listing outside the configured time window

Do not reject ambiguous Khmer text solely because an English-only keyword rule fails. Route ambiguity to semantic evaluation.

### 8.6 OpenClaw vision evaluator

OpenClaw's only responsibility in this pipeline is screenshot evaluation.

It receives:

- One focused screenshot
- Listing ID
- Product summary
- Positive signals
- Hard rejections
- Rubric level descriptions
- Exact JSON Schema
- Instruction to avoid guessing

It returns one structured evaluation. It does not write to Supabase.

Recommended implementation contract:

- One listing per request for traceability.
- Structured Outputs rather than free-form JSON when the chosen OpenAI model/API supports it.
- Low output-token limit.
- Fixed prompt version.
- Request timeout and limited retries.
- Store model identifier, response/request identifiers as permitted, latency, token usage, and validation outcome.
- Treat refusal, timeout, malformed schema, and incomplete response as explicit error states.

### 8.7 Deterministic eligibility service

The MVP uses ordinary Python rules over validated observations and OpenClaw's structured screenshot evaluation.

Responsibilities:

- Apply hard rejections.
- Require minimum evidence quality.
- Route missing or contradictory evidence to manual review.
- Normalize score ranges.
- Produce explicit eligibility reasons.
- Never read raw free-form model text when a structured field exists.

Example eligibility policy:

```text
if vision_decision == "reject":
    reject
elif vision_decision == "insufficient_evidence":
    recapture_or_review
elif evidence_quality_percent < minimum_evidence_quality:
    manual_review
elif apparent_risk_level >= critical_risk_level:
    manual_review
else:
    eligible_for_ranking
```

### 8.8 Composite scoring in Python

Keep business weights in code or configuration, not inside the model prompt.

Example:

```text
composite_score =
    0.35 * product_fit_score
  + 0.25 * buying_intent_score
  + 0.20 * evidence_completeness_score
  + 0.20 * listing_quality_score
```

Apply non-compensating gates separately:

```text
if hard_rejection_detected:
    reject

if evidence_quality_percent < threshold:
    manual_review_or_recapture

if apparent_risk_severity >= critical_level:
    manual_review
```

A high score in one dimension must not cancel a serious hard rejection.

### 8.9 Candidate ranking

Use a two-stage process:

1. SQL/Python shortlist by hard gates, freshness, composite score, and duplicate group.
2. Python sorts the shortlist using a versioned deterministic ranking policy.

For each ranking run, persist compact candidate summaries with stable listing IDs and component scores.

If the candidate list is large:

- Rank with SQL/Python using the same policy version for every candidate.
- Partition by search profile, geography, category, and time window where appropriate.
- Apply a final minimum-score gate after sorting.

Store every candidate's component scores and final composite score, not only the winner.

### 8.10 Persistence worker

Only trusted Python server code writes pipeline results.

Before a write:

- Validate schema.
- Validate enum values and numeric ranges.
- Verify listing and evidence IDs exist.
- Verify the evaluation version has not already been committed.
- Verify screenshot checksum matches the evaluation input.
- Attach model, prompt, rubric, and policy versions.

Use upserts only on stable idempotency keys. Never overwrite immutable evidence or historical evaluations.

---

## 9. Supabase logical data model

The final schema may change during implementation, but preserve these boundaries.

### 9.1 Configuration tables

#### `product_briefs`

- `id`
- `owner_id`
- `name`
- `summary`
- `target_customer`
- `positive_signals` JSONB
- `hard_rejections` JSONB
- `supported_locations` JSONB
- `supported_categories` JSONB
- `version`
- `active`
- timestamps

#### `search_profiles`

- `id`
- `owner_id`
- `product_brief_id`
- `name`
- `intent`
- `languages` JSONB
- `locations` JSONB
- `platforms` JSONB
- crawl budgets
- `version`
- `enabled`
- timestamps

#### `search_terms`

- `id`
- `search_profile_id`
- `text`
- `language`
- `category`
- `priority`
- `planner_version`
- `approved_by`
- `approved_at`
- timestamps

### 9.2 Collection tables

#### `crawl_runs`

- `id`
- `search_profile_id`
- `status`
- planned/started/completed timestamps
- query/listing/error counters
- pipeline version
- failure summary

#### `crawl_queries`

- `id`
- `crawl_run_id`
- `platform`
- `search_term_id`
- `status`
- page/result counters
- block status
- timing and error fields

#### `listings`

- `id`
- platform and platform listing ID
- source and canonical URLs
- observed raw fields
- normalized deterministic fields
- published/captured/last-seen timestamps
- adapter version
- hashes
- canonical duplicate ID
- lifecycle status
- timestamps

Unique constraints should cover the strongest available platform identity and canonical URL hash without preventing versioned observations.

#### `listing_observations`

Append-only snapshots of raw fields and page state for recrawls.

#### `listing_assets`

- `id`
- `listing_id`
- private storage path
- checksum
- perceptual hash
- dimensions and MIME type
- capture/crop/redaction metadata
- timestamps

### 9.3 Evaluation tables

#### `vision_evaluations`

- `id`
- `listing_id`
- `listing_asset_id`
- decision and scores
- visible signals, risks, missing information, cannot-determine fields
- short reason
- model and provider identifiers
- prompt, schema, rubric, and product-brief versions
- raw validated response JSONB
- latency and usage metadata
- timestamps

Unique key recommendation:

```text
(listing_id, listing_asset_id, prompt_version, rubric_version, model)
```

#### `ranking_runs`

- `id`
- `search_profile_id`
- candidate-set hash
- policy version
- status
- selected listing ID, nullable
- minimum acceptable score
- selected composite score
- component-score summary JSONB
- timestamps

#### `ranking_members`

- `ranking_run_id`
- `listing_id`
- input position
- component scores JSONB
- deterministic composite score
- selected flag

### 9.4 Workflow and audit tables

#### `review_tasks`

- listing/evaluation/ranking reference
- review reason
- priority
- status
- assigned reviewer
- reviewer decision and notes
- timestamps

#### `pipeline_events`

Append-only event log containing entity ID, previous state, next state, actor, job ID, idempotency key, reason, and timestamp.

#### `job_failures`

Sanitized error details, attempt count, retry schedule, terminal status, and correlation IDs.

### 9.5 Storage buckets

Use a private bucket for screenshots and traces.

Suggested object layout:

```text
listing-evidence/{owner_id}/{platform}/{yyyy}/{mm}/{listing_id}/{asset_id}.png
```

Use short-lived signed URLs when a worker needs to send an image to a vision model. Do not make the evidence bucket public.

### 9.6 Supabase security

- Enable RLS on every exposed table.
- Revoke default grants and grant only required operations.
- Scope authenticated access by `owner_id` or organization membership.
- Keep `service_role` and secret keys only in server-side workers.
- Do not use user-editable metadata for authorization.
- Use separate policies for select, insert, update, and delete.
- Test allow and deny behavior for every policy.
- Treat views carefully; use security-invoker behavior where supported or keep privileged views unexposed.
- Keep system-maintained evaluation and audit tables read-only to normal clients.
- Consider a private schema for internal worker tables.

### 9.7 Queues

For the first prototype, a conventional `jobs` table with row locking may be sufficient.

For production background processing, Supabase Queues can carry durable jobs such as:

- `capture_listing`
- `evaluate_screenshot`
- `score_listing`
- `rank_candidates`
- `recapture_evidence`

Queue messages contain IDs, versions, and idempotency keys—not large screenshots or full secrets.

Archive or retain failed messages for investigation. Configure an appropriate visibility window and retry policy for each job class.

---

## 10. End-to-end workflows

### 10.1 Search planning

```text
Owner creates search profile
 -> Python loads product brief and dictionaries
 -> OpenAI generates structured search plan
 -> Python validates, deduplicates, and caps terms
 -> Optional human review of Khmer and model variations
 -> Approved terms stored and versioned
```

### 10.2 Collection

```text
Scheduler starts crawl run
 -> Orchestrator creates platform/query jobs
 -> Adapter validates access
 -> Playwright opens approved search URL
 -> Adapter searches and collects result references
 -> Each listing is opened and observed
 -> Focused screenshot is captured
 -> Observation and evidence metadata are persisted
 -> Deduplication and prefilter run
```

### 10.3 Screenshot evaluation

```text
Eligible listing enters vision_pending
 -> Worker creates a short-lived evidence URL or safe image payload
 -> Worker sends screenshot + product rubric to OpenClaw
 -> OpenClaw returns schema-constrained evaluation
 -> Python validates all fields and ranges
 -> Result is stored as an immutable evaluation
 -> Listing moves to good, review, reject, or insufficient_evidence
```

### 10.4 Python eligibility and scoring

```text
Python loads validated observations and the vision evaluation
 -> Python applies hard rejections and evidence thresholds
 -> Python calculates versioned component scores
 -> Python calculates the deterministic composite score
 -> Listing becomes eligible, manual_review, or rejected
```

### 10.5 Ranking

```text
Python queries eligible listings for a ranking window
 -> Remove duplicates and stale listings
 -> Create deterministic shortlist
 -> Python sorts all candidates with the same policy version
 -> Python applies the minimum acceptable score
 -> The highest qualifying result becomes recommended
 -> Ties, missing evidence, and near-threshold cases create review tasks
 -> Ranking run and all members are persisted
```

### 10.6 Recrawl and change detection

```text
Previously active listing is revisited
 -> New observation is captured
 -> Compare price, availability, text, and image hashes
 -> No material change: update last_seen only
 -> Material change: store new observation and evaluate affected dimensions
 -> Removed/sold: mark lifecycle status without deleting history
```

---

## 11. Decision policy

Initial thresholds are hypotheses and must be calibrated.

Example vision routing:

```text
decision = reject
    if a hard rejection is visibly clear

decision = insufficient_evidence
    if evidence_quality_percent < 50

decision = good
    if fit_score_percent >= 80
   and evidence_quality_percent >= 75
   and apparent_risk_level <= 2

decision = review
    otherwise
```

Example ranking routing:

```text
automatic recommendation
    only if independent eligibility gates pass
   and composite score reaches the validated minimum
   and required evidence is complete

manual review
    if material evidence is missing
    or the top candidates are close
    or the result is near the minimum threshold
```

Never reuse thresholds from a demo without measuring them on labeled production-like data.

---

## 12. Prompt contracts

### 12.1 Keyword-planner contract

System intent:

```text
Generate a bounded multilingual search plan for approved public listing sources.
Return only the provided schema. Do not include private-data searches, contact actions,
platform bypass instructions, or unsupported locations. Include Khmer, English, and
mixed-language variants when appropriate. Respect the exact query budget.
```

Input fields:

- User intent
- Product brief
- Approved locations
- Approved categories
- Brand/model dictionary
- Negative concepts
- Query limit

### 12.2 OpenClaw screenshot-evaluator contract

System intent:

```text
Evaluate only the visible evidence in this listing screenshot against the supplied
product rubric. Do not browse, infer hidden facts, identify people, or guess missing
vehicle details. Return only the required schema. If the screenshot is insufficient,
choose insufficient_evidence and list what cannot be determined.
```

Rubric descriptions must anchor each level. For example:

```text
visual_condition_level:
1 = major visible damage or unusable evidence
2 = visible concerns that materially reduce apparent condition
3 = ordinary used condition with no clear major concern
4 = clean apparent condition with good supporting views
5 = exceptionally clear evidence of excellent apparent condition
```

The model must be reminded that apparent visual condition is not mechanical condition.

### 12.3 Deterministic ranking contract

The ranking function accepts normalized candidate records and a versioned policy object.

Required inputs:

- Stable listing ID
- Eligibility status
- Fit score
- Evidence-quality score
- Freshness score
- Apparent-risk level
- Hard-rejection flags
- Missing-information flags
- Duplicate-group identity

The function must produce component scores, penalties, final composite score, qualification result, and explicit reason codes. Sorting must be stable and deterministic. If no candidate reaches the minimum acceptable score, the result must contain no selected listing.

---

## 13. Facebook strategy

Facebook is technically navigable with Playwright, but production automation is high-risk and brittle. Public visibility does not automatically grant permission for automated collection.

Implement Facebook only after:

1. Reviewing current Meta terms and available official APIs.
2. Defining exactly which public surfaces are authorized.
3. Confirming whether an authenticated session may be automated for the intended use.
4. Establishing low-volume limits and account-isolation controls.
5. Creating explicit stop conditions for CAPTCHA, checkpoints, warnings, and blocks.

The Facebook adapter must not:

- Access private groups or private profiles.
- Collect friends, contacts, private messages, or unrelated personal information.
- Automate seller contact, likes, reactions, comments, or posts.
- Hide automation, rotate identities to evade controls, or bypass enforcement.
- Treat a login session as blanket authorization for bulk collection.

Preferred rollout order:

1. Stable public marketplace or dealer website.
2. Public dealer pages or sources with explicit automation permission.
3. Facebook as an optional supervised source, if authorized.

If Facebook cannot be used compliantly and reliably, support manual URL submission: a user supplies a permitted listing URL, Playwright captures that page, and the rest of the evaluation pipeline remains unchanged.

---

## 14. Reliability and failure handling

### 14.1 Idempotency keys

Examples:

```text
crawl query: hash(crawl_run_id, platform, search_term_id, page_cursor)
capture: hash(platform, canonical_url, observation_version)
vision: hash(listing_asset_checksum, prompt_version, rubric_version, model)
ranking: hash(sorted_candidate_ids, ranking_policy_version, evidence_versions)
```

### 14.2 Retry classes

Retryable:

- Network timeout
- Temporary DNS or server error
- 429 with honored retry guidance
- Browser crash
- Transient model-provider failure

Not automatically retryable:

- CAPTCHA
- Account restriction
- Permission denied
- Schema validation failure after a limited repair attempt
- Unsupported page state
- Explicit terms or policy restriction

### 14.3 Dead-letter behavior

After the configured retry count:

- Mark the job terminal.
- Preserve sanitized diagnostics.
- Create a review task if the listing remains valuable.
- Do not silently drop the listing.

---

## 15. Observability

Track at minimum:

- Queries attempted per platform
- Search pages processed
- Listings discovered, captured, duplicated, rejected, and evaluated
- CAPTCHA/block/login-wall counts
- Adapter failure rate by version
- Screenshot success and evidence-quality distribution
- Vision decision distribution
- Composite-score and eligibility-status distribution
- Human override rate
- Precision of `good` decisions on reviewed samples
- False-rejection and false-approval rates
- Cost and latency per accepted listing
- Model tokens and API errors
- Queue age and retry counts

Every log entry should include correlation IDs for crawl run, query job, listing, evidence, evaluation, and ranking run. Do not log secrets, session cookies, signed URLs, or unnecessary personal data.

---

## 16. Testing strategy

### 16.1 Unit tests

- URL canonicalization
- Query normalization and budget enforcement
- Price/location/date parsers
- Hashing and deduplication
- State-machine transition rules
- JSON-schema validation
- Composite scoring and hard gates
- Idempotency-key stability
- Retention and redaction rules

### 16.2 Adapter contract tests

Use saved, permitted HTML fixtures and screenshots.

Test:

- Search result extraction
- Listing extraction
- Pagination/scroll termination
- Consent and login states
- Sold/removed listing detection
- CAPTCHA/block detection
- Screenshot crop correctness
- Selector fallback behavior

### 16.3 AI evaluation tests

Build a labeled evaluation set containing:

- Clear good listings
- Clear rejections
- Rentals, parts, wanted-to-buy posts
- Khmer, English, and mixed-language listings
- Blurry, cropped, and blocked screenshots
- Missing prices or locations
- Duplicate listings
- Suspiciously attractive listings
- Near-threshold cases

Measure:

- Schema-valid response rate
- Accuracy by decision class
- Calibration of fit bands and evidence quality
- Human override rate
- Performance by language and platform
- Stability across prompt/model versions

### 16.4 Ranking-policy tests

- Verify hard rejections cannot be offset by positive component scores.
- Verify no listing is selected when all candidates are below the minimum.
- Verify sorting is deterministic for identical input and policy versions.
- Verify ties route to the documented tie-breaker or manual review.
- Test missing fields and near-threshold values.
- Store exact component scores, reason codes, and policy version for every test.

### 16.5 Security tests

- RLS allow/deny tests for each table and operation
- Private bucket access tests
- Signed URL expiration
- Secret scanning
- Domain allowlist enforcement
- SSRF-resistant URL validation
- Malicious page text treated as untrusted content, not instructions
- Prompt injection fixtures embedded in listing descriptions and screenshots

---

## 17. Privacy, safety, and data governance

- Collect only data necessary to evaluate a public listing.
- Avoid face recognition and sensitive-trait inference.
- Keep screenshots private and define a retention period.
- Support deletion of captured evidence when required.
- Preserve audit history without retaining unnecessary raw personal data.
- Hash or redact identifiers where full values are not needed.
- Maintain an allowlist of approved domains and surfaces.
- Treat page content, comments, and screenshots as untrusted input that cannot change system instructions.
- Require explicit owner approval before adding a new platform or externally visible action.

---

## 18. Deployment topology

Initial deployment:

```text
Python scheduler/orchestrator
Python Playwright worker
Python AI evaluation worker
Supabase Postgres + private Storage
OpenClaw gateway/model access
```

Scale-out deployment:

```text
Scheduler
   |
Supabase Queues
   |----------------------|----------------------|
Capture workers       Vision workers         Scoring/ranking workers
   |                      |                      |
Playwright            OpenClaw/OpenAI          Python policy
   |                      |                      |
   |------------------ Supabase ----------------|
```

Separate browser workers from API workers so browser crashes and platform sessions cannot expose database or model credentials unnecessarily.

---

## 19. Recommended implementation phases

### Phase 0: Product calibration

- Finalize product brief.
- Define good/review/reject examples.
- Label an initial screenshot set.
- Confirm approved sources and allowed behavior.
- Review Khmer search vocabulary.

### Phase 1: One-source vertical slice

- One stable source adapter
- Manual fixed search terms
- Playwright capture
- Private screenshot storage
- OpenClaw structured screenshot evaluation
- Python validation and Supabase persistence
- Manual review screen or export

Success condition: the full pipeline processes a small controlled sample with complete auditability.

### Phase 2: Intelligent search planning

- OpenAI structured keyword planner
- Khmer/English/mixed query review
- Query budgets and negative terms
- Search-plan versioning

### Phase 3: Deterministic scoring and ranking

- Python eligibility gates
- Versioned component scores
- Composite scoring and penalties
- Minimum-acceptable-score rule
- Tie and near-threshold review routing

### Phase 4: Production reliability

- Durable queues
- Retry and dead-letter policies
- Monitoring and cost controls
- Adapter fixtures and regression tests
- RLS and security test suite

### Phase 5: Additional sources

- Add sources one at a time.
- Require adapter contract tests and a policy review.
- Consider Facebook only as a separately approved supervised adapter.

---

## 20. Acceptance criteria for the first production candidate

The system is ready for limited production only when:

- At least one platform adapter passes contract tests.
- Every source has documented permission and rate-limit assumptions.
- Every listing has a canonical URL and evidence checksum.
- Vision responses are schema-valid at the required rate.
- Missing evidence leads to review rather than invented facts.
- Duplicate listings do not create repeated paid evaluations.
- Ranking selects no winner when no listing reaches the minimum acceptable score.
- Every ranking result stores component scores, reason codes, and policy version.
- Thresholds have been evaluated on labeled Cambodia-focused examples.
- Human override rates are measured.
- All exposed Supabase tables have tested RLS and minimal grants.
- Service secrets are absent from clients, logs, and repository history.
- Facebook is not a critical dependency.
- CAPTCHA and access blocks stop automation.
- No external messages, comments, posts, or purchases can occur.

---

## 21. Open decisions for the owner

The implementation LLM must ask for these before building:

1. What exact product is being matched to listings?
2. Which first marketplace is approved?
3. Which Cambodian locations are supported?
4. Which vehicle categories, brands, years, and prices are in scope?
5. What makes a listing commercially useful?
6. What are the hard rejection conditions?
7. How long may screenshots and raw listing text be retained?
8. Is a human required to approve every recommendation initially?
9. What daily query and listing budgets are acceptable?
10. Is Facebook authorized, and for which exact public surfaces?
11. Should seller contact information be excluded entirely?
12. What review accuracy is required before automatic recommendation is enabled?

---

## 22. Final architectural recommendation

Start with this narrow path:

```text
Approved search terms
 -> one strict Playwright adapter
 -> deterministic deduplication
 -> focused screenshot
 -> OpenClaw structured vision evaluation
 -> Python validation
 -> Supabase staging and review
```

Then add:

```text
OpenAI keyword expansion
 -> Python composite policy
 -> deterministic Python ranking
 -> durable queues
 -> additional approved sources
```

This division keeps each tool in the role where it is strongest:

- **Playwright:** deterministic browser execution and evidence capture.
- **OpenAI keyword planner:** bounded multilingual query generation.
- **OpenClaw vision model:** screenshot interpretation with strict structured output.
- **Python:** validation, orchestration, rules, scoring, retries, and database writes.
- **Supabase:** durable records, private evidence storage, queues, authorization, and audit history.
- **Human reviewer:** ambiguous, low-confidence, policy-sensitive, and high-impact decisions.

The system should become more automated only after its decisions are measured against real labeled examples.

---

## 23. Source documentation for the implementation agent

- OpenAI Structured Outputs: <https://developers.openai.com/api/docs/guides/structured-outputs>
- OpenAI Responses API: <https://developers.openai.com/api/reference/resources/responses/methods/create>
- Supabase Queues: <https://supabase.com/docs/guides/queues>
- Supabase Storage: <https://supabase.com/docs/guides/storage>
- Supabase Row Level Security: <https://supabase.com/docs/guides/database/postgres/row-level-security>
- Supabase Database Webhooks: <https://supabase.com/docs/guides/database/webhooks>
- Facebook scraping explanation: <https://www.facebook.com/help/463983701520800>

### Deferred option: TypeSafe/Jev

Jev is deliberately outside the MVP. Do not install its SDK, create Jev tables, add Jev queues, or call its API in the initial implementation. If deterministic ranking later proves insufficient, evaluate Jev in a separate experiment against the labeled dataset and compare accuracy, cost, latency, and human override rate before adopting it. Reference index: <https://docs.typesafe.ai/llms.txt>.
