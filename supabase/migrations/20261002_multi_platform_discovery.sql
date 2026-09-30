-- Multi-platform discovery (Tier 1–3 adapters) on top of 20261001_public_social_generalized.sql.
-- 1) widen platform / content-type checks to every registered adapter
-- 2) RX300 lead typing columns on posts and comments (confirmed_rx300_buyer | potential_rx300_fit | seller_or_dealer | irrelevant)
-- 3) organizations (dealers, shops, business pages/channels) stored APART from buyer leads
-- 4) per-platform worker status for the dashboard (state, failures, circuit breaker, last success, next run)
-- Same RLS pattern: owner may SELECT own rows; no client writes; service role writes. Idempotent.

-- ─── 1) platform / content-type checks ─────────────────────────────────────
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT c.conrelid::regclass AS tbl, c.conname FROM pg_constraint c
           WHERE c.contype = 'c' AND c.conrelid IN ('public.public_social_posts'::regclass, 'public.public_social_comments'::regclass,
                                                   'public.public_social_post_skips'::regclass)
             AND (pg_get_constraintdef(c.oid) ILIKE '%platform%= ANY%' OR pg_get_constraintdef(c.oid) ILIKE '%source_content_type%= ANY%')
  LOOP
    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
  END LOOP;
END $$;

ALTER TABLE public.public_social_posts ADD CONSTRAINT psp_platform_chk CHECK (platform IN
  ('facebook','facebook_marketplace','instagram','tiktok','reddit','youtube','x','threads','telegram','pinterest','bluesky',
   'mastodon','forum','classifieds','web'));
ALTER TABLE public.public_social_posts ADD CONSTRAINT psp_content_type_chk CHECK (source_content_type IN
  ('facebook_post','facebook_marketplace_listing','instagram_post','instagram_reel','tiktok_video','reddit_post','youtube_video',
   'x_post','threads_post','telegram_channel_post','pinterest_pin','bluesky_post','mastodon_status','forum_thread',
   'classified_listing','web_page'));
ALTER TABLE public.public_social_comments ADD CONSTRAINT psc_platform_chk CHECK (platform IN
  ('facebook','facebook_marketplace','instagram','tiktok','reddit','youtube','x','threads','telegram','pinterest','bluesky',
   'mastodon','forum','classifieds','web'));
ALTER TABLE public.public_social_post_skips ADD CONSTRAINT pss_platform_chk CHECK (platform IN
  ('facebook','facebook_marketplace','instagram','tiktok','reddit','youtube','x','threads','telegram','pinterest','bluesky',
   'mastodon','forum','classifieds','web'));

-- ─── 3) organizations (before posts reference them) ─────────────────────────
CREATE TABLE IF NOT EXISTS public.public_social_organizations (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id      uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  platform      text NOT NULL,
  name          text NOT NULL CHECK (length(name) BETWEEN 1 AND 300),
  url           text CHECK (url IS NULL OR length(url) <= 2000),
  kind          text NOT NULL CHECK (kind IN ('dealer','shop','page','channel','marketplace_seller','forum','media','other')),
  evidence      text NOT NULL CHECK (length(evidence) BETWEEN 1 AND 500),   -- why it is considered organizational
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL DEFAULT now() + interval '365 days'
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pso_owner_platform_name ON public.public_social_organizations(owner_id, platform, name);
COMMENT ON TABLE public.public_social_organizations IS
  'Clearly organizational accounts (dealers, shops, business pages/channels). Never private individuals; never buyer leads.';

-- ─── 2) lead typing ─────────────────────────────────────────────────────────
ALTER TABLE public.public_social_posts
  ADD COLUMN IF NOT EXISTS author_key         text CHECK (author_key IS NULL OR author_key ~ '^[0-9a-f]{64}$'),
  ADD COLUMN IF NOT EXISTS author_key_version text,
  ADD COLUMN IF NOT EXISTS organization_id    uuid REFERENCES public.public_social_organizations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS lead_type          text CHECK (lead_type IS NULL OR lead_type IN
                                                ('confirmed_rx300_buyer','potential_rx300_fit','seller_or_dealer','irrelevant')),
  ADD COLUMN IF NOT EXISTS lead               jsonb,
  ADD COLUMN IF NOT EXISTS source_adapter     text;

