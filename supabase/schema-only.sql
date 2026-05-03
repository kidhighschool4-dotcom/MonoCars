-- ============================================================
-- MonoCars — Schema Only (DDL + RLS + Vector Function)
-- Paste into Supabase SQL Editor → Run
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── USER PROFILES ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS profiles (
  id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name   text,
  phone       text,
  avatar_url  text,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

-- Auto-create a profile row whenever a new auth user is created
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name')
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE handle_new_user();

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_profiles"   ON profiles FOR SELECT USING (true);
CREATE POLICY "owner_update_profile"   ON profiles FOR UPDATE TO authenticated USING (id = auth.uid());
CREATE POLICY "service_all_profiles"   ON profiles FOR ALL TO service_role USING (true);

CREATE TABLE IF NOT EXISTS brands (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name       text NOT NULL UNIQUE,
  country    text NOT NULL,
  logo_url   text,
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

-- ─── CHAT ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
  id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  car_id      uuid NOT NULL REFERENCES cars(id)       ON DELETE CASCADE,
  buyer_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  seller_id   uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now(),
  UNIQUE (car_id, buyer_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id              uuid    PRIMARY KEY DEFAULT uuid_generate_v4(),
  conversation_id uuid    NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id       uuid    NOT NULL REFERENCES auth.users(id)    ON DELETE CASCADE,
  message_type    text    NOT NULL DEFAULT 'text'
                          CHECK (message_type IN ('text', 'voice', 'file')),
  content         text,
  file_url        text,
  file_name       text,
  file_size       integer,
  duration_secs   integer,
  is_read         boolean NOT NULL DEFAULT false,
  created_at      timestamptz DEFAULT now(),
  CONSTRAINT content_or_file CHECK (
    (message_type = 'text'              AND content  IS NOT NULL AND content  != '') OR
    (message_type IN ('voice', 'file')  AND file_url IS NOT NULL)
  )
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

CREATE INDEX IF NOT EXISTS idx_conversations_buyer   ON conversations(buyer_id);
CREATE INDEX IF NOT EXISTS idx_conversations_seller  ON conversations(seller_id);
CREATE INDEX IF NOT EXISTS idx_conversations_car     ON conversations(car_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created      ON messages(created_at DESC);

ALTER PUBLICATION supabase_realtime ADD TABLE messages;

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

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages       ENABLE ROW LEVEL SECURITY;

CREATE POLICY "participants_read_conversations"   ON conversations FOR SELECT TO authenticated
  USING (buyer_id = auth.uid() OR seller_id = auth.uid());
CREATE POLICY "buyer_insert_conversation"         ON conversations FOR INSERT TO authenticated
  WITH CHECK (buyer_id = auth.uid());
CREATE POLICY "participants_update_conversations" ON conversations FOR UPDATE TO authenticated
  USING (buyer_id = auth.uid() OR seller_id = auth.uid());
CREATE POLICY "service_all_conversations"         ON conversations FOR ALL TO service_role USING (true);

CREATE POLICY "participants_read_messages" ON messages FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM conversations WHERE id = conversation_id AND (buyer_id = auth.uid() OR seller_id = auth.uid())));
CREATE POLICY "participants_insert_messages" ON messages FOR INSERT TO authenticated
  WITH CHECK (sender_id = auth.uid() AND EXISTS (SELECT 1 FROM conversations WHERE id = conversation_id AND (buyer_id = auth.uid() OR seller_id = auth.uid())));
CREATE POLICY "recipient_mark_read" ON messages FOR UPDATE TO authenticated
  USING (sender_id != auth.uid() AND EXISTS (SELECT 1 FROM conversations WHERE id = conversation_id AND (buyer_id = auth.uid() OR seller_id = auth.uid())));
CREATE POLICY "service_all_messages" ON messages FOR ALL TO service_role USING (true);

-- ─── STORAGE BUCKET ────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'chat-media', 'chat-media', true, 52428800,
  ARRAY[
    'audio/webm','audio/mp4','audio/ogg','audio/wav','audio/mpeg',
    'image/jpeg','image/png','image/gif','image/webp',
    'application/pdf','text/plain',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ]
) ON CONFLICT (id) DO NOTHING;

CREATE POLICY "auth_upload_chat_media" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'chat-media');

