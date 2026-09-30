-- Buyer-intent classification results next to the ORIGINAL comment text (never replaced).
-- comment_text stays the original; comment_text_normalized is the matching copy (buyer-intent-khmer-latin-v1).

ALTER TABLE public.facebook_public_comments
  ADD COLUMN IF NOT EXISTS comment_text_normalized  text CHECK (comment_text_normalized IS NULL OR length(comment_text_normalized) <= 10000),
  ADD COLUMN IF NOT EXISTS buyer_intent             boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS buyer_intent_signals     jsonb   NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS matched_phrases          jsonb   NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS intent_classifier_version text;

CREATE INDEX IF NOT EXISTS ix_fbpc_buyer_intent ON public.facebook_public_comments(owner_id, captured_at DESC) WHERE buyer_intent;
CREATE INDEX IF NOT EXISTS ix_fbpc_text_norm_trgm ON public.facebook_public_comments
  USING gin (comment_text_normalized extensions.gin_trgm_ops);

ALTER TABLE public.listing_comments
  ADD COLUMN IF NOT EXISTS text_normalized  text,
  ADD COLUMN IF NOT EXISTS matched_phrases  jsonb NOT NULL DEFAULT '[]';
