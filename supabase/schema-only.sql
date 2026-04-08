-- ============================================================
-- MonoCars — Schema Only (DDL + RLS + Vector Function)
-- Paste into Supabase SQL Editor → Run
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS brands (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name       text NOT NULL UNIQUE,
  country    text NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS car_types (
  id   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fuel_types (
  id   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS transmissions (
  id   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cars (
  id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  title               text    NOT NULL,
  brand_id            uuid    NOT NULL REFERENCES brands(id)        ON DELETE RESTRICT,
  model               text    NOT NULL,
  year                integer NOT NULL CHECK (year BETWEEN 1990 AND 2030),
  car_type_id         uuid    NOT NULL REFERENCES car_types(id)     ON DELETE RESTRICT,
  fuel_type_id        uuid    NOT NULL REFERENCES fuel_types(id)    ON DELETE RESTRICT,
  transmission_id     uuid    NOT NULL REFERENCES transmissions(id) ON DELETE RESTRICT,
  price_usd           integer NOT NULL CHECK (price_usd > 0),
  estimated_value_usd integer          CHECK (estimated_value_usd > 0),
  price_label         text    NOT NULL CHECK (price_label IN ('Good Deal','Fair','Overpriced')),
  mileage_km          integer NOT NULL DEFAULT 0 CHECK (mileage_km >= 0),
  color               text,
  engine_cc           integer          CHECK (engine_cc > 0),
  seats               integer NOT NULL DEFAULT 5 CHECK (seats BETWEEN 1 AND 15),
  location            text    NOT NULL DEFAULT 'Phnom Penh',
  description         text    NOT NULL,
  source              text    NOT NULL DEFAULT 'user' CHECK (source IN ('user','scraped')),
  is_featured         boolean NOT NULL DEFAULT false,
  is_available        boolean NOT NULL DEFAULT true,
  seller_name         text    NOT NULL,
  seller_phone        text    NOT NULL,
  seller_id           uuid             REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at          timestamptz DEFAULT now(),
  updated_at          timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS car_images (
  id            uuid    PRIMARY KEY DEFAULT uuid_generate_v4(),
  car_id        uuid    NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  url           text    NOT NULL,
  is_primary    boolean NOT NULL DEFAULT false,
  display_order integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS car_features (
  id      uuid    PRIMARY KEY DEFAULT uuid_generate_v4(),
  car_id  uuid    NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  feature text    NOT NULL,
  is_pro  boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS car_embeddings (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  car_id     uuid NOT NULL UNIQUE REFERENCES cars(id) ON DELETE CASCADE,
  embedding  vector(1536),
  content    text NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cars_brand       ON cars(brand_id);
CREATE INDEX IF NOT EXISTS idx_cars_type        ON cars(car_type_id);
CREATE INDEX IF NOT EXISTS idx_cars_fuel        ON cars(fuel_type_id);
CREATE INDEX IF NOT EXISTS idx_cars_year        ON cars(year);
CREATE INDEX IF NOT EXISTS idx_cars_price       ON cars(price_usd);
CREATE INDEX IF NOT EXISTS idx_cars_available   ON cars(is_available);
CREATE INDEX IF NOT EXISTS idx_cars_created     ON cars(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_car_images_car   ON car_images(car_id);
CREATE INDEX IF NOT EXISTS idx_car_features_car ON car_features(car_id);

CREATE INDEX IF NOT EXISTS idx_car_embeddings_vector
  ON car_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);

CREATE OR REPLACE FUNCTION match_cars(
  query_embedding  vector(1536),
  match_threshold  float  DEFAULT 0.3,
  match_count      int    DEFAULT 10,
  filter_car_ids   uuid[] DEFAULT NULL
)
RETURNS TABLE (car_id uuid, similarity float)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  SELECT ce.car_id, 1 - (ce.embedding <=> query_embedding) AS similarity
  FROM   car_embeddings ce
  WHERE  (filter_car_ids IS NULL OR ce.car_id = ANY(filter_car_ids))
    AND  1 - (ce.embedding <=> query_embedding) > match_threshold
  ORDER BY ce.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

ALTER TABLE brands         ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_types      ENABLE ROW LEVEL SECURITY;
ALTER TABLE fuel_types     ENABLE ROW LEVEL SECURITY;
ALTER TABLE transmissions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE cars           ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_images     ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_features   ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_brands"         ON brands         FOR SELECT USING (true);
CREATE POLICY "public_read_car_types"      ON car_types      FOR SELECT USING (true);
CREATE POLICY "public_read_fuel_types"     ON fuel_types     FOR SELECT USING (true);
CREATE POLICY "public_read_transmissions"  ON transmissions  FOR SELECT USING (true);
CREATE POLICY "public_read_cars"           ON cars           FOR SELECT USING (is_available = true);
CREATE POLICY "public_read_car_images"     ON car_images     FOR SELECT USING (true);
CREATE POLICY "public_read_car_features"   ON car_features   FOR SELECT USING (true);
CREATE POLICY "public_read_car_embeddings" ON car_embeddings FOR SELECT USING (true);

CREATE POLICY "service_all_brands"         ON brands         FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_types"      ON car_types      FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_fuel_types"     ON fuel_types     FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_transmissions"  ON transmissions  FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_cars"           ON cars           FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_images"     ON car_images     FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_features"   ON car_features   FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_embeddings" ON car_embeddings FOR ALL TO service_role USING (true);

CREATE POLICY "auth_insert_cars"     ON cars FOR INSERT TO authenticated WITH CHECK (seller_id = auth.uid());
CREATE POLICY "auth_update_own_cars" ON cars FOR UPDATE TO authenticated USING      (seller_id = auth.uid());
CREATE POLICY "auth_delete_own_cars" ON cars FOR DELETE TO authenticated USING      (seller_id = auth.uid());
