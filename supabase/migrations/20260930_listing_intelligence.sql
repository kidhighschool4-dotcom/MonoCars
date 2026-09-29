-- ============================================================================
-- Public Listing Intelligence System — schema (PUBLIC_LISTING_INTELLIGENCE_ARCHITECTURE.md §9)
--
-- Access model
--   * Only the Python worker (service_role) writes. It bypasses RLS.
--   * anon: no access at all.
--   * authenticated: SELECT only, and RLS limits rows to admins
--     (auth.jwt() -> app_metadata.role = 'admin'; app_metadata is NOT user-editable).
--   * Evidence screenshots live in the private bucket `listing-evidence`.
-- Safe to re-run: CREATE ... IF NOT EXISTS / DROP POLICY IF EXISTS.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Admin check used by every read policy
CREATE OR REPLACE FUNCTION public.li_is_admin()
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT coalesce((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin', false)
$$;

-- ─── 9.1 Configuration ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS product_briefs (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id             uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  slug                 text NOT NULL,
  name                 text NOT NULL,
  summary              text NOT NULL,
  target_customer      text NOT NULL,
  positive_signals     jsonb NOT NULL DEFAULT '[]',
  hard_rejections      jsonb NOT NULL DEFAULT '[]',
  supported_locations  jsonb NOT NULL DEFAULT '[]',
  supported_categories jsonb NOT NULL DEFAULT '[]',
  version              integer NOT NULL DEFAULT 1 CHECK (version > 0),
  active               boolean NOT NULL DEFAULT true,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (slug, version)
);

CREATE TABLE IF NOT EXISTS search_profiles (
  id                       uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id                 uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  product_brief_id         uuid NOT NULL REFERENCES product_briefs(id) ON DELETE RESTRICT,
  slug                     text NOT NULL,
  name                     text NOT NULL,
  intent                   text NOT NULL,
  languages                jsonb NOT NULL DEFAULT '["km","en","mixed"]',
  locations                jsonb NOT NULL DEFAULT '[]',
  platforms                jsonb NOT NULL DEFAULT '[]',
  max_queries_per_run      integer NOT NULL DEFAULT 20  CHECK (max_queries_per_run BETWEEN 1 AND 200),
  max_pages_per_query      integer NOT NULL DEFAULT 5   CHECK (max_pages_per_query BETWEEN 1 AND 50),
  max_listings_per_run     integer NOT NULL DEFAULT 500 CHECK (max_listings_per_run BETWEEN 1 AND 5000),
  maximum_listing_age_days integer          CHECK (maximum_listing_age_days IS NULL OR maximum_listing_age_days > 0),
  version                  integer NOT NULL DEFAULT 1 CHECK (version > 0),
  enabled                  boolean NOT NULL DEFAULT true,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (slug, version)
);

CREATE TABLE IF NOT EXISTS search_terms (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  search_profile_id uuid NOT NULL REFERENCES search_profiles(id) ON DELETE CASCADE,
  text              text NOT NULL CHECK (length(text) BETWEEN 1 AND 120),
  text_normalized   text NOT NULL,
  language          text NOT NULL CHECK (language IN ('km','en','mixed')),
  category          text NOT NULL CHECK (category IN ('generic','model','location','brand')),
  priority          integer NOT NULL CHECK (priority BETWEEN 0 AND 100),
  planner_version   text NOT NULL,
  source            text NOT NULL DEFAULT 'planner' CHECK (source IN ('planner','seed','manual')),
  approved_by       text,
  approved_at       timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (search_profile_id, text_normalized, planner_version)
);

-- ─── 9.2 Collection ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS crawl_runs (
  id                 uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  search_profile_id  uuid NOT NULL REFERENCES search_profiles(id) ON DELETE RESTRICT,
  status             text NOT NULL DEFAULT 'planned'
                     CHECK (status IN ('planned','running','completed','completed_with_errors','stopped_blocked','failed')),
  pipeline_version   text NOT NULL,
  planned_at         timestamptz NOT NULL DEFAULT now(),
  started_at         timestamptz,
  completed_at       timestamptz,
  queries_attempted  integer NOT NULL DEFAULT 0,
  pages_processed    integer NOT NULL DEFAULT 0,
  listings_found     integer NOT NULL DEFAULT 0,
  listings_captured  integer NOT NULL DEFAULT 0,
  duplicates         integer NOT NULL DEFAULT 0,
  prefilter_rejected integer NOT NULL DEFAULT 0,
  blocks             integer NOT NULL DEFAULT 0,
  errors             integer NOT NULL DEFAULT 0,
  failure_summary    text
);

CREATE TABLE IF NOT EXISTS crawl_queries (
  id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  crawl_run_id     uuid NOT NULL REFERENCES crawl_runs(id) ON DELETE CASCADE,
  platform         text NOT NULL,
  search_term_id   uuid REFERENCES search_terms(id) ON DELETE SET NULL,
  query_text       text,
  idempotency_key  text NOT NULL UNIQUE,
  status           text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','running','completed','blocked','failed','skipped')),
  pages_processed  integer NOT NULL DEFAULT 0,
  results_found    integer NOT NULL DEFAULT 0,
  block_status     text,
  started_at       timestamptz,
  completed_at     timestamptz,
  error            text
);

CREATE TABLE IF NOT EXISTS listings (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_platform      text NOT NULL,
  source_listing_id    text,
  source_url           text NOT NULL,
  canonical_url        text NOT NULL,
  canonical_url_hash   text NOT NULL,
  -- observed (latest)
  title_raw            text,
  description_raw      text,
  price_text_raw       text,
  location_text_raw    text,
  seller_display_name  text,
  published_at_observed timestamptz,
  -- normalized, deterministic
  price_usd            integer CHECK (price_usd IS NULL OR price_usd >= 0),
  location_normalized  text,
  category_normalized  text,
  -- bookkeeping
  first_captured_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at         timestamptz NOT NULL DEFAULT now(),
  adapter_version      text NOT NULL,
  content_hash         text NOT NULL,
  duplicate_of         uuid REFERENCES listings(id) ON DELETE SET NULL,
  lifecycle_status     text NOT NULL DEFAULT 'discovered' CHECK (lifecycle_status IN (
                         'discovered','captured','duplicate','prefilter_rejected','vision_pending',
                         'vision_processing','vision_good','vision_review','vision_rejected','insufficient_evidence',
                         'scoring_pending','scored','eligible','manual_review','rejected','ranked',
                         'approved','not_selected','expired','retryable_error','terminal_error')),
  status_reason        text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (canonical_url_hash)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_listings_platform_id
  ON listings(source_platform, source_listing_id) WHERE source_listing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_listings_status  ON listings(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_listings_content ON listings(content_hash);

CREATE TABLE IF NOT EXISTS listing_observations (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  listing_id           uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  crawl_run_id         uuid REFERENCES crawl_runs(id) ON DELETE SET NULL,
  captured_at          timestamptz NOT NULL,
  adapter_version      text NOT NULL,
  content_hash         text NOT NULL,
  observation_payload  jsonb NOT NULL,
  page_state           text NOT NULL,
  UNIQUE (listing_id, content_hash)
);

CREATE TABLE IF NOT EXISTS listing_assets (
  id                    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  listing_id            uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  storage_path          text NOT NULL,
  checksum_sha256       text NOT NULL,
  perceptual_hash       text,
  width                 integer NOT NULL CHECK (width > 0),
  height                integer NOT NULL CHECK (height > 0),
  mime_type             text NOT NULL,
  captured_at           timestamptz NOT NULL,
  viewport              jsonb NOT NULL,
  source_url            text NOT NULL,
  crop_policy_version   text NOT NULL,
  visibility            jsonb NOT NULL DEFAULT '{}',
  redaction_status      text NOT NULL DEFAULT 'none',
  created_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (listing_id, checksum_sha256)
);

-- ─── 9.3 Evaluation ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vision_evaluations (
  id                        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  listing_id                uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  listing_asset_id          uuid NOT NULL REFERENCES listing_assets(id) ON DELETE CASCADE,
  idempotency_key           text NOT NULL UNIQUE,
  model_decision            text NOT NULL CHECK (model_decision IN ('good','review','reject','insufficient_evidence')),
  decision                  text NOT NULL CHECK (decision IN ('good','review','reject','insufficient_evidence')),
  fit_score_percent         integer NOT NULL CHECK (fit_score_percent BETWEEN 0 AND 100),
  evidence_quality_percent  integer NOT NULL CHECK (evidence_quality_percent BETWEEN 0 AND 100),
  visual_condition_level    integer NOT NULL CHECK (visual_condition_level BETWEEN 1 AND 5),
  information_quality_level integer NOT NULL CHECK (information_quality_level BETWEEN 1 AND 5),
  apparent_risk_level       integer NOT NULL CHECK (apparent_risk_level BETWEEN 1 AND 5),
  hard_rejections_detected  jsonb NOT NULL DEFAULT '[]',
  visible_signals           jsonb NOT NULL DEFAULT '[]',
  risk_flags                jsonb NOT NULL DEFAULT '[]',
  missing_information       jsonb NOT NULL DEFAULT '[]',
  cannot_determine          jsonb NOT NULL DEFAULT '[]',
  short_reason              text NOT NULL,
  provider                  text NOT NULL,
  model                     text NOT NULL,
  prompt_version            text NOT NULL,
  schema_version            text NOT NULL,
  rubric_version            text NOT NULL,
  product_brief_id          uuid REFERENCES product_briefs(id) ON DELETE SET NULL,
  product_brief_version     integer NOT NULL,
  input_checksum_sha256     text NOT NULL,
  raw_response              jsonb NOT NULL,
  latency_ms                integer,
  usage                     jsonb,
  evaluated_at              timestamptz NOT NULL,
  created_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (listing_id, listing_asset_id, prompt_version, rubric_version, model)
);

CREATE TABLE IF NOT EXISTS listing_scores (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  listing_id           uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  vision_evaluation_id uuid NOT NULL REFERENCES vision_evaluations(id) ON DELETE CASCADE,
  policy_version       text NOT NULL,
  eligibility          text NOT NULL CHECK (eligibility IN ('eligible','manual_review','rejected')),
  reason_codes         jsonb NOT NULL DEFAULT '[]',
  component_scores     jsonb NOT NULL,
  penalties            jsonb NOT NULL DEFAULT '{}',
  composite_score      numeric(6,2) NOT NULL CHECK (composite_score BETWEEN 0 AND 100),
  scored_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (vision_evaluation_id, policy_version)
);

CREATE TABLE IF NOT EXISTS ranking_runs (
  id                        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  search_profile_id         uuid REFERENCES search_profiles(id) ON DELETE SET NULL,
  idempotency_key           text NOT NULL UNIQUE,
  candidate_set_hash        text NOT NULL,
  policy_version            text NOT NULL,
  status                    text NOT NULL CHECK (status IN ('recommended','no_qualifying_candidate','manual_review','empty')),
  selected_listing_id       uuid REFERENCES listings(id) ON DELETE SET NULL,
  minimum_acceptable_score  numeric(6,2) NOT NULL,
  selected_composite_score  numeric(6,2),
  component_score_summary   jsonb NOT NULL DEFAULT '{}',
  reason_codes              jsonb NOT NULL DEFAULT '[]',
  created_at                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ranking_members (
  ranking_run_id   uuid NOT NULL REFERENCES ranking_runs(id) ON DELETE CASCADE,
  listing_id       uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  input_position   integer NOT NULL,
  rank_position    integer NOT NULL,
  component_scores jsonb NOT NULL,
  composite_score  numeric(6,2) NOT NULL,
  qualified        boolean NOT NULL,
  selected         boolean NOT NULL DEFAULT false,
  reason_codes     jsonb NOT NULL DEFAULT '[]',
  PRIMARY KEY (ranking_run_id, listing_id)
);

-- ─── 9.4 Workflow and audit ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS review_tasks (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  listing_id           uuid REFERENCES listings(id) ON DELETE CASCADE,
  vision_evaluation_id uuid REFERENCES vision_evaluations(id) ON DELETE SET NULL,
  ranking_run_id       uuid REFERENCES ranking_runs(id) ON DELETE SET NULL,
  idempotency_key      text NOT NULL UNIQUE,
  reason               text NOT NULL,
  priority             integer NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
  status               text NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','resolved','dismissed')),
  assigned_reviewer    uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  reviewer_decision    text CHECK (reviewer_decision IN ('approve','reject','needs_more_evidence')),
  reviewer_notes       text,
  resolved_at          timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status, priority DESC);

CREATE TABLE IF NOT EXISTS pipeline_events (
  id              bigserial PRIMARY KEY,
  entity_type     text NOT NULL,
  entity_id       uuid NOT NULL,
  previous_state  text,
  next_state      text NOT NULL,
  actor           text NOT NULL,
  job_id          text,
  idempotency_key text UNIQUE,
  reason          text,
  metadata        jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_entity ON pipeline_events(entity_type, entity_id, created_at);

CREATE TABLE IF NOT EXISTS job_failures (
  id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_type        text NOT NULL,
  entity_id       uuid,
  idempotency_key text,
  error_class     text NOT NULL,
  error_message   text NOT NULL,
  retryable       boolean NOT NULL,
  attempt         integer NOT NULL DEFAULT 1,
  terminal        boolean NOT NULL DEFAULT false,
  correlation     jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Append-only guards: history is never rewritten
CREATE OR REPLACE FUNCTION public.li_forbid_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;
DROP TRIGGER IF EXISTS trg_pipeline_events_append_only ON pipeline_events;
CREATE TRIGGER trg_pipeline_events_append_only BEFORE UPDATE OR DELETE ON pipeline_events
  FOR EACH ROW EXECUTE FUNCTION public.li_forbid_mutation();
DROP TRIGGER IF EXISTS trg_vision_evaluations_immutable ON vision_evaluations;
CREATE TRIGGER trg_vision_evaluations_immutable BEFORE UPDATE ON vision_evaluations
  FOR EACH ROW EXECUTE FUNCTION public.li_forbid_mutation();
DROP TRIGGER IF EXISTS trg_listing_assets_immutable ON listing_assets;
CREATE TRIGGER trg_listing_assets_immutable BEFORE UPDATE ON listing_assets
  FOR EACH ROW EXECUTE FUNCTION public.li_forbid_mutation();

-- ─── 9.6 Security: RLS + minimal grants ─────────────────────────────────────

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'product_briefs','search_profiles','search_terms','crawl_runs','crawl_queries','listings',
    'listing_observations','listing_assets','vision_evaluations','listing_scores','ranking_runs',
    'ranking_members','review_tasks','pipeline_events','job_failures'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
    EXECUTE format('DROP POLICY IF EXISTS li_admin_read ON public.%I', t);
    EXECUTE format('CREATE POLICY li_admin_read ON public.%I FOR SELECT TO authenticated USING (public.li_is_admin())', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
  END LOOP;
END $$;
REVOKE ALL ON SEQUENCE public.pipeline_events_id_seq FROM anon, authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.pipeline_events_id_seq TO service_role;

-- ─── 9.5 Private evidence bucket ────────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('listing-evidence', 'listing-evidence', false, 10485760, ARRAY['image/png','image/jpeg','image/webp'])
ON CONFLICT (id) DO UPDATE SET public = false;
-- No storage.objects policies for this bucket: only service_role (server) can read/write,
-- and reviewers get short-lived signed URLs minted server-side.
