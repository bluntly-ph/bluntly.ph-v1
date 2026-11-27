"""The private `message-attachments` bucket, and every other bucket the code uses.

Revision ID: 0086_storage_buckets
Revises: 0085_email_outbox
Create Date: 2026-10-04

Owner report 2026-10-04: uploading a file as evidence on a store claim fails.
Root cause, from production's storage log: every attachment written since 0076
went to `/object/message-attachments/...` and Supabase Storage answered 400 -
the bucket was never created (0076 said it "must exist" and left it to a manual
step that was never done, on production or on TEST). storage.upload_attachment
turned that into the 503 "Attachments aren't available right now", so a claimant
could send text but never a file, and the Admin claim review never saw evidence.

Buckets were provisioned by hand until now (qa/README.md, 2026-08-19). This makes
them part of the schema: every bucket in app.services.storage.BUCKETS is created
when it is missing, with the privacy, size limit and types it was given by hand.
ON CONFLICT DO NOTHING - an existing bucket is never changed (the lifecycle
columns stay NULL, which storage.protect_bucket_control_columns requires of a
plain INSERT). Only a Supabase database has a `storage` schema: on a plain
Postgres (local, CI) the block does nothing.

`message-attachments` is PRIVATE (signed links only, minted by the API after it
checks the caller is a party or staff), 5 MB like the other image buckets (the
API's own 4 MB check is the one that binds), photos and PDFs.

No downgrade: a bucket holds claim evidence, and Supabase refuses a bucket delete
from SQL anyway (storage.protect_delete). Remove one through the Storage API.
"""

from __future__ import annotations

from alembic import op

revision = "0086_storage_buckets"
down_revision = "0085_email_outbox"
branch_labels = None
depends_on = None

IMAGES = ("image/png", "image/jpeg", "image/webp")

#: (id, public, file_size_limit, allowed_mime_types) - the first four as they
#: stand on production (storage.buckets, 2026-10-04); the fifth is new.
BUCKETS: tuple[tuple[str, bool, int, tuple[str, ...]], ...] = (
    ("avatars", True, 5 * 1024 * 1024, IMAGES),
    ("product-images", True, 5 * 1024 * 1024, IMAGES),
    ("review-photos", True, 8 * 1024 * 1024, IMAGES),
    ("review-receipts", False, 8 * 1024 * 1024, IMAGES),
    ("message-attachments", False, 5 * 1024 * 1024, IMAGES + ("application/pdf",)),
)


def _insert(bucket: str, public: bool, limit: int, mimes: tuple[str, ...]) -> str:
    types = ", ".join(f"'{m}'" for m in mimes)
    return (f"INSERT INTO storage.buckets (id, name, public, file_size_limit, "
            f"allowed_mime_types) VALUES ('{bucket}', '{bucket}', "
            f"{'true' if public else 'false'}, {limit}, ARRAY[{types}]) "
            f"ON CONFLICT (id) DO NOTHING;")


#: PL/pgSQL resolves storage.buckets only when the branch runs, so the same
#: statement is safe on a database without the storage schema.
BUCKETS_SQL = f"""
DO $$ BEGIN
  IF to_regclass('storage.buckets') IS NOT NULL THEN
    {chr(10).join("    " + _insert(*b) for b in BUCKETS).lstrip()}
  END IF;
END $$;"""


def upgrade() -> None:
    op.execute(BUCKETS_SQL)


def downgrade() -> None:
    pass
