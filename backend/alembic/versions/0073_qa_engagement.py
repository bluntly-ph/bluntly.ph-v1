"""Q&A thread engagement: votes and replies (Figma Question Detail v6B 7731:15601).

Revision ID: 0073_qa_engagement
Revises: 0072_payout_account_name
Create Date: 2026-10-02

The question page is a thread: the question takes up-votes, every answer and
every reply takes up / down votes, and answers carry nested replies ("Reply
(n)", "Continue this thread"). Nothing recorded any of it: `answers.helpful_votes`
existed but nothing wrote it, and there was no reply table.

`qa_votes`: one row per member per target. Exactly one of question_id /
answer_id / reply_id is set (CHECK), a question takes only "up" (CHECK), and a
partial unique index per target makes a second row for the same (target,
member) impossible, so a double tap cannot double-count. Helpfulness only, as on
seller reviews: no money, no trust stage.

`answer_replies`: a reply under an answer, optionally under another reply
(parent_id, depth 1..3: the frame draws three levels). Soft removal keeps the
thread's shape.

Both enable RLS and revoke the public roles, as every application table does.
Additive; the downgrade drops both tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0073_qa_engagement"
down_revision = "0072_payout_account_name"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _lock_down(table: str) -> None:
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
    op.create_table(
        "answer_replies",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("answer_id", _UUID, sa.ForeignKey("answers.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("parent_id", _UUID, sa.ForeignKey("answer_replies.id", ondelete="CASCADE")),
        sa.Column("author_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("depth", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("depth BETWEEN 1 AND 3", name="ck_answer_reply_depth"),
    )
    op.create_index("ix_answer_replies_answer_created", "answer_replies",
                    ["answer_id", "created_at"])

    op.create_table(
        "qa_votes",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("question_id", _UUID, sa.ForeignKey("questions.id", ondelete="CASCADE")),
        sa.Column("answer_id", _UUID, sa.ForeignKey("answers.id", ondelete="CASCADE")),
        sa.Column("reply_id", _UUID, sa.ForeignKey("answer_replies.id", ondelete="CASCADE")),
        sa.Column("direction", postgresql.ENUM("up", "down", name="vote_direction",
                                               create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("num_nonnulls(question_id, answer_id, reply_id) = 1",
                           name="ck_qa_vote_one_target"),
        sa.CheckConstraint("question_id IS NULL OR direction = 'up'",
                           name="ck_qa_vote_question_up_only"),
    )
    for target in ("question_id", "answer_id", "reply_id"):
        op.create_index(f"uq_qa_votes_{target}_user", "qa_votes", [target, "user_id"],
                        unique=True, postgresql_where=sa.text(f"{target} IS NOT NULL"))
    op.create_index("ix_qa_votes_user", "qa_votes", ["user_id", "created_at"])

    _lock_down("answer_replies")
    _lock_down("qa_votes")


def downgrade() -> None:
    op.drop_table("qa_votes")
    op.drop_table("answer_replies")
