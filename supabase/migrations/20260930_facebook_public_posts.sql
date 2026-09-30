-- ============================================================================
-- Facebook PUBLIC posts + public comments (FacebookPublicPostsAdapter)
--
-- Only records whose public visibility was verified may exist in these tables
-- (CHECK visibility_status = 'public_verified'). Unverified/private results are
-- written to facebook_public_post_skips with the reason instead.
--
-- People are pseudonymous: no display names and no profile URLs are stored.
-- commenter_key / author_key = HMAC-SHA256(server secret, canonical profile URL),
-- with *_key_version for rotation. The secret never leaves the Python worker.
--
-- Access: anon has nothing. authenticated can SELECT only rows it owns
-- (owner_id = auth.uid()). Only the service role writes.
-- Retention: rows expire (expires_at) and are purged daily by pg_cron.
-- Safe to re-run.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

-- ─── Posts ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.facebook_public_posts (
  id                        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id                  uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  platform                  text NOT NULL DEFAULT 'facebook',
  source_post_id            text,
  source_post_url           text NOT NULL,
  canonical_post_url        text NOT NULL,
  author_key                text,            -- HMAC of the post author's canonical profile/page URL, or null
  author_key_version        text,
  post_text                 text CHECK (post_text IS NULL OR length(post_text) <= 20000),
  published_at_observed     timestamptz,
  visibility_status         text NOT NULL,
  visibility_evidence       text NOT NULL,
  search_query              text NOT NULL,
  captured_at               timestamptz NOT NULL,
  adapter_version           text NOT NULL,
  content_hash              text NOT NULL,
  comments_complete         boolean NOT NULL DEFAULT false,
  comments_collected_count  integer NOT NULL DEFAULT 0 CHECK (comments_collected_count >= 0),
  replies_collected_count   integer NOT NULL DEFAULT 0 CHECK (replies_collected_count >= 0),
  comment_expansion_rounds  integer NOT NULL DEFAULT 0 CHECK (comment_expansion_rounds >= 0),
  comments_incomplete_reason text,
  expires_at                timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fbpp_public_only CHECK (visibility_status = 'public_verified'),
  CONSTRAINT fbpp_key_version CHECK ((author_key IS NULL) = (author_key_version IS NULL)),
  CONSTRAINT fbpp_incomplete_reason CHECK (
    (comments_complete AND comments_incomplete_reason IS NULL) OR
    (NOT comments_complete AND comments_incomplete_reason IN (
      'configured_limit_reached','timeout','facebook_stopped_loading','login_wall','checkpoint','captcha',
      'rate_limit','post_unavailable','visibility_changed','not_attempted','unknown'))),
  CONSTRAINT fbpp_url_is_facebook CHECK (canonical_post_url ~ '^https://www\.facebook\.com/')
);

-- ─── Comments / replies ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.facebook_public_comments (
  id                     uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id               uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  post_id                uuid NOT NULL REFERENCES public.facebook_public_posts(id) ON DELETE CASCADE,
  source_comment_id      text,
  source_comment_url     text,               -- as shown by Facebook (tracking removed)
  canonical_comment_url  text,               -- post URL + comment_id / reply_comment_id
  comment_fingerprint    text NOT NULL,      -- deterministic identity (source id, or fallback hash)
  parent_comment_id      uuid REFERENCES public.facebook_public_comments(id) ON DELETE CASCADE,
  commenter_key          text,               -- HMAC of the commenter's canonical profile URL, or null
  commenter_key_version  text,
  comment_text           text NOT NULL CHECK (length(comment_text) BETWEEN 1 AND 10000),
  commented_at_observed  timestamptz,
  comment_type           text NOT NULL,
  visibility_status      text NOT NULL,
  captured_at            timestamptz NOT NULL,
  adapter_version        text NOT NULL,
  content_hash           text NOT NULL,
  expires_at             timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fbpc_type CHECK (comment_type IN ('comment','reply')),
  CONSTRAINT fbpc_reply_has_parent CHECK ((comment_type = 'reply') = (parent_comment_id IS NOT NULL)),
  CONSTRAINT fbpc_public_only CHECK (visibility_status = 'public_verified'),
  CONSTRAINT fbpc_key_version CHECK ((commenter_key IS NULL) = (commenter_key_version IS NULL))
);

-- ─── Skipped results (audit of what was NOT collected, and why) ─────────────
CREATE TABLE IF NOT EXISTS public.facebook_public_post_skips (
  id                  bigserial PRIMARY KEY,
  owner_id            uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  canonical_post_url  text,
  search_query        text NOT NULL,
  visibility_status   text NOT NULL CHECK (visibility_status IN ('unverified','private','restricted')),
  skip_reason         text NOT NULL,
  adapter_version     text NOT NULL,
  observed_at         timestamptz NOT NULL DEFAULT now(),
  expires_at          timestamptz NOT NULL DEFAULT (now() + interval '30 days')
);

