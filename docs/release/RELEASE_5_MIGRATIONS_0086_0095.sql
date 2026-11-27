-- Release 5 production migrations: 0085_email_outbox -> 0095_trust_score_override
-- Generated offline from defense-build-oct6 (alembic upgrade 0085_email_outbox:0095_trust_score_override --sql)
-- FOR REVIEW. The supported way to apply is alembic itself (docs/ENVIRONMENTS.md):
--   alembic -x allow_production=1 current   # expect 0085_email_outbox
--   alembic -x allow_production=1 upgrade head
-- Three transactions; the 0089 and 0092 ALTER TYPE ... ADD VALUE statements run between them, outside any transaction.
-- Do not execute without the owner's explicit approval.
BEGIN;

-- Running upgrade 0085_email_outbox -> 0086_storage_buckets

DO $$ BEGIN
  IF to_regclass('storage.buckets') IS NOT NULL THEN
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) VALUES ('avatars', 'avatars', true, 5242880, ARRAY['image/png', 'image/jpeg', 'image/webp']) ON CONFLICT (id) DO NOTHING;
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) VALUES ('product-images', 'product-images', true, 5242880, ARRAY['image/png', 'image/jpeg', 'image/webp']) ON CONFLICT (id) DO NOTHING;
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) VALUES ('review-photos', 'review-photos', true, 8388608, ARRAY['image/png', 'image/jpeg', 'image/webp']) ON CONFLICT (id) DO NOTHING;
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) VALUES ('review-receipts', 'review-receipts', false, 8388608, ARRAY['image/png', 'image/jpeg', 'image/webp']) ON CONFLICT (id) DO NOTHING;
    INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) VALUES ('message-attachments', 'message-attachments', false, 5242880, ARRAY['image/png', 'image/jpeg', 'image/webp', 'application/pdf']) ON CONFLICT (id) DO NOTHING;
  END IF;
END $$;;

UPDATE alembic_version SET version_num='0086_storage_buckets' WHERE alembic_version.version_num = '0085_email_outbox';

-- Running upgrade 0086_storage_buckets -> 0087_rls_every_table

ALTER TABLE cron_credentials ENABLE ROW LEVEL SECURITY;

ALTER TABLE cron_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE email_otps ENABLE ROW LEVEL SECURITY;

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE rate_limit_counters ENABLE ROW LEVEL SECURITY;

ALTER TABLE request_geo_buckets ENABLE ROW LEVEL SECURITY;

ALTER TABLE review_first_vote_geo_buckets ENABLE ROW LEVEL SECURITY;

ALTER TABLE review_reading_sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE review_view_buckets ENABLE ROW LEVEL SECURITY;

ALTER TABLE seller_claims ENABLE ROW LEVEL SECURITY;

ALTER TABLE seller_reviews ENABLE ROW LEVEL SECURITY;

ALTER TABLE sellers ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON cron_credentials FROM anon, authenticated;
    REVOKE ALL ON cron_runs FROM anon, authenticated;
    REVOKE ALL ON email_otps FROM anon, authenticated;
    REVOKE ALL ON notifications FROM anon, authenticated;
    REVOKE ALL ON rate_limit_counters FROM anon, authenticated;
    REVOKE ALL ON request_geo_buckets FROM anon, authenticated;
    REVOKE ALL ON review_first_vote_geo_buckets FROM anon, authenticated;
    REVOKE ALL ON review_reading_sessions FROM anon, authenticated;
    REVOKE ALL ON review_view_buckets FROM anon, authenticated;
    REVOKE ALL ON seller_claims FROM anon, authenticated;
    REVOKE ALL ON seller_reviews FROM anon, authenticated;
    REVOKE ALL ON sellers FROM anon, authenticated;
  END IF;
END $$;;

UPDATE alembic_version SET version_num='0087_rls_every_table' WHERE alembic_version.version_num = '0086_storage_buckets';

-- Running upgrade 0087_rls_every_table -> 0088_function_search_path

ALTER FUNCTION users_staff_ref_is_immutable() SET search_path = public, pg_temp;

ALTER FUNCTION users_keep_one_super_admin() SET search_path = public, pg_temp;

UPDATE alembic_version SET version_num='0088_function_search_path' WHERE alembic_version.version_num = '0087_rls_every_table';

-- Running upgrade 0088_function_search_path -> 0089_product_import_action

COMMIT;

ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'product_import';

BEGIN;

UPDATE alembic_version SET version_num='0089_product_import_action' WHERE alembic_version.version_num = '0088_function_search_path';

-- Running upgrade 0089_product_import_action -> 0090_appeal_kind

ALTER TABLE seller_review_appeals ADD COLUMN kind VARCHAR(20) DEFAULT 'never_ordered' NOT NULL;

ALTER TABLE seller_review_appeals ADD CONSTRAINT ck_seller_review_appeal_kind CHECK (kind IN ('never_ordered', 'untrue', 'breaks_rules'));