CREATE POLICY "auth_read_chat_media" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'chat-media');

CREATE POLICY "owner_delete_chat_media" ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'chat-media' AND owner = auth.uid());

-- ─── EVENTS ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
  id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  title          text    NOT NULL,
  location       text    NOT NULL,
  event_date     timestamptz NOT NULL,
  description    text    NOT NULL,
  image_url      text,
  category       text    NOT NULL CHECK (category IN ('Motor Show','Car Meet','Racing','EV Show','Group Drive','Off-Road')),
  attendee_count integer NOT NULL DEFAULT 0,
  organizer_id   uuid             REFERENCES auth.users(id) ON DELETE SET NULL,
  is_published   boolean NOT NULL DEFAULT true,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_attendees (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id   uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz DEFAULT now(),
  UNIQUE (event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_events_date      ON events(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_events_category  ON events(category);
CREATE INDEX IF NOT EXISTS idx_event_att_event  ON event_attendees(event_id);
CREATE INDEX IF NOT EXISTS idx_event_att_user   ON event_attendees(user_id);

ALTER TABLE events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_attendees ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_events"          ON events          FOR SELECT USING (is_published = true);
CREATE POLICY "auth_insert_events"          ON events          FOR INSERT TO authenticated WITH CHECK (organizer_id = auth.uid());
CREATE POLICY "owner_update_events"         ON events          FOR UPDATE TO authenticated USING (organizer_id = auth.uid());
CREATE POLICY "owner_delete_events"         ON events          FOR DELETE TO authenticated USING (organizer_id = auth.uid());
CREATE POLICY "service_all_events"          ON events          FOR ALL TO service_role USING (true);

CREATE POLICY "auth_read_attendees"         ON event_attendees FOR SELECT TO authenticated USING (true);
CREATE POLICY "auth_join_event"             ON event_attendees FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "auth_leave_event"            ON event_attendees FOR DELETE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "service_all_attendees"       ON event_attendees FOR ALL TO service_role USING (true);

-- Keep attendee_count in sync
CREATE OR REPLACE FUNCTION update_event_attendee_count()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE events SET attendee_count = attendee_count + 1 WHERE id = NEW.event_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE events SET attendee_count = GREATEST(attendee_count - 1, 0) WHERE id = OLD.event_id;
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_event_attendee_count ON event_attendees;
CREATE TRIGGER trg_event_attendee_count
  AFTER INSERT OR DELETE ON event_attendees
  FOR EACH ROW EXECUTE PROCEDURE update_event_attendee_count();

-- ─── COMMUNITY ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS community_posts (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  content       text NOT NULL,
  post_type     text NOT NULL DEFAULT 'discussion' CHECK (post_type IN ('question','photo','discussion')),
  like_count    integer NOT NULL DEFAULT 0,
  comment_count integer NOT NULL DEFAULT 0,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS post_images (
  id            uuid    PRIMARY KEY DEFAULT uuid_generate_v4(),
  post_id       uuid    NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  url           text    NOT NULL,
  display_order integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS post_likes (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  post_id    uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz DEFAULT now(),
  UNIQUE (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS post_comments (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  post_id    uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  content    text NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_posts_created      ON community_posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_user         ON community_posts(user_id);
CREATE INDEX IF NOT EXISTS idx_post_images_post   ON post_images(post_id);
CREATE INDEX IF NOT EXISTS idx_post_likes_post    ON post_likes(post_id);
CREATE INDEX IF NOT EXISTS idx_post_likes_user    ON post_likes(user_id);
CREATE INDEX IF NOT EXISTS idx_post_comments_post ON post_comments(post_id);

ALTER TABLE community_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_images     ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_likes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_comments   ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_posts"          ON community_posts FOR SELECT USING (true);
CREATE POLICY "auth_insert_posts"          ON community_posts FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "owner_update_posts"         ON community_posts FOR UPDATE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "owner_delete_posts"         ON community_posts FOR DELETE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "service_all_posts"          ON community_posts FOR ALL TO service_role USING (true);

CREATE POLICY "public_read_post_images"    ON post_images     FOR SELECT USING (true);
CREATE POLICY "service_all_post_images"    ON post_images     FOR ALL TO service_role USING (true);

CREATE POLICY "auth_read_likes"            ON post_likes      FOR SELECT TO authenticated USING (true);
CREATE POLICY "auth_like_post"             ON post_likes      FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "auth_unlike_post"           ON post_likes      FOR DELETE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "service_all_likes"          ON post_likes      FOR ALL TO service_role USING (true);

CREATE POLICY "public_read_comments"       ON post_comments   FOR SELECT USING (true);
CREATE POLICY "auth_insert_comment"        ON post_comments   FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "owner_delete_comment"       ON post_comments   FOR DELETE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "service_all_comments"       ON post_comments   FOR ALL TO service_role USING (true);

-- Keep like_count and comment_count in sync
CREATE OR REPLACE FUNCTION update_post_like_count()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE community_posts SET like_count = like_count + 1 WHERE id = NEW.post_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE community_posts SET like_count = GREATEST(like_count - 1, 0) WHERE id = OLD.post_id;
  END IF;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION update_post_comment_count()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE community_posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE community_posts SET comment_count = GREATEST(comment_count - 1, 0) WHERE id = OLD.post_id;
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_post_like_count    ON post_likes;
DROP TRIGGER IF EXISTS trg_post_comment_count ON post_comments;

CREATE TRIGGER trg_post_like_count
  AFTER INSERT OR DELETE ON post_likes
  FOR EACH ROW EXECUTE PROCEDURE update_post_like_count();

CREATE TRIGGER trg_post_comment_count
  AFTER INSERT OR DELETE ON post_comments
  FOR EACH ROW EXECUTE PROCEDURE update_post_comment_count();

-- ─── DB FUNCTIONS ──────────────────────────────────────────

-- Send any message type; validates participant, inserts, bumps conversation
CREATE OR REPLACE FUNCTION send_chat_message(
  p_conversation_id uuid,
  p_message_type    text    DEFAULT 'text',
  p_content         text    DEFAULT NULL,
  p_file_url        text    DEFAULT NULL,
  p_file_name       text    DEFAULT NULL,
  p_file_size       integer DEFAULT NULL,
  p_duration_secs   integer DEFAULT NULL
)
RETURNS TABLE (
  id uuid, conversation_id uuid, sender_id uuid, message_type text,
  content text, file_url text, file_name text, file_size integer,
  duration_secs integer, is_read boolean, created_at timestamptz
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM conversations c
    WHERE c.id = p_conversation_id
      AND (c.buyer_id = auth.uid() OR c.seller_id = auth.uid())
  ) THEN
    RAISE EXCEPTION 'Not a participant';
  END IF;

  RETURN QUERY
  INSERT INTO messages (conversation_id, sender_id, message_type, content,
                        file_url, file_name, file_size, duration_secs)
  VALUES (p_conversation_id, auth.uid(), p_message_type, p_content,
          p_file_url, p_file_name, p_file_size, p_duration_secs)
  RETURNING id, conversation_id, sender_id, message_type, content,
            file_url, file_name, file_size, duration_secs, is_read, created_at;

  UPDATE conversations SET updated_at = now() WHERE id = p_conversation_id;
END;
$$;

-- Mark all messages from the other participant as read
CREATE OR REPLACE FUNCTION mark_messages_read(p_conversation_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM conversations c
    WHERE c.id = p_conversation_id
      AND (c.buyer_id = auth.uid() OR c.seller_id = auth.uid())
  ) THEN
    RAISE EXCEPTION 'Not a participant';
  END IF;

  UPDATE messages SET is_read = true
  WHERE conversation_id = p_conversation_id
    AND is_read = false
    AND sender_id != auth.uid();
END;
$$;

-- Total unread messages for the current user across all conversations
CREATE OR REPLACE FUNCTION get_unread_count()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_count integer;
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM messages m
  JOIN conversations c ON m.conversation_id = c.id
  WHERE (c.buyer_id = auth.uid() OR c.seller_id = auth.uid())
    AND m.sender_id != auth.uid()
    AND m.is_read = false;
  RETURN v_count;
END;
$$;
