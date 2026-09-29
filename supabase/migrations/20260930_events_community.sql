-- Adds the Events + Community tables that the app expects but the live DB is missing.
-- Copied from supabase/schema-only.sql. Paste into Supabase → SQL Editor → Run. Safe to run once.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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

