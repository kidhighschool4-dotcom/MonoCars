-- ============================================================
-- MonoCars Cambodia — Complete Database Schema + Seed Data
-- Paste this entire file into the Supabase SQL Editor and run.
-- ============================================================

-- ─── EXTENSIONS ────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── LOOKUP TABLES ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS brands (
  id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name      text NOT NULL UNIQUE,
  country   text NOT NULL,
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

-- ─── CORE TABLES ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cars (
  id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  title               text        NOT NULL,
  brand_id            uuid        NOT NULL REFERENCES brands(id)       ON DELETE RESTRICT,
  model               text        NOT NULL,
  year                integer     NOT NULL CHECK (year BETWEEN 1990 AND 2030),
  car_type_id         uuid        NOT NULL REFERENCES car_types(id)    ON DELETE RESTRICT,
  fuel_type_id        uuid        NOT NULL REFERENCES fuel_types(id)   ON DELETE RESTRICT,
  transmission_id     uuid        NOT NULL REFERENCES transmissions(id) ON DELETE RESTRICT,
  price_usd           integer     NOT NULL CHECK (price_usd > 0),
  estimated_value_usd integer              CHECK (estimated_value_usd > 0),
  price_label         text        NOT NULL CHECK (price_label IN ('Good Deal','Fair','Overpriced')),
  mileage_km          integer     NOT NULL DEFAULT 0 CHECK (mileage_km >= 0),
  color               text,
  engine_cc           integer              CHECK (engine_cc > 0),
  seats               integer     NOT NULL DEFAULT 5 CHECK (seats BETWEEN 1 AND 15),
  location            text        NOT NULL DEFAULT 'Phnom Penh',
  description         text        NOT NULL,
  source              text        NOT NULL DEFAULT 'user' CHECK (source IN ('user','scraped')),
  is_featured         boolean     NOT NULL DEFAULT false,
  is_available        boolean     NOT NULL DEFAULT true,
  seller_name         text        NOT NULL,
  seller_phone        text        NOT NULL,
  seller_id           uuid                 REFERENCES auth.users(id) ON DELETE SET NULL,
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
  is_pro  boolean NOT NULL DEFAULT true   -- true = pro, false = con
);

CREATE TABLE IF NOT EXISTS car_embeddings (
  id        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  car_id    uuid NOT NULL UNIQUE REFERENCES cars(id) ON DELETE CASCADE,
  embedding vector(1536),
  content   text NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- ─── INDEXES ───────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_cars_brand       ON cars(brand_id);
CREATE INDEX IF NOT EXISTS idx_cars_type        ON cars(car_type_id);
CREATE INDEX IF NOT EXISTS idx_cars_fuel        ON cars(fuel_type_id);
CREATE INDEX IF NOT EXISTS idx_cars_year        ON cars(year);
CREATE INDEX IF NOT EXISTS idx_cars_price       ON cars(price_usd);
CREATE INDEX IF NOT EXISTS idx_cars_available   ON cars(is_available);
CREATE INDEX IF NOT EXISTS idx_cars_featured    ON cars(is_featured);
CREATE INDEX IF NOT EXISTS idx_cars_created     ON cars(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_car_images_car   ON car_images(car_id);
CREATE INDEX IF NOT EXISTS idx_car_features_car ON car_features(car_id);

-- Approximate nearest-neighbour vector index (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_car_embeddings_vector
  ON car_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);

-- ─── VECTOR SEARCH FUNCTION ────────────────────────────────

CREATE OR REPLACE FUNCTION match_cars(
  query_embedding  vector(1536),
  match_threshold  float   DEFAULT 0.3,
  match_count      int     DEFAULT 10,
  filter_car_ids   uuid[]  DEFAULT NULL
)
RETURNS TABLE (car_id uuid, similarity float)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
  RETURN QUERY
  SELECT
    ce.car_id,
    1 - (ce.embedding <=> query_embedding) AS similarity
  FROM car_embeddings ce
  WHERE
    (filter_car_ids IS NULL OR ce.car_id = ANY(filter_car_ids))
    AND 1 - (ce.embedding <=> query_embedding) > match_threshold
  ORDER BY ce.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ─── ROW LEVEL SECURITY ────────────────────────────────────

ALTER TABLE brands         ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_types      ENABLE ROW LEVEL SECURITY;
ALTER TABLE fuel_types     ENABLE ROW LEVEL SECURITY;
ALTER TABLE transmissions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE cars           ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_images     ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_features   ENABLE ROW LEVEL SECURITY;
ALTER TABLE car_embeddings ENABLE ROW LEVEL SECURITY;

-- Public read
CREATE POLICY "public_read_brands"         ON brands         FOR SELECT USING (true);
CREATE POLICY "public_read_car_types"      ON car_types      FOR SELECT USING (true);
CREATE POLICY "public_read_fuel_types"     ON fuel_types     FOR SELECT USING (true);
CREATE POLICY "public_read_transmissions"  ON transmissions  FOR SELECT USING (true);
CREATE POLICY "public_read_cars"           ON cars           FOR SELECT USING (is_available = true);
CREATE POLICY "public_read_car_images"     ON car_images     FOR SELECT USING (true);
CREATE POLICY "public_read_car_features"   ON car_features   FOR SELECT USING (true);
CREATE POLICY "public_read_car_embeddings" ON car_embeddings FOR SELECT USING (true);

-- Service role full access (API routes, seeding)
CREATE POLICY "service_all_brands"         ON brands         FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_types"      ON car_types      FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_fuel_types"     ON fuel_types     FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_transmissions"  ON transmissions  FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_cars"           ON cars           FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_images"     ON car_images     FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_features"   ON car_features   FOR ALL TO service_role USING (true);
CREATE POLICY "service_all_car_embeddings" ON car_embeddings FOR ALL TO service_role USING (true);

-- Authenticated users manage their own listings
CREATE POLICY "auth_insert_cars"     ON cars FOR INSERT TO authenticated WITH CHECK (seller_id = auth.uid());
CREATE POLICY "auth_update_own_cars" ON cars FOR UPDATE TO authenticated USING      (seller_id = auth.uid());
CREATE POLICY "auth_delete_own_cars" ON cars FOR DELETE TO authenticated USING      (seller_id = auth.uid());

-- ─── SEED: LOOKUP DATA ─────────────────────────────────────

INSERT INTO brands (name, country) VALUES
  ('Toyota',        'Japan'),
  ('Honda',         'Japan'),
  ('Lexus',         'Japan'),
  ('BMW',           'Germany'),
  ('Mercedes-Benz', 'Germany'),
  ('Hyundai',       'South Korea'),
  ('Kia',           'South Korea'),
  ('Ford',          'United States'),
  ('Mitsubishi',    'Japan'),
  ('Nissan',        'Japan'),
  ('Mazda',         'Japan'),
  ('Audi',          'Germany'),
  ('Isuzu',         'Japan'),
  ('Land Rover',    'United Kingdom'),
  ('Porsche',       'Germany')
ON CONFLICT (name) DO NOTHING;

INSERT INTO car_types (name) VALUES
  ('Sedan'), ('SUV'), ('Pickup'), ('Hatchback'), ('Van'), ('Coupe'), ('Crossover')
ON CONFLICT (name) DO NOTHING;

INSERT INTO fuel_types (name) VALUES
  ('Gasoline'), ('Diesel'), ('Hybrid'), ('Plug-in Hybrid'), ('Electric')
ON CONFLICT (name) DO NOTHING;

INSERT INTO transmissions (name) VALUES
  ('Automatic'), ('Manual'), ('CVT'), ('Semi-Automatic')
ON CONFLICT (name) DO NOTHING;

-- ─── SEED: CARS ────────────────────────────────────────────
-- 20 real Cambodia-market listings

DO $$
DECLARE
  cid uuid;

  -- Brand IDs
  b_toyota      uuid; b_honda      uuid; b_lexus      uuid;
  b_bmw         uuid; b_mercedes   uuid; b_hyundai    uuid;
  b_kia         uuid; b_ford       uuid; b_mitsubishi uuid;
  b_nissan      uuid; b_mazda      uuid; b_audi       uuid;
  b_isuzu       uuid;

  -- Type IDs
  t_sedan  uuid; t_suv   uuid; t_pickup uuid;
  t_hatch  uuid; t_van   uuid; t_coupe  uuid; t_cross uuid;

  -- Fuel IDs
  f_gasoline uuid; f_diesel uuid; f_hybrid uuid;
  f_phev     uuid; f_ev    uuid;

  -- Transmission IDs
  tr_auto uuid; tr_manual uuid; tr_cvt uuid;

BEGIN
  -- Load brand IDs
  SELECT id INTO b_toyota      FROM brands WHERE name='Toyota';
  SELECT id INTO b_honda       FROM brands WHERE name='Honda';
  SELECT id INTO b_lexus       FROM brands WHERE name='Lexus';
  SELECT id INTO b_bmw         FROM brands WHERE name='BMW';
  SELECT id INTO b_mercedes    FROM brands WHERE name='Mercedes-Benz';
  SELECT id INTO b_hyundai     FROM brands WHERE name='Hyundai';
  SELECT id INTO b_kia         FROM brands WHERE name='Kia';
  SELECT id INTO b_ford        FROM brands WHERE name='Ford';
  SELECT id INTO b_mitsubishi  FROM brands WHERE name='Mitsubishi';
  SELECT id INTO b_nissan      FROM brands WHERE name='Nissan';
  SELECT id INTO b_mazda       FROM brands WHERE name='Mazda';
  SELECT id INTO b_audi        FROM brands WHERE name='Audi';
  SELECT id INTO b_isuzu       FROM brands WHERE name='Isuzu';

  -- Load type IDs
  SELECT id INTO t_sedan  FROM car_types WHERE name='Sedan';
  SELECT id INTO t_suv    FROM car_types WHERE name='SUV';
  SELECT id INTO t_pickup FROM car_types WHERE name='Pickup';
  SELECT id INTO t_hatch  FROM car_types WHERE name='Hatchback';
  SELECT id INTO t_van    FROM car_types WHERE name='Van';
  SELECT id INTO t_coupe  FROM car_types WHERE name='Coupe';
  SELECT id INTO t_cross  FROM car_types WHERE name='Crossover';

  -- Load fuel IDs
  SELECT id INTO f_gasoline FROM fuel_types WHERE name='Gasoline';
  SELECT id INTO f_diesel   FROM fuel_types WHERE name='Diesel';
  SELECT id INTO f_hybrid   FROM fuel_types WHERE name='Hybrid';
  SELECT id INTO f_phev     FROM fuel_types WHERE name='Plug-in Hybrid';
  SELECT id INTO f_ev       FROM fuel_types WHERE name='Electric';

  -- Load transmission IDs
  SELECT id INTO tr_auto   FROM transmissions WHERE name='Automatic';
  SELECT id INTO tr_manual FROM transmissions WHERE name='Manual';
  SELECT id INTO tr_cvt    FROM transmissions WHERE name='CVT';

  -- ── 1. Toyota Land Cruiser 300 GR Sport ─────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Toyota Land Cruiser 300 GR Sport',
    b_toyota, 'Land Cruiser 300', 2022, t_suv, f_gasoline, tr_auto,
    95000, 108000, 'Good Deal', 8200, 'Pearl White', 3500, 7,
    'Phnom Penh',
    'Flagship Toyota Land Cruiser 300 GR Sport imported from Japan, full Toyota warranty remaining. Twin-turbocharged V6 engine delivers effortless power on any terrain. Panoramic moonroof, 14-speaker JBL audio, Toyota Safety Sense 3.0. The undisputed king of Cambodia roads.',
    'scraped', true, 'Sopheak Mao', '+855 12 888 001')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800', false, 1),
    (cid, 'https://images.unsplash.com/photo-1551830820-41e5f6cfc2a1?w=800', false, 2);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Twin-turbo V6 with massive torque', true),
    (cid, 'Full Toyota warranty still active', true),
    (cid, 'Advanced Multi-Terrain Select 4WD', true),
    (cid, 'Panoramic moonroof + JBL audio', true),
    (cid, 'High fuel consumption in city', false),
    (cid, 'Large size — tight for city parking', false);

  -- ── 2. Toyota Fortuner 2.4G 4WD ─────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2021 Toyota Fortuner 2.4G 4WD',
    b_toyota, 'Fortuner', 2021, t_suv, f_diesel, tr_auto,
    38500, 40000, 'Fair', 32000, 'Attitude Black', 2400, 7,
    'Phnom Penh',
    'Well-maintained Toyota Fortuner 2.4G in excellent condition. Single owner, always serviced at Toyota dealer. Diesel engine is perfect for long-distance trips to Siem Reap or Sihanoukville. 7 seats, leather interior, parking sensors, reverse camera.',
    'user', true, 'Rith Vanna', '+855 17 456 002')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1551830820-41e5f6cfc2a1?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Fuel-efficient 2.4L diesel engine', true),
    (cid, '7-seat capacity with leather interior', true),
    (cid, 'Full Toyota dealer service history', true),
    (cid, 'Excellent resale value', true),
    (cid, 'Older entertainment system', false),
    (cid, 'Diesel harder to find in some provinces', false);

  -- ── 3. Toyota Camry 2.5 Hybrid ──────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2023 Toyota Camry 2.5 Hybrid',
    b_toyota, 'Camry', 2023, t_sedan, f_hybrid, tr_cvt,
    36000, 43000, 'Good Deal', 5500, 'Midnight Blue', 2500, 5,
    'Phnom Penh',
    'Near-new Toyota Camry Hybrid with only 5,500km. Extremely fuel efficient — averaging 5.5L/100km in city traffic. Perfect executive sedan for business use. Full Toyota warranty, 12.3" touchscreen, wireless Apple CarPlay and Android Auto, Toyota Safety Sense.',
    'user', false, 'Bopha Chan', '+855 93 123 003')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1542362567-b07e54358753?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Excellent fuel economy — 5.5L/100km', true),
    (cid, 'Almost new, full Toyota warranty', true),
    (cid, 'Wireless Apple CarPlay + Android Auto', true),
    (cid, 'Quiet and smooth ride', true),
    (cid, 'Premium fuel required', false),
    (cid, 'Higher price than petrol equivalent', false);

  -- ── 4. Toyota Hilux Revo 2.4G 4x4 ──────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2020 Toyota Hilux Revo 2.4G 4x4',
    b_toyota, 'Hilux Revo', 2020, t_pickup, f_diesel, tr_auto,
    26500, 27500, 'Fair', 56000, 'Silver Metallic', 2400, 5,
    'Siem Reap',
    'Reliable Toyota Hilux Revo 2.4G with 4x4 capability. Used for business deliveries — all serviced. Dual-cab with work liner, tow bar, snorkel fitted. Great for travel between provinces. Honest seller, no hidden issues.',
    'user', false, 'Dara Keo', '+855 17 234 004')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', true, 0),
    (cid, 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '4x4 capability for off-road', true),
    (cid, 'Snorkel and tow bar fitted', true),
    (cid, 'Durable diesel engine', true),
    (cid, 'Dual-cab with work liner', true),
    (cid, 'Higher mileage — 56,000km', false),
    (cid, 'Ride rougher than SUV for passengers', false);

  -- ── 5. Honda CR-V 1.5 Turbo AWD ─────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Honda CR-V 1.5 Turbo AWD',
    b_honda, 'CR-V', 2022, t_suv, f_gasoline, tr_cvt,
    29500, 34000, 'Good Deal', 18500, 'Lunar Silver', 1500, 5,
    'Phnom Penh',
    'Stylish Honda CR-V 1.5 Turbo with AWD. Lady owner, garage kept, non-smoker. Turbocharged engine feels punchy yet returns excellent fuel economy. Honda Sensing suite (collision mitigation, lane keep, adaptive cruise). Perfect family SUV for Phnom Penh.',
    'user', false, 'Srey Leak', '+855 12 567 005')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Honda Sensing safety suite', true),
    (cid, 'AWD for rainy season confidence', true),
    (cid, 'Excellent fuel economy for turbo', true),
    (cid, 'Lady owner — immaculate condition', true),
    (cid, 'CVT can feel sluggish in sport mode', false),
    (cid, 'Smaller boot than competitors', false);

  -- ── 6. Honda Accord 1.5 Turbo ────────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2021 Honda Accord 1.5 Turbo',
    b_honda, 'Accord', 2021, t_sedan, f_gasoline, tr_cvt,
    27000, 28500, 'Fair', 29000, 'Platinum White Pearl', 1500, 5,
    'Phnom Penh',
    'Elegant Honda Accord imported from Singapore. Turbocharged 1.5L produces 192hp — surprisingly quick. 10.2" touchscreen, wireless phone charging, heated seats, sunroof, Honda Sensing. Driven by expat returning home. Complete service records.',
    'user', false, 'Michael Chen', '+855 96 888 006')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '192hp turbo — fun to drive', true),
    (cid, 'Wireless charging + heated seats', true),
    (cid, 'Full Singapore service records', true),
    (cid, 'Spacious rear cabin', true),
    (cid, 'Higher maintenance than Japanese average', false),
    (cid, 'Small turbo engine for highway cruising', false);

  -- ── 7. Lexus RX 350h F-Sport ─────────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2023 Lexus RX 350h F-Sport',
    b_lexus, 'RX 350h', 2023, t_suv, f_hybrid, tr_auto,
    72000, 75000, 'Fair', 6500, 'Sonic Titanium', 2500, 5,
    'Phnom Penh',
    'Nearly new Lexus RX 350h F-Sport in stunning Sonic Titanium. Self-charging hybrid with 246 combined horsepower. Lexus Safety System+, 14" touchscreen, Mark Levinson 21-speaker audio, panoramic roof. Purchased by expat relocating. Perfect flagship for business executives.',
    'scraped', true, 'Import KH Auto', '+855 23 777 007')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=800', false, 1),
    (cid, 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800', false, 2);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Self-charging hybrid — no plug needed', true),
    (cid, '21-speaker Mark Levinson audio', true),
    (cid, 'F-Sport with adaptive suspension', true),
    (cid, 'Only 6,500km — essentially new', true),
    (cid, 'Premium service costs more than Toyota', false),
    (cid, 'Parts supply slower than mainstream brands', false);

  -- ── 8. Mercedes-Benz GLC 300 AMG Line ───────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Mercedes-Benz GLC 300 AMG Line',
    b_mercedes, 'GLC 300', 2022, t_suv, f_gasoline, tr_auto,
    65000, 61000, 'Overpriced', 14000, 'Obsidian Black', 2000, 5,
    'Phnom Penh',
    'Mercedes-Benz GLC 300 AMG Line in premium condition. MBUX touchscreen with voice control, Burmester sound system, 19" AMG wheels, ambient lighting package. Imported via Singapore dealer. All maintenance at Mercedes dealer Phnom Penh.',
    'scraped', false, 'Luxury Auto PH', '+855 23 999 008')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'AMG Line styling package', true),
    (cid, 'MBUX AI voice control system', true),
    (cid, 'Burmester surround sound', true),
    (cid, 'Strong brand prestige', true),
    (cid, 'Priced above market value', false),
    (cid, 'High maintenance and parts cost', false);

  -- ── 9. BMW 320i M Sport ──────────────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2021 BMW 320i M Sport',
    b_bmw, '320i', 2021, t_sedan, f_gasoline, tr_auto,
    42000, 43500, 'Fair', 38000, 'Alpine White', 2000, 5,
    'Phnom Penh',
    'Sporty BMW 320i M Sport with the perfect balance of performance and luxury. 184hp 2.0 TwinPower Turbo, 8-speed automatic. M Sport suspension, 18" M wheels, sport seats with heating. iDrive 7 with 10.25" display, BMW Live Cockpit. Fun to drive daily.',
    'user', false, 'Panha Lim', '+855 77 345 009')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'M Sport package — sharper dynamics', true),
    (cid, 'Heated sport seats front and rear', true),
    (cid, 'BMW ConnectedDrive + wireless CarPlay', true),
    (cid, 'Exciting to drive on open roads', true),
    (cid, 'Higher than average running costs', false),
    (cid, 'Firm M Sport ride on rough roads', false);

  -- ── 10. Hyundai Tucson 1.6T Premium ─────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Hyundai Tucson 1.6 Turbo Premium',
    b_hyundai, 'Tucson', 2022, t_suv, f_gasoline, tr_auto,
    25000, 29500, 'Good Deal', 21000, 'Phantom Black', 1600, 5,
    'Phnom Penh',
    'Excellent value Hyundai Tucson 1.6 Turbo — one of the best mid-size SUVs available. Panoramic sunroof, Bose 8-speaker audio, heated and ventilated front seats, 360° camera system, blind spot warning. Selling below market due to owner upgrading. First come first served.',
    'user', false, 'Nary Sok', '+855 12 678 010')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1590510296227-13d7aac29736?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Priced well below market value', true),
    (cid, 'Panoramic sunroof + Bose audio', true),
    (cid, '360° camera for easy parking', true),
    (cid, 'Heated and ventilated front seats', true),
    (cid, 'Less prestigious brand than Japanese rivals', false),
    (cid, 'Resale value slightly lower than Toyota/Honda', false);

  -- ── 11. Kia Sportage 1.6T ────────────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Kia Sportage 1.6 Turbo',
    b_kia, 'Sportage', 2022, t_suv, f_gasoline, tr_auto,
    22500, 27000, 'Good Deal', 25500, 'Snow White Pearl', 1600, 5,
    'Kampot',
    'Brand new generation Kia Sportage with bold design. 1.6 turbo engine with smooth 7-speed DCT. 12.3" panoramic display, wireless phone charging, KIA Drive Wise safety suite. Living in Kampot, moving to Phnom Penh, selling to avoid shipping cost. Priced to sell fast.',
    'user', false, 'James Walker', '+855 96 234 011')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1606611013016-969c19ba27bb?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1590510296227-13d7aac29736?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Significantly below market price', true),
    (cid, 'Latest generation with bold styling', true),
    (cid, '12.3" panoramic dual display', true),
    (cid, 'KIAS Drive Wise safety suite', true),
    (cid, 'Located in Kampot — may need transport', false),
    (cid, 'DCT can shudder at low speed', false);

  -- ── 12. Ford Ranger Wildtrak 2.0 Bi-Turbo ───────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2021 Ford Ranger Wildtrak 2.0 Bi-Turbo',
    b_ford, 'Ranger Wildtrak', 2021, t_pickup, f_diesel, tr_auto,
    30000, 31500, 'Fair', 43000, 'Meteor Grey', 2000, 5,
    'Sihanoukville',
    'Ford Ranger Wildtrak Bi-Turbo — the premium pickup. 213hp twin-turbo diesel, best-in-class towing 3,500kg. 10" SYNC 4 touchscreen, 360° camera, FordPass Connect. Used for coastal property development. Serviced every 5,000km at Ford dealer. All receipts kept.',
    'user', false, 'Tom Richards', '+855 96 777 012')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '3,500kg tow rating — class leading', true),
    (cid, '360° camera system', true),
    (cid, 'Full Ford dealer service history', true),
    (cid, 'Best payload capacity in segment', true),
    (cid, 'Located in Sihanoukville', false),
    (cid, 'High-spec trim has more electronics to maintain', false);

  -- ── 13. Mitsubishi Pajero Sport 2.4 GT ──────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Mitsubishi Pajero Sport 2.4 GT',
    b_mitsubishi, 'Pajero Sport', 2022, t_suv, f_diesel, tr_auto,
    33000, 35000, 'Fair', 22000, 'Graphite Grey', 2400, 7,
    'Phnom Penh',
    'Tough and capable Mitsubishi Pajero Sport GT with 7 seats. 181hp diesel with Super Select 4WD-II — locks into 4L for true off-road. 8" touchscreen with Apple CarPlay, powered tailgate, Mitsubishi e-Assist safety. Popular with NGO workers for province travel.',
    'user', false, 'Vanna Chea', '+855 88 456 013')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1554843231-0b5fb3f24dc8?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1551830820-41e5f6cfc2a1?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Super Select 4WD-II — true off-road', true),
    (cid, '7-seat capacity — great for family', true),
    (cid, 'Powered tailgate for convenience', true),
    (cid, 'Strong resale value in Cambodia', true),
    (cid, 'Older interior design vs competitors', false),
    (cid, 'Long body — harder to maneuver in city', false);

  -- ── 14. Mazda CX-5 2.5 Turbo AWD ────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2021 Mazda CX-5 2.5 Turbo AWD',
    b_mazda, 'CX-5', 2021, t_suv, f_gasoline, tr_auto,
    24500, 28000, 'Good Deal', 31000, 'Machine Grey Metallic', 2500, 5,
    'Phnom Penh',
    'Beautiful Mazda CX-5 2.5 Turbo in the iconic Machine Grey Metallic. KODO design is stunning inside and out. 227hp turbo feels like a sports SUV. Bose 10-speaker audio, 360° view monitor, i-ACTIVSENSE safety. Mazda is underrated in Cambodia — buy at a discount, enjoy premium quality.',
    'user', false, 'Kimheng Rin', '+855 85 234 014')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1591073113125-e46713c829ed?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '227hp turbo — most powerful in class', true),
    (cid, 'Premium Bose 10-speaker audio', true),
    (cid, 'Stunning KODO design inside and out', true),
    (cid, 'Priced below market — great value', true),
    (cid, 'Mazda parts slightly harder to find', false),
    (cid, 'Lower resale vs Toyota/Honda', false);

  -- ── 15. Nissan Navara 2.5 VL 4WD ────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2019 Nissan Navara 2.5 VL 4WD',
    b_nissan, 'Navara', 2019, t_pickup, f_diesel, tr_auto,
    16500, 19000, 'Good Deal', 69000, 'Burning Red', 2500, 5,
    'Battambang',
    'Reliable Nissan Navara VL with top-spec features. Leather seats, 7" touchscreen, forward collision warning, lane departure. 4WD for wet season dirt roads. Honest seller — buying a house, need cash. Can arrange delivery to Phnom Penh for serious buyer.',
    'user', false, 'Sophal Men', '+855 92 123 015')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'VL top-spec — leather and all features', true),
    (cid, 'Priced significantly below market', true),
    (cid, '4WD for all Cambodia terrain', true),
    (cid, 'Seller motivated — price negotiable', true),
    (cid, 'Higher mileage — 69,000km', false),
    (cid, 'Located in Battambang', false);

  -- ── 16. BMW X5 xDrive40i ─────────────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2023 BMW X5 xDrive40i',
    b_bmw, 'X5', 2023, t_suv, f_gasoline, tr_auto,
    88000, 95000, 'Good Deal', 7000, 'Black Sapphire', 3000, 7,
    'Phnom Penh',
    'Near-new BMW X5 xDrive40i — the ultimate luxury SUV. 340hp inline-6, 0-100 in 5.5 seconds. BMW Live Cockpit Professional (dual 12.3" screens), Harman Kardon audio, panoramic sky lounge roof, air suspension. 7-seat configuration, massage front seats. Importer stock at below-retail price.',
    'scraped', true, 'Euro Auto KH', '+855 23 456 016')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1535732820275-9a2a3f5e5d93?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800', false, 1),
    (cid, 'https://images.unsplash.com/photo-1617654112368-307921291f42?w=800', false, 2);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '340hp — 0 to 100km/h in 5.5 seconds', true),
    (cid, 'Air suspension adapts to any road', true),
    (cid, 'Massage front seats + panoramic roof', true),
    (cid, 'Priced below retail for quick sale', true),
    (cid, 'Very high purchase price', false),
    (cid, 'Premium fuel and high maintenance costs', false);

  -- ── 17. Audi A4 2.0 TFSI ─────────────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2020 Audi A4 2.0 TFSI S Line',
    b_audi, 'A4', 2020, t_sedan, f_gasoline, tr_auto,
    32000, 33000, 'Fair', 45000, 'Navarra Blue', 2000, 5,
    'Phnom Penh',
    'Sophisticated Audi A4 S Line with Quattro AWD. Virtual Cockpit 12.3" digital cluster, MMI Navigation Plus, B&O sound system, adaptive LED matrix headlights. S Line body kit gives sporty presence. German precision engineering for those who appreciate refinement.',
    'user', false, 'Hans Müller', '+855 96 567 017')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1616788494707-ec28f08d05a1?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1542362567-b07e54358753?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Quattro AWD for all-weather confidence', true),
    (cid, 'B&O premium sound system', true),
    (cid, 'Virtual Cockpit — stunning digital dash', true),
    (cid, 'S Line body — sporty European look', true),
    (cid, 'Audi parts expensive in Cambodia', false),
    (cid, 'Service intervals shorter than Japanese cars', false);

  -- ── 18. Isuzu D-Max 3.0 Hi-Lander 4WD ──────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2022 Isuzu D-Max 3.0 Hi-Lander 4WD',
    b_isuzu, 'D-Max', 2022, t_pickup, f_diesel, tr_auto,
    28000, 30000, 'Fair', 28000, 'Onyx Grey', 3000, 5,
    'Siem Reap',
    'Workhorse Isuzu D-Max 3.0 Hi-Lander — the most reliable pickup in Cambodia. 190hp diesel with 450Nm torque, 3,500kg tow capacity. 9" touchscreen, Apple CarPlay, ISUZU BIG 9 safety system. Popular with construction, agriculture, and province work. Huge parts availability nationwide.',
    'user', false, 'Chan Virak', '+855 12 456 018')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1563720223185-11003d516935?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '450Nm torque — outstanding towing', true),
    (cid, 'Isuzu parts available across Cambodia', true),
    (cid, 'Most reliable diesel pickup engine', true),
    (cid, '9" touchscreen with Apple CarPlay', true),
    (cid, 'Ride comfort less than SUV', false),
    (cid, 'Located in Siem Reap', false);

  -- ── 19. Hyundai Santa Fe 2.5T Premium ───────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2021 Hyundai Santa Fe 2.5T Premium AWD',
    b_hyundai, 'Santa Fe', 2021, t_suv, f_gasoline, tr_auto,
    34500, 38000, 'Good Deal', 23000, 'Creme White', 2500, 7,
    'Phnom Penh',
    'Family-perfect Hyundai Santa Fe 2.5 Turbo AWD with 7 seats. 281hp — more power than most competitors. Relaxation front seats (14-way powered), Bose premium sound, 8" rear entertainment displays for kids. Remote smart parking. Private sale — no dealer markup. Price firm.',
    'user', false, 'Meng Channara', '+855 77 890 019')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1590510296227-13d7aac29736?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, '281hp — most powerful in 7-seat segment', true),
    (cid, 'Rear entertainment for children', true),
    (cid, '14-way powered relaxation front seats', true),
    (cid, 'Private sale — below dealer pricing', true),
    (cid, 'Hyundai lower resale than Toyota', false),
    (cid, 'Turbo petrol drinks more in traffic', false);

  -- ── 20. Toyota bZ4X Electric AWD ─────────────────────────
  INSERT INTO cars (title, brand_id, model, year, car_type_id, fuel_type_id, transmission_id,
    price_usd, estimated_value_usd, price_label, mileage_km, color, engine_cc, seats,
    location, description, source, is_featured, seller_name, seller_phone)
  VALUES ('2023 Toyota bZ4X Electric AWD',
    b_toyota, 'bZ4X', 2023, t_suv, f_ev, tr_auto,
    45000, 48000, 'Good Deal', 12000, 'Wind Chill Pearl', NULL, 5,
    'Phnom Penh',
    'Cambodia first pure electric Toyota SUV. 218hp dual-motor AWD, 0-100 in 6.9 seconds. 71.4kWh battery — 460km real-world range. Solar charging roof adds up to 1,800km/year free. 12.3" touchscreen, Toyota Safety Sense 3.0. Solar carport at home required for best experience. The future is here.',
    'scraped', true, 'EV Cambodia', '+855 23 111 020')
  RETURNING id INTO cid;

  INSERT INTO car_images (car_id, url, is_primary, display_order) VALUES
    (cid, 'https://images.unsplash.com/photo-1628297437426-55510e68c432?w=800', true,  0),
    (cid, 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=800', false, 1);

  INSERT INTO car_features (car_id, feature, is_pro) VALUES
    (cid, 'Zero fuel cost — fully electric', true),
    (cid, 'Solar roof adds free range daily', true),
    (cid, '460km range — enough for any Cambodia trip', true),
    (cid, 'AWD with instant electric torque', true),
    (cid, 'Charging infrastructure still developing in Cambodia', false),
    (cid, 'Higher upfront cost vs petrol equivalent', false);

END $$;
