-- ============================================================================
-- Customer / seller accounts
--   profiles.role: 'customer' (buys, messages sellers) or 'seller' (can list cars).
--   Chosen at sign-up (raw_user_meta_data.account_type) and switchable by the user.
--   Only these two values are possible, so a user can never grant themselves admin.
--   Admin (internal reviewer of the listing-intelligence pipeline) is app_metadata.role='admin',
--   which only the service role can set.
-- Safe to re-run.
-- ============================================================================

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'customer';

DO $$ BEGIN
  ALTER TABLE public.profiles ADD CONSTRAINT profiles_role_check CHECK (role IN ('customer','seller'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Existing listing owners are sellers
UPDATE public.profiles p SET role = 'seller'
WHERE role = 'customer' AND EXISTS (SELECT 1 FROM public.cars c WHERE c.seller_id = p.id);

-- Sign-up: take the account type the user picked (anything else falls back to customer)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  picked text := NEW.raw_user_meta_data->>'account_type';
BEGIN
  INSERT INTO public.profiles (id, full_name, role)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'full_name',
    CASE WHEN picked IN ('customer','seller') THEN picked ELSE 'customer' END
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Users may only edit their own profile, and only keep a valid role
DROP POLICY IF EXISTS "owner_update_profile" ON public.profiles;
CREATE POLICY "owner_update_profile" ON public.profiles
  FOR UPDATE TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid() AND role IN ('customer','seller'));

-- Helper: is the current user a seller?
CREATE OR REPLACE FUNCTION public.is_seller()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'seller')
$$;

-- Only sellers can create listings (defence in depth; the API checks too)
DROP POLICY IF EXISTS "auth_insert_cars" ON public.cars;
CREATE POLICY "auth_insert_cars" ON public.cars
  FOR INSERT TO authenticated
  WITH CHECK (seller_id = auth.uid() AND public.is_seller());

-- Sellers see their own listings even when unavailable (for the seller dashboard)
DROP POLICY IF EXISTS "seller_read_own_cars" ON public.cars;
CREATE POLICY "seller_read_own_cars" ON public.cars
  FOR SELECT TO authenticated
  USING (seller_id = auth.uid());
