-- Profile handling (owner's update, 2026-10-01):
-- Individuals: no names / usernames / profile URLs / profile screenshots; a pseudonymous key, the public post URL, the
-- exact comment permalink and a screenshot of the comment in its post context with name + avatar redacted.
-- Businesses: public page name, canonical page URL and a screenshot of publicly displayed business information only.
-- The three business_* fields must stay NULL unless account_type = 'business' (enforced here).

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['public_social_comments','facebook_public_comments'] LOOP
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS source_post_url text CHECK (source_post_url IS NULL OR length(source_post_url) <= 2000)', t);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS comment_context_screenshot text CHECK (comment_context_screenshot IS NULL OR length(comment_context_screenshot) BETWEEN 1 AND 500)', t);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS identity_redacted boolean NOT NULL DEFAULT true', t);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS account_type text NOT NULL DEFAULT ''unknown''', t);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS business_page_name text CHECK (business_page_name IS NULL OR length(business_page_name) BETWEEN 1 AND 300)', t);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS business_page_url text CHECK (business_page_url IS NULL OR length(business_page_url) <= 2000)', t);
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS business_page_screenshot text CHECK (business_page_screenshot IS NULL OR length(business_page_screenshot) BETWEEN 1 AND 500)', t);
    EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', t, t || '_account_type_chk');
    EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (account_type IN (''individual'',''business'',''unknown''))', t, t || '_account_type_chk');
    EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', t, t || '_business_only_chk');
    EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (account_type = ''business'' OR '
                   '(business_page_name IS NULL AND business_page_url IS NULL AND business_page_screenshot IS NULL))', t, t || '_business_only_chk');
    EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', t, t || '_redacted_chk');
    EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (identity_redacted OR account_type = ''business'')', t, t || '_redacted_chk');
  END LOOP;
END $$;

-- existing rows: the comment screenshot already is the redacted in-context shot
UPDATE public.public_social_comments   SET comment_context_screenshot = screenshot_path WHERE comment_context_screenshot IS NULL AND screenshot_path IS NOT NULL;
UPDATE public.facebook_public_comments SET comment_context_screenshot = screenshot_path WHERE comment_context_screenshot IS NULL AND screenshot_path IS NOT NULL;
UPDATE public.public_social_comments c SET source_post_url = p.canonical_post_url FROM public.public_social_posts p
  WHERE c.post_id = p.id AND c.source_post_url IS NULL;
UPDATE public.facebook_public_comments c SET source_post_url = p.canonical_post_url FROM public.facebook_public_posts p
  WHERE c.post_id = p.id AND c.source_post_url IS NULL;

-- organizations: business-relevant public information only
ALTER TABLE public.public_social_organizations
  ADD COLUMN IF NOT EXISTS category         text CHECK (category IS NULL OR length(category) <= 200),
  ADD COLUMN IF NOT EXISTS sales_location   text CHECK (sales_location IS NULL OR length(sales_location) <= 300),
  ADD COLUMN IF NOT EXISTS contact_channels jsonb NOT NULL DEFAULT '{}'::jsonb,   -- official channels shown on the page
  ADD COLUMN IF NOT EXISTS screenshot_path  text CHECK (screenshot_path IS NULL OR length(screenshot_path) BETWEEN 1 AND 500),
  ADD COLUMN IF NOT EXISTS captured_at      timestamptz;

COMMENT ON COLUMN public.public_social_comments.account_type IS
  'individual | business | unknown. Individuals: identity never stored. business_* fields only for clear organizations.';