ALTER TABLE public.public_social_comments
  ADD COLUMN IF NOT EXISTS lead_type         text CHECK (lead_type IS NULL OR lead_type IN
                                               ('confirmed_rx300_buyer','potential_rx300_fit','seller_or_dealer','irrelevant')),
  ADD COLUMN IF NOT EXISTS lead_use_case     text CHECK (lead_use_case IS NULL OR lead_use_case IN ('family','taxi')),
  ADD COLUMN IF NOT EXISTS lead_confidence   integer CHECK (lead_confidence IS NULL OR lead_confidence BETWEEN 0 AND 100),
  ADD COLUMN IF NOT EXISTS lead_reasons      text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS lead_needs_review boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS lead_version      text,
  ADD COLUMN IF NOT EXISTS rx300_mentioned   boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS rx300_context     boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_post_author    boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS ix_psc_leads ON public.public_social_comments(owner_id, lead_type, captured_at DESC)
  WHERE lead_type IN ('confirmed_rx300_buyer','potential_rx300_fit');
CREATE INDEX IF NOT EXISTS ix_psp_lead ON public.public_social_posts(owner_id, lead_type, captured_at DESC);
CREATE INDEX IF NOT EXISTS ix_psp_org ON public.public_social_posts(organization_id);

-- ─── 4) worker status per platform ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.social_platform_status (
  owner_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  platform             text NOT NULL CHECK (length(platform) BETWEEN 1 AND 64),
  enabled              boolean NOT NULL DEFAULT false,
  state                text NOT NULL,
  detail               text CHECK (detail IS NULL OR length(detail) <= 500),
  consecutive_failures integer NOT NULL DEFAULT 0,
  circuit_open_until   timestamptz,
  last_success_at      timestamptz,
  last_run_at          timestamptz,
  next_run_at          timestamptz,
  last_cycle           jsonb,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_id, platform)
);

-- ─── RLS (same pattern as the other social tables) ─────────────────────────
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['public_social_organizations','social_platform_status'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
    EXECUTE format('DROP POLICY IF EXISTS social_owner_select ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS social_no_client_insert ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS social_no_client_update ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS social_no_client_delete ON public.%I', t);
    EXECUTE format('CREATE POLICY social_owner_select ON public.%I FOR SELECT TO authenticated USING (owner_id = auth.uid())', t);
    EXECUTE format('CREATE POLICY social_no_client_insert ON public.%I FOR INSERT TO authenticated WITH CHECK (false)', t);
    EXECUTE format('CREATE POLICY social_no_client_update ON public.%I FOR UPDATE TO authenticated USING (false)', t);
    EXECUTE format('CREATE POLICY social_no_client_delete ON public.%I FOR DELETE TO authenticated USING (false)', t);
  END LOOP;
END $$;

-- ─── Retention: organizations expire too (365 days after last seen) ─────────
CREATE OR REPLACE FUNCTION public.purge_expired_social_data() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c int; p int; s int; o int;
BEGIN
  DELETE FROM public.public_social_comments WHERE expires_at < now();      GET DIAGNOSTICS c = ROW_COUNT;
  DELETE FROM public.public_social_posts    WHERE expires_at < now();      GET DIAGNOSTICS p = ROW_COUNT;
  DELETE FROM public.public_social_post_skips WHERE expires_at < now();    GET DIAGNOSTICS s = ROW_COUNT;
  DELETE FROM public.public_social_organizations WHERE expires_at < now(); GET DIAGNOSTICS o = ROW_COUNT;
  RETURN jsonb_build_object('comments', c, 'posts', p, 'skips', s, 'organizations', o);
END $$;
REVOKE ALL ON FUNCTION public.purge_expired_social_data() FROM PUBLIC, anon, authenticated;
