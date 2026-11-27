"""Record each canonical product's own marketplace link as its listing.

Revision ID: 0054_record_source_listings
Revises: 0053_repair_rejection_links
Create Date: 2026-09-25

A product is submitted with a marketplace link and a moderator canonicalizes
it. Attaching a duplicate submission recorded that duplicate's link as a
product_platforms listing (canonical_service.attach_listing), but the
product's own link never was, so a product sold on one marketplace looked
like one with no listing. The affiliate-link queue lists only reviews whose
product has a monetizable listing (monetization_attention._awaiting_filter),
so an earnings-approved review of such a product never reached it.

canonical_service.record_source_listing now records the link at
canonicalization. This adds the rows that were never written: one per
canonicalized product whose source_url host is a marketplace, using the same
domains as config.DEFAULT_AFFILIATE_DOMAINS (frozen here, as a migration
must be). Data only; idempotent through uq_product_platform. The downgrade
removes nothing: an existing listing may since have been edited or
referenced, and the missing row was the defect.
"""

from __future__ import annotations

from alembic import op

revision = "0054_record_source_listings"
down_revision = "0053_repair_rejection_links"
branch_labels = None
depends_on = None

DOMAINS = {
    "shopee": ("s.shopee.ph", "shope.ee", "shopee.ph"),
    "lazada": ("s.lazada.com.ph", "c.lazada.com.ph", "lazada.com.ph"),
    "amazon": ("amzn.to", "amazon.com", "www.amazon.com"),
}


def _platform_case() -> str:
    arms = []
    for platform, domains in DOMAINS.items():
        tests = " OR ".join(f"h.host = '{d}' OR h.host LIKE '%.{d}'" for d in domains)
        arms.append(f"WHEN {tests} THEN '{platform}'")
    return "CASE " + " ".join(arms) + " END"


BACKFILL_SQL = f"""
INSERT INTO product_platforms (id, product_id, platform, platform_url, is_monetizable,
                               created_at, updated_at)
SELECT gen_random_uuid(), m.id, m.platform::platform, m.source_url, true,
       m.created_at, m.created_at
  FROM (SELECT h.id, h.source_url, h.created_at, {_platform_case()} AS platform
          FROM (SELECT p.id, p.source_url, p.created_at,
                       lower(substring(p.source_url FROM
                             '^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/?#]*@)?([^/:?#]+)')) AS host
                  FROM products p
                 WHERE p.status = 'canonicalized' AND p.source_url IS NOT NULL) AS h
       ) AS m
 WHERE m.platform IS NOT NULL
ON CONFLICT ON CONSTRAINT uq_product_platform DO NOTHING
"""


def upgrade() -> None:
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    pass