-- ─── Uniqueness (no duplicates across crawls) ───────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uq_fbpp_owner_canonical_url ON public.facebook_public_posts(owner_id, canonical_post_url);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fbpp_owner_source_id     ON public.facebook_public_posts(owner_id, platform, source_post_id)
  WHERE source_post_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fbpc_post_source_id      ON public.facebook_public_comments(post_id, source_comment_id)
  WHERE source_comment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fbpc_owner_canonical_url ON public.facebook_public_comments(owner_id, canonical_comment_url)
  WHERE canonical_comment_url IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fbpc_post_fingerprint    ON public.facebook_public_comments(post_id, comment_fingerprint);

-- ─── Query indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_fbpp_owner          ON public.facebook_public_posts(owner_id);
CREATE INDEX IF NOT EXISTS ix_fbpp_source_post_id ON public.facebook_public_posts(source_post_id);
CREATE INDEX IF NOT EXISTS ix_fbpp_author_key     ON public.facebook_public_posts(author_key) WHERE author_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_fbpp_search_query   ON public.facebook_public_posts(owner_id, search_query);
CREATE INDEX IF NOT EXISTS ix_fbpp_published      ON public.facebook_public_posts(published_at_observed);
CREATE INDEX IF NOT EXISTS ix_fbpp_captured       ON public.facebook_public_posts(captured_at);
CREATE INDEX IF NOT EXISTS ix_fbpp_visibility     ON public.facebook_public_posts(visibility_status);
CREATE INDEX IF NOT EXISTS ix_fbpp_expires        ON public.facebook_public_posts(expires_at);
CREATE INDEX IF NOT EXISTS ix_fbpp_text_trgm      ON public.facebook_public_posts USING gin (post_text extensions.gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_fbpc_owner          ON public.facebook_public_comments(owner_id);
CREATE INDEX IF NOT EXISTS ix_fbpc_post           ON public.facebook_public_comments(post_id);
CREATE INDEX IF NOT EXISTS ix_fbpc_parent         ON public.facebook_public_comments(parent_comment_id) WHERE parent_comment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_fbpc_source_id      ON public.facebook_public_comments(source_comment_id);
CREATE INDEX IF NOT EXISTS ix_fbpc_commenter_key  ON public.facebook_public_comments(commenter_key) WHERE commenter_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_fbpc_commented_at   ON public.facebook_public_comments(commented_at_observed);
CREATE INDEX IF NOT EXISTS ix_fbpc_captured       ON public.facebook_public_comments(captured_at);
CREATE INDEX IF NOT EXISTS ix_fbpc_visibility     ON public.facebook_public_comments(visibility_status);
CREATE INDEX IF NOT EXISTS ix_fbpc_expires        ON public.facebook_public_comments(expires_at);
CREATE INDEX IF NOT EXISTS ix_fbpc_text_trgm      ON public.facebook_public_comments USING gin (comment_text extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_fbps_expires        ON public.facebook_public_post_skips(expires_at);

-- ─── A reply's parent must belong to the same post ──────────────────────────
CREATE OR REPLACE FUNCTION public.fbpc_parent_same_post()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.parent_comment_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM public.facebook_public_comments p
       WHERE p.id = NEW.parent_comment_id AND p.post_id = NEW.post_id AND p.owner_id = NEW.owner_id) THEN
    RAISE EXCEPTION 'reply parent must be a comment on the same post';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_fbpc_parent_same_post ON public.facebook_public_comments;
CREATE TRIGGER trg_fbpc_parent_same_post BEFORE INSERT OR UPDATE ON public.facebook_public_comments
  FOR EACH ROW EXECUTE FUNCTION public.fbpc_parent_same_post();

-- ─── RLS + minimal grants ───────────────────────────────────────────────────
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['facebook_public_posts','facebook_public_comments','facebook_public_post_skips'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
    EXECUTE format('GRANT ALL ON public.%I TO service_role', t);
    EXECUTE format('DROP POLICY IF EXISTS fb_owner_read ON public.%I', t);
    EXECUTE format('CREATE POLICY fb_owner_read ON public.%I FOR SELECT TO authenticated USING (owner_id = auth.uid())', t);
  END LOOP;
END $$;
REVOKE ALL ON SEQUENCE public.facebook_public_post_skips_id_seq FROM anon, authenticated;

-- ─── Retention ──────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.purge_expired_facebook_public_data()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c int; p int; s int;
BEGIN
  DELETE FROM public.facebook_public_comments WHERE expires_at < now();  GET DIAGNOSTICS c = ROW_COUNT;
  DELETE FROM public.facebook_public_posts    WHERE expires_at < now();  GET DIAGNOSTICS p = ROW_COUNT;
  DELETE FROM public.facebook_public_post_skips WHERE expires_at < now(); GET DIAGNOSTICS s = ROW_COUNT;
  RETURN jsonb_build_object('comments', c, 'posts', p, 'skips', s);
END $$;
REVOKE ALL ON FUNCTION public.purge_expired_facebook_public_data() FROM PUBLIC, anon, authenticated;
