-- ============================================================================
-- Generalized public social data (TikTok now; Instagram/Reddit later; Facebook can move here later).
-- NOT destructive: the existing facebook_public_* tables and their data are untouched.
--
-- Privacy: no display names, usernames or profile URLs anywhere. People are HMAC keys
-- (HMAC-SHA256(secret, platform || ':' || identifier)), versioned, with scope 'profile' or 'comment_only'.
-- Access: anon nothing; authenticated SELECT own rows only; INSERT/UPDATE/DELETE denied to clients
-- (explicit separate policies); service role writes. Retention: expires_at + daily purge.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

-- Cross-platform repost groups: records are linked, never merged (every original URL kept).
CREATE TABLE IF NOT EXISTS public.public_social_duplicate_groups (
  id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  basis       text NOT NULL CHECK (basis IN ('canonical_url','text_hash','perceptual_hash','source_id')),
  similarity  numeric(5,4),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.public_social_posts (
  id                         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id                   uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  platform                   text NOT NULL CHECK (platform IN ('facebook','instagram','tiktok','reddit')),
  source_content_type        text NOT NULL CHECK (source_content_type IN
                               ('facebook_post','instagram_post','instagram_reel','tiktok_video','reddit_post')),
  source_post_id             text,
  source_post_url            text NOT NULL,
  canonical_post_url         text NOT NULL,
  document_title             text,
  post_title                 text,
  post_text                  text CHECK (post_text IS NULL OR length(post_text) <= 20000),
  hashtags                   text[] NOT NULL DEFAULT '{}',
  subreddit                  text,
  published_text_displayed   text,
  published_at_observed      timestamptz,
  engagement                 jsonb NOT NULL DEFAULT '{}',     -- displayed counts only (likes/comments/shares)
  visibility_status          text NOT NULL CHECK (visibility_status = 'public_verified'),
  visibility_evidence        text NOT NULL,
  search_query               text NOT NULL,
  search_url                 text,                            -- the exact search-result URL that found it
  captured_at                timestamptz NOT NULL,
  adapter_version            text NOT NULL,
  content_hash               text NOT NULL,
  completeness_status        text NOT NULL DEFAULT 'comments_unavailable' CHECK (completeness_status IN
                               ('complete','partial_limit','partial_timeout','login_required','access_blocked','comments_unavailable')),
  comments_complete          boolean GENERATED ALWAYS AS (completeness_status = 'complete') STORED,
  comments_collected_count   integer NOT NULL DEFAULT 0 CHECK (comments_collected_count >= 0),
  replies_collected_count    integer NOT NULL DEFAULT 0 CHECK (replies_collected_count >= 0),
  comment_expansion_rounds   integer NOT NULL DEFAULT 0,
  rejected_comment_count     integer NOT NULL DEFAULT 0,      -- non-buyer comments not stored (buyers-only policy)
  rejection_reasons          jsonb NOT NULL DEFAULT '{}',
  screenshot_path            text,                            -- private bucket listing-evidence/social/...
  perceptual_hash            text,
  duplicate_group_id         uuid REFERENCES public.public_social_duplicate_groups(id) ON DELETE SET NULL,
  expires_at                 timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.public_social_comments (
  id                     uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id               uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  platform               text NOT NULL CHECK (platform IN ('facebook','instagram','tiktok','reddit')),
  post_id                uuid NOT NULL REFERENCES public.public_social_posts(id) ON DELETE CASCADE,
  source_comment_id      text,
  source_comment_url     text,
  canonical_comment_url  text,
  comment_url_available  boolean NOT NULL DEFAULT false,      -- never invent a URL
  comment_fingerprint    text NOT NULL,
  parent_comment_id      uuid REFERENCES public.public_social_comments(id) ON DELETE CASCADE,
  comment_type           text NOT NULL CHECK (comment_type IN ('comment','reply')),
  commenter_key          text,
  commenter_key_version  text,
  commenter_key_scope    text NOT NULL DEFAULT 'comment_only' CHECK (commenter_key_scope IN ('profile','comment_only')),
  comment_text           text NOT NULL CHECK (length(comment_text) BETWEEN 1 AND 10000),   -- original (contacts redacted)
  comment_text_normalized text,
  displayed_timestamp    text,
  commented_at_observed  timestamptz,
  visibility_status      text NOT NULL CHECK (visibility_status = 'public_verified'),
  captured_at            timestamptz NOT NULL,
  adapter_version        text NOT NULL,
  content_hash           text NOT NULL,
  buyer_intent_score     integer NOT NULL DEFAULT 0 CHECK (buyer_intent_score BETWEEN 0 AND 100),
  buyer_intent_label     text NOT NULL DEFAULT 'not_buyer_intent' CHECK (buyer_intent_label IN
                           ('strong_buyer_intent','possible_buyer_intent','not_buyer_intent')),
  intent_type            text,
  detected_language      text,
  matched_signals        jsonb NOT NULL DEFAULT '[]',
  matched_phrases        jsonb NOT NULL DEFAULT '[]',
  negative_signals       jsonb NOT NULL DEFAULT '[]',
  spam_score             integer NOT NULL DEFAULT 0 CHECK (spam_score BETWEEN 0 AND 100),
  intent_reason          text,
  needs_human_review     boolean NOT NULL DEFAULT false,
  scorer_version         text,
  screenshot_path        text,
  expires_at             timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  created_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT psc_reply_has_parent CHECK ((comment_type = 'reply') = (parent_comment_id IS NOT NULL)),
  CONSTRAINT psc_key_version CHECK ((commenter_key IS NULL) = (commenter_key_version IS NULL)),
  CONSTRAINT psc_url_flag CHECK (comment_url_available = (source_comment_url IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS public.public_social_post_skips (
  id                 bigserial PRIMARY KEY,
  owner_id           uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  platform           text NOT NULL CHECK (platform IN ('facebook','instagram','tiktok','reddit')),
  canonical_post_url text,
  search_query       text NOT NULL,
  visibility_status  text NOT NULL CHECK (visibility_status IN ('unverified','private','restricted')),
  skip_reason        text NOT NULL,
  observed_at        timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL DEFAULT (now() + interval '30 days')
);

-- ─── Uniqueness / idempotency ───────────────────────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uq_psp_owner_platform_url ON public.public_social_posts(owner_id, platform, canonical_post_url);
CREATE UNIQUE INDEX IF NOT EXISTS uq_psp_owner_platform_src ON public.public_social_posts(owner_id, platform, source_post_id) WHERE source_post_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_psc_post_fingerprint   ON public.public_social_comments(post_id, comment_fingerprint);
CREATE UNIQUE INDEX IF NOT EXISTS uq_psc_post_src           ON public.public_social_comments(post_id, platform, source_comment_id) WHERE source_comment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_psc_owner_comment_url  ON public.public_social_comments(owner_id, canonical_comment_url) WHERE canonical_comment_url IS NOT NULL;

-- ─── Query indexes (why) ────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_psp_owner_platform_captured ON public.public_social_posts(owner_id, platform, captured_at DESC);   -- dashboard lists per platform, newest first
CREATE INDEX IF NOT EXISTS ix_psp_source_id      ON public.public_social_posts(platform, source_post_id);                       -- look up by platform id
CREATE INDEX IF NOT EXISTS ix_psp_search_query   ON public.public_social_posts(owner_id, search_query);                         -- "what did this phrase find?"
CREATE INDEX IF NOT EXISTS ix_psp_published      ON public.public_social_posts(published_at_observed);                          -- date filters
CREATE INDEX IF NOT EXISTS ix_psp_hashtags       ON public.public_social_posts USING gin (hashtags);                            -- hashtag containment (@>)
CREATE INDEX IF NOT EXISTS ix_psp_subreddit      ON public.public_social_posts(subreddit) WHERE subreddit IS NOT NULL;          -- Reddit community filter
CREATE INDEX IF NOT EXISTS ix_psp_text_trgm      ON public.public_social_posts USING gin (post_text extensions.gin_trgm_ops);   -- ILIKE text search incl. Khmer
CREATE INDEX IF NOT EXISTS ix_psp_dup_group      ON public.public_social_posts(duplicate_group_id) WHERE duplicate_group_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_psp_content_hash   ON public.public_social_posts(owner_id, content_hash);                         -- cross-platform repost detection
CREATE INDEX IF NOT EXISTS ix_psp_expires        ON public.public_social_posts(expires_at);                                     -- retention purge
CREATE INDEX IF NOT EXISTS ix_psc_post           ON public.public_social_comments(post_id);                                     -- thread for a post
CREATE INDEX IF NOT EXISTS ix_psc_parent         ON public.public_social_comments(parent_comment_id) WHERE parent_comment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_psc_buyers         ON public.public_social_comments(owner_id, platform, buyer_intent_score DESC)
                                                   WHERE buyer_intent_label <> 'not_buyer_intent';                              -- buyer lists by min score
CREATE INDEX IF NOT EXISTS ix_psc_label          ON public.public_social_comments(owner_id, buyer_intent_label);                -- filter by category
CREATE INDEX IF NOT EXISTS ix_psc_commenter_key  ON public.public_social_comments(commenter_key) WHERE commenter_key IS NOT NULL; -- same (pseudonymous) person
CREATE INDEX IF NOT EXISTS ix_psc_source_id      ON public.public_social_comments(platform, source_comment_id);
CREATE INDEX IF NOT EXISTS ix_psc_commented_at   ON public.public_social_comments(commented_at_observed);
CREATE INDEX IF NOT EXISTS ix_psc_captured       ON public.public_social_comments(captured_at);
CREATE INDEX IF NOT EXISTS ix_psc_text_trgm      ON public.public_social_comments USING gin (comment_text extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_psc_expires        ON public.public_social_comments(expires_at);
CREATE INDEX IF NOT EXISTS ix_pss_expires        ON public.public_social_post_skips(expires_at);

-- A reply's parent must be on the same post
CREATE OR REPLACE FUNCTION public.psc_parent_same_post() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.parent_comment_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM public.public_social_comments p WHERE p.id = NEW.parent_comment_id AND p.post_id = NEW.post_id) THEN
    RAISE EXCEPTION 'reply parent must be a comment on the same post';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_psc_parent_same_post ON public.public_social_comments;
CREATE TRIGGER trg_psc_parent_same_post BEFORE INSERT OR UPDATE ON public.public_social_comments
  FOR EACH ROW EXECUTE FUNCTION public.psc_parent_same_post();

-- ─── RLS: separate policies per operation ───────────────────────────────────
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['public_social_posts','public_social_comments','public_social_post_skips','public_social_duplicate_groups'] LOOP
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
REVOKE ALL ON SEQUENCE public.public_social_post_skips_id_seq FROM anon, authenticated;

-- ─── Retention ──────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_expired_social_data() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c int; p int; s int;
BEGIN
  DELETE FROM public.public_social_comments WHERE expires_at < now();   GET DIAGNOSTICS c = ROW_COUNT;
  DELETE FROM public.public_social_posts    WHERE expires_at < now();   GET DIAGNOSTICS p = ROW_COUNT;
  DELETE FROM public.public_social_post_skips WHERE expires_at < now(); GET DIAGNOSTICS s = ROW_COUNT;
  RETURN jsonb_build_object('comments', c, 'posts', p, 'skips', s);
END $$;
REVOKE ALL ON FUNCTION public.purge_expired_social_data() FROM PUBLIC, anon, authenticated;
SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname = 'purge-social-data';
SELECT cron.schedule('purge-social-data', '27 3 * * *', $$SELECT public.purge_expired_social_data()$$);
