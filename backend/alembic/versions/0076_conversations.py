"""Conversations: the Inbox and Messages (Figma Screen/Admin/Inbox 8291:30461,
Screen/Seller/Inbox 8304:32524, Screen/Messages 8296:31219).

Revision ID: 0076_conversations
Revises: 0075_seller_claim_withdrawn
Create Date: 2026-10-03

A member (a store's owner or claimant, or a reviewer) writes to the Bluntly
team; any Administrator or Super Admin answers, one may be assigned. Two
tables: `conversations` (the thread: topic, optional link to what it is about,
status, assignee, per-side read state) and `conversation_messages` (messages
and the system's event lines, with an optional private attachment).

Owner decision 2026-10-03 ("merge into Inbox"): a claim's or an appeal's chat
becomes ONE conversation, keyed by `case_key`. This migration COPIES every
existing case chat — the `platform_settings` rows `chat:claim:<id>`,
`chat:appeal:<id>` and `chat:appeal-reviewer:<id>` — into conversations and
messages. The settings rows are left untouched (nothing is deleted), so the
copy can be checked against its source. A copied thread is marked read on both
sides as of this migration, so it does not reappear as new.

Also adds 'conversation' to moderation_action (assign / status / close /
reopen / move to Support are audited). Hidden from PostgREST like every table
(RLS on, no policy, nothing granted to the API roles).

Downgrade drops the two tables and the four types. The case chats copied in
are still in `platform_settings`, but everything written AFTER 0076 (every
Inbox conversation, and case chat messages, which now live only here) is lost
by a downgrade — export the two tables first if that matters. The enum value added to moderation_action stays
(PostgreSQL cannot remove one).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

from alembic import op

revision = "0076_conversations"
down_revision = "0075_seller_claim_withdrawn"
branch_labels = None
depends_on = None

AUDIENCE = ENUM("seller", "reviewer", name="conversation_audience", create_type=False)
TOPIC = ENUM("appeal", "claim", "product", "payout", "review", "report", "account", "other",
             name="conversation_topic", create_type=False)
STATUS = ENUM("open", "waiting", "closed", name="conversation_status", create_type=False)
KIND = ENUM("message", "event", name="conversation_message_kind", create_type=False)

TABLES = ("conversations", "conversation_messages")


def _hide(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON {table} FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON {table} FROM authenticated;
          END IF;
        END $$;""")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'conversation'")

    for t in (AUDIENCE, TOPIC, STATUS, KIND):
        t.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("reference", sa.String(24), nullable=False, unique=True),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("audience", AUDIENCE, nullable=False),
        sa.Column("seller_id", UUID(as_uuid=True),
                  sa.ForeignKey("sellers.id", ondelete="SET NULL")),
        sa.Column("topic", TOPIC, nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("link_type", sa.String(16)),
        sa.Column("link_id", UUID(as_uuid=True)),
        sa.Column("case_key", sa.String(80), unique=True),
        sa.Column("status", STATUS, nullable=False, server_default="open"),
        sa.Column("assigned_admin_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("last_member_message_at", sa.DateTime(timezone=True)),
        sa.Column("last_staff_message_at", sa.DateTime(timezone=True)),
        sa.Column("member_read_at", sa.DateTime(timezone=True)),
        sa.Column("staff_read_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("support_request_id", UUID(as_uuid=True),
                  sa.ForeignKey("seller_support_requests.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(
            "link_type IS NULL OR link_type IN "
            "('appeal', 'claim', 'payout', 'review', 'report', 'product')",
            name="ck_conversations_link_type"),
    )
    op.create_index("ix_conversations_member", "conversations", ["member_id", "last_message_at"])
    op.create_index("ix_conversations_inbox", "conversations", ["status", "last_message_at"])
    op.create_index("ix_conversations_seller", "conversations", ["seller_id", "last_message_at"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", KIND, nullable=False, server_default="message"),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("from_staff", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attachment_key", sa.String(255)),
        sa.Column("attachment_name", sa.String(160)),
        sa.Column("attachment_type", sa.String(64)),
        sa.Column("attachment_size", sa.Integer()),
        sa.Column("legacy_id", sa.String(24)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    op.create_index("ix_conversation_messages_thread", "conversation_messages",
                    ["conversation_id", "created_at"])
    for t in TABLES:
        _hide(t)

    # ---- copy the case chats (claims, appeals, the reviewer's side of appeals)
    op.execute("""
        INSERT INTO conversations (reference, member_id, audience, seller_id, topic, subject,
                                   link_type, link_id, case_key, status, closed_at)
        SELECT 'MSG-' || upper(substr(md5(ps.key), 1, 8)), c.user_id, 'seller', c.seller_id,
               'claim', left('Claim · ' || s.display_name, 160), 'claim', c.id,
               substr(ps.key, 6),
               CASE WHEN c.status = 'pending' THEN 'open' ELSE 'closed' END::conversation_status,
               CASE WHEN c.status = 'pending' THEN NULL ELSE coalesce(c.decided_at, now()) END
          FROM platform_settings ps
          JOIN seller_claims c ON ps.key = 'chat:claim:' || c.id::text
          JOIN sellers s ON s.id = c.seller_id
         WHERE jsonb_array_length(coalesce(ps.value -> 'messages', '[]'::jsonb)) > 0
    """)
    op.execute("""
        INSERT INTO conversations (reference, member_id, audience, seller_id, topic, subject,
                                   link_type, link_id, case_key, status, closed_at)
        SELECT 'MSG-' || upper(substr(md5(ps.key), 1, 8)), a.appellant_id, 'seller', a.seller_id,
               'appeal',
               left('Appeal · ' || coalesce(u.display_name, '@' || u.username, 'a reviewer')
                    || '''s review', 160),
               'appeal', a.id, substr(ps.key, 6),
               CASE WHEN a.status IN ('open', 'substantiation_requested') THEN 'open'
                    ELSE 'closed' END::conversation_status,
               CASE WHEN a.status IN ('open', 'substantiation_requested') THEN NULL
                    ELSE coalesce(a.decided_at, now()) END
          FROM platform_settings ps
          JOIN seller_review_appeals a ON ps.key = 'chat:appeal:' || a.id::text
          LEFT JOIN seller_reviews r ON r.id = a.seller_review_id
          LEFT JOIN users u ON u.id = r.reviewer_id
         WHERE jsonb_array_length(coalesce(ps.value -> 'messages', '[]'::jsonb)) > 0
    """)
    op.execute("""
        INSERT INTO conversations (reference, member_id, audience, seller_id, topic, subject,
                                   link_type, link_id, case_key, status, closed_at)
        SELECT 'MSG-' || upper(substr(md5(ps.key), 1, 8)), r.reviewer_id, 'reviewer', NULL,
               'review', left('Your review of ' || s.display_name, 160),
               'appeal', a.id, substr(ps.key, 6),
               CASE WHEN a.status IN ('open', 'substantiation_requested') THEN 'open'
                    ELSE 'closed' END::conversation_status,
               CASE WHEN a.status IN ('open', 'substantiation_requested') THEN NULL
                    ELSE coalesce(a.decided_at, now()) END
          FROM platform_settings ps
          JOIN seller_review_appeals a ON ps.key = 'chat:appeal-reviewer:' || a.id::text
          JOIN seller_reviews r ON r.id = a.seller_review_id
          JOIN sellers s ON s.id = a.seller_id
         WHERE jsonb_array_length(coalesce(ps.value -> 'messages', '[]'::jsonb)) > 0
    """)
    op.execute("""
        INSERT INTO conversation_messages (conversation_id, kind, author_id, from_staff, body,
                                           legacy_id, created_at)
        SELECT conv.id, 'message', u.id, coalesce((m ->> 'from_staff')::boolean, false),
               m ->> 'body', left(m ->> 'id', 24), (m ->> 'sent_at')::timestamptz
          FROM conversations conv
          JOIN platform_settings ps ON ps.key = 'chat:' || conv.case_key
          CROSS JOIN LATERAL jsonb_array_elements(ps.value -> 'messages') AS m
          LEFT JOIN users u ON u.id::text = m ->> 'author_id'
         WHERE conv.case_key IS NOT NULL
    """)
    op.execute("""
        UPDATE conversations conv
           SET last_message_at = agg.last_at,
               last_member_message_at = agg.member_at,
               last_staff_message_at = agg.staff_at,
               member_read_at = now(),
               staff_read_at = now(),
               created_at = agg.first_at
          FROM (SELECT conversation_id,
                       min(created_at) AS first_at,
                       max(created_at) AS last_at,
                       max(created_at) FILTER (WHERE NOT from_staff) AS member_at,
                       max(created_at) FILTER (WHERE from_staff) AS staff_at
                  FROM conversation_messages GROUP BY conversation_id) agg
         WHERE agg.conversation_id = conv.id
    """)


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_thread", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    for name in ("ix_conversations_seller", "ix_conversations_inbox", "ix_conversations_member"):
        op.drop_index(name, table_name="conversations")
    op.drop_table("conversations")
    for t in (KIND, STATUS, TOPIC, AUDIENCE):
        t.drop(op.get_bind(), checkfirst=True)
