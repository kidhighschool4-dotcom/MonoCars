-- Screenshot evidence for Facebook public posts and buyer-intent comments.
-- Paths point into the PRIVATE Storage bucket `listing-evidence` (prefix social/facebook/YYYY/MM/...), same as
-- public_social_posts.screenshot_path. Commenter/author names and avatars are hidden before capture.

ALTER TABLE public.facebook_public_posts ADD COLUMN IF NOT EXISTS screenshot_path text;
ALTER TABLE public.facebook_public_comments ADD COLUMN IF NOT EXISTS screenshot_path text;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fbpp_screenshot_path_len') THEN
    ALTER TABLE public.facebook_public_posts
      ADD CONSTRAINT fbpp_screenshot_path_len CHECK (screenshot_path IS NULL OR length(screenshot_path) BETWEEN 1 AND 500);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fbpc_screenshot_path_len') THEN
    ALTER TABLE public.facebook_public_comments
      ADD CONSTRAINT fbpc_screenshot_path_len CHECK (screenshot_path IS NULL OR length(screenshot_path) BETWEEN 1 AND 500);
  END IF;
END $$;

COMMENT ON COLUMN public.facebook_public_posts.screenshot_path IS
  'Private listing-evidence object path (social/facebook/...) of the post region screenshot; names/avatars hidden.';
COMMENT ON COLUMN public.facebook_public_comments.screenshot_path IS
  'Private listing-evidence object path (social/facebook/...) of a buyer-intent comment screenshot; names/avatars hidden.';