UPDATE alembic_version SET version_num='0090_appeal_kind' WHERE alembic_version.version_num = '0089_product_import_action';

-- Running upgrade 0090_appeal_kind -> 0091_store_change_requests

CREATE TABLE store_change_requests (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    seller_id UUID NOT NULL, 
    requested_by_id UUID, 
    conversation_id UUID, 
    field VARCHAR(24) NOT NULL, 
    current_value TEXT, 
    requested_value TEXT NOT NULL, 
    status VARCHAR(16) DEFAULT 'pending' NOT NULL, 
    decided_by_id UUID, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    decision_note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_store_change_field CHECK (field IN ('display_name', 'store_url', 'registration')), 
    CONSTRAINT ck_store_change_status CHECK (status IN ('pending', 'approved', 'rejected')), 
    FOREIGN KEY(seller_id) REFERENCES sellers (id) ON DELETE CASCADE, 
    FOREIGN KEY(requested_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE SET NULL, 
    FOREIGN KEY(decided_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_store_change_seller ON store_change_requests (seller_id, created_at);

CREATE INDEX ix_store_change_conversation ON store_change_requests (conversation_id);

CREATE UNIQUE INDEX uq_store_change_pending ON store_change_requests (seller_id, field) WHERE status = 'pending';

ALTER TABLE store_change_requests ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON store_change_requests FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON store_change_requests FROM authenticated;
          END IF;
        END $$;;

UPDATE alembic_version SET version_num='0091_store_change_requests' WHERE alembic_version.version_num = '0090_appeal_kind';

-- Running upgrade 0091_store_change_requests -> 0092_support_waiting

COMMIT;

ALTER TYPE support_request_status ADD VALUE IF NOT EXISTS 'waiting_for_seller' BEFORE 'resolved';

ALTER TYPE support_request_category ADD VALUE IF NOT EXISTS 'store_change' BEFORE 'general';

BEGIN;

UPDATE alembic_version SET version_num='0092_support_waiting' WHERE alembic_version.version_num = '0091_store_change_requests';

-- Running upgrade 0092_support_waiting -> 0093_message_edits

ALTER TABLE conversation_messages ADD COLUMN edited_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE conversation_messages ADD COLUMN unsent_at TIMESTAMP WITH TIME ZONE;

CREATE TABLE conversation_message_revisions (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    message_id UUID NOT NULL, 
    action VARCHAR(8) NOT NULL, 
    body TEXT NOT NULL, 
    attachment_name VARCHAR(160), 
    actor_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_message_revision_action CHECK (action IN ('edit', 'unsend')), 
    FOREIGN KEY(message_id) REFERENCES conversation_messages (id) ON DELETE CASCADE, 
    FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_message_revisions_message ON conversation_message_revisions (message_id, created_at);

ALTER TABLE conversation_message_revisions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON conversation_message_revisions FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON conversation_message_revisions FROM authenticated;
          END IF;
        END $$;;

CREATE TABLE conversation_message_hides (
    message_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (message_id, user_id), 
    FOREIGN KEY(message_id) REFERENCES conversation_messages (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_message_hides_user ON conversation_message_hides (user_id);

ALTER TABLE conversation_message_hides ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON conversation_message_hides FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON conversation_message_hides FROM authenticated;
          END IF;
        END $$;;

UPDATE alembic_version SET version_num='0093_message_edits' WHERE alembic_version.version_num = '0092_support_waiting';

-- Running upgrade 0093_message_edits -> 0094_review_photos

ALTER TABLE reviews ADD COLUMN photo_urls TEXT[] DEFAULT '{}'::text[] NOT NULL;

UPDATE reviews SET photo_urls = ARRAY[photo_url] WHERE photo_url IS NOT NULL AND photo_url <> '';

ALTER TABLE reviews ADD CONSTRAINT ck_review_photo_count CHECK (cardinality(photo_urls) <= 4);

UPDATE alembic_version SET version_num='0094_review_photos' WHERE alembic_version.version_num = '0093_message_edits';

-- Running upgrade 0094_review_photos -> 0095_trust_score_override

ALTER TABLE users ADD COLUMN computed_reputation_score NUMERIC(5, 2) DEFAULT '0' NOT NULL;

UPDATE users SET computed_reputation_score = reputation_score;

ALTER TABLE users ADD COLUMN reputation_score_override NUMERIC(5, 2);

ALTER TABLE users ADD COLUMN reputation_override_by_id UUID;

ALTER TABLE users ADD FOREIGN KEY(reputation_override_by_id) REFERENCES users (id) ON DELETE SET NULL;

ALTER TABLE users ADD COLUMN reputation_override_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE users ADD COLUMN reputation_override_reason TEXT;

ALTER TABLE users ADD CONSTRAINT ck_users_reputation_override_range CHECK (reputation_score_override IS NULL OR (reputation_score_override >= 0 AND reputation_score_override <= 100));

UPDATE alembic_version SET version_num='0095_trust_score_override' WHERE alembic_version.version_num = '0094_review_photos';

COMMIT;

