-- 1) Evidence kinds: the focused listing screenshot (sent to the vision model) and the main photo.
ALTER TABLE public.listing_assets ADD COLUMN IF NOT EXISTS asset_kind text NOT NULL DEFAULT 'listing_container';
DO $$ BEGIN
  ALTER TABLE public.listing_assets ADD CONSTRAINT listing_assets_kind_check
    CHECK (asset_kind IN ('listing_container', 'primary_image'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_listing_assets_kind ON public.listing_assets(listing_id, asset_kind, captured_at DESC);

-- 2) Buyer-interest comments on a listing post.
--    Only comments that show buying interest are stored. No commenter identity (name, profile, avatar) is
--    ever stored, and phone numbers / emails / links inside the text are redacted before insert.
CREATE TABLE IF NOT EXISTS public.listing_comments (
  id                 uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  listing_id         uuid NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,
  crawl_run_id       uuid REFERENCES public.crawl_runs(id) ON DELETE SET NULL,
  comment_hash       text NOT NULL,             -- sha256 of the normalized original text (dedupe only)
  text_redacted      text NOT NULL CHECK (length(text_redacted) <= 1000),
  intent             text NOT NULL DEFAULT 'buyer_interest' CHECK (intent IN ('buyer_interest')),
  signals            jsonb NOT NULL DEFAULT '[]',
  language           text,
  classifier_version text NOT NULL,
  observed_at        timestamptz NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (listing_id, comment_hash)
);
CREATE INDEX IF NOT EXISTS idx_listing_comments_listing ON public.listing_comments(listing_id);

ALTER TABLE public.listing_comments ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.listing_comments FROM anon, authenticated;
GRANT SELECT ON public.listing_comments TO authenticated;
DROP POLICY IF EXISTS li_admin_read ON public.listing_comments;
CREATE POLICY li_admin_read ON public.listing_comments FOR SELECT TO authenticated USING (public.li_is_admin());
GRANT ALL ON public.listing_comments TO service_role;
