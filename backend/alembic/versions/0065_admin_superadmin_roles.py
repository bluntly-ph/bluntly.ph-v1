"""Administrator and Super Admin replace moderator (owner decisions B-D).

Revision ID: 0065_admin_superadmin_roles
Revises: 0064_routing_enum_values
Create Date: 2026-09-28

`member_role` is rebuilt as user | seller | administrator | super_admin, with
no `moderator` value left to grant, and `member_type` as shopper | seller |
administrator. Existing rows map deterministically, from data the owner
already set — this migration decides nobody's authority:

    role = moderator AND is_super_admin      -> super_admin
    role = moderator                         -> administrator
    member_type = moderator                  -> administrator
    everything else                          -> unchanged

`users.is_super_admin` (0038) and its check constraint go: the role is now the
one source of truth, and a second flag that could disagree with it is how an
authorization bug starts. See docs/ADMIN_SUPERADMIN_MIGRATION.md for the
production rollout, which is a coordinated release: a build from before this
migration cannot read the new role values, and a build from after it cannot
read `moderator`.

Downgrade is supported and lossless for authority: administrator and
super_admin both become moderator, with is_super_admin restored from
super_admin.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0065_admin_superadmin_roles"
down_revision = "0064_routing_enum_values"
branch_labels = None
depends_on = None


def _rebuild(type_name: str, column: str, values: tuple[str, ...], mapping_sql: str,
             default: str) -> None:
    labels = ", ".join(f"'{v}'" for v in values)
    op.execute(f"CREATE TYPE {type_name}_next AS ENUM ({labels})")
    op.execute(f"ALTER TABLE users ALTER COLUMN {column} DROP DEFAULT")
    op.execute(f"ALTER TABLE users ALTER COLUMN {column} TYPE {type_name}_next "
               f"USING ({mapping_sql})::{type_name}_next")
    op.execute(f"ALTER TABLE users ALTER COLUMN {column} SET DEFAULT '{default}'")
    op.execute(f"DROP TYPE {type_name}")
    op.execute(f"ALTER TYPE {type_name}_next RENAME TO {type_name}")


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_super_admin_is_moderator")
    _rebuild("member_role", "role", ("user", "seller", "administrator", "super_admin"),
             "CASE WHEN role::text = 'moderator' AND is_super_admin THEN 'super_admin' "
             "WHEN role::text = 'moderator' THEN 'administrator' ELSE role::text END",
             "user")
    _rebuild("member_type", "member_type", ("shopper", "seller", "administrator"),
             "CASE WHEN member_type::text = 'moderator' THEN 'administrator' "
             "ELSE member_type::text END",
             "shopper")
    op.drop_column("users", "is_super_admin")


def downgrade() -> None:
    op.add_column("users", sa.Column("is_super_admin", sa.Boolean(), nullable=False,
                                     server_default=sa.text("false")))
    op.execute("UPDATE users SET is_super_admin = true WHERE role::text = 'super_admin'")
    _rebuild("member_role", "role", ("user", "seller", "moderator"),
             "CASE WHEN role::text IN ('administrator', 'super_admin') THEN 'moderator' "
             "ELSE role::text END",
             "user")
    _rebuild("member_type", "member_type", ("shopper", "seller", "moderator"),
             "CASE WHEN member_type::text = 'administrator' THEN 'moderator' "
             "ELSE member_type::text END",
             "shopper")
    op.create_check_constraint("ck_users_super_admin_is_moderator", "users",
                               "NOT is_super_admin OR role = 'moderator'")
