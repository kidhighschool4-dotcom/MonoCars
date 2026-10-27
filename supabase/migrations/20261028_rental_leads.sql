-- Rental-seeker leads (campaign switched from Lexus RX300 buyers to people looking for a place to rent in Phnom Penh).
-- Old RX300 lead types stay valid so stored leads keep loading. The post rating (0–100 %) lives in posts.lead->post_score.

ALTER TABLE public.public_social_posts DROP CONSTRAINT IF EXISTS public_social_posts_lead_type_check;
ALTER TABLE public.public_social_posts ADD CONSTRAINT public_social_posts_lead_type_check CHECK (lead_type IS NULL OR lead_type IN
  ('confirmed_rx300_buyer','potential_rx300_fit','rental_seeker','potential_rental_seeker','seller_or_dealer','irrelevant'));

ALTER TABLE public.public_social_comments DROP CONSTRAINT IF EXISTS public_social_comments_lead_type_check;
ALTER TABLE public.public_social_comments ADD CONSTRAINT public_social_comments_lead_type_check CHECK (lead_type IS NULL OR lead_type IN
  ('confirmed_rx300_buyer','potential_rx300_fit','rental_seeker','potential_rental_seeker','seller_or_dealer','irrelevant'));

-- use case = what kind of place (rentals) or what the car is for (RX300)
ALTER TABLE public.public_social_comments DROP CONSTRAINT IF EXISTS public_social_comments_lead_use_case_check;
ALTER TABLE public.public_social_comments ADD CONSTRAINT public_social_comments_lead_use_case_check CHECK (lead_use_case IS NULL OR lead_use_case IN
  ('family','taxi','house','apartment','room','commercial'));

CREATE INDEX IF NOT EXISTS ix_psc_rental_leads ON public.public_social_comments(owner_id, lead_type, captured_at DESC)
  WHERE lead_type IN ('rental_seeker','potential_rental_seeker');
CREATE INDEX IF NOT EXISTS ix_psp_post_score ON public.public_social_posts(owner_id, ((lead->>'post_score')::int) DESC NULLS LAST);
