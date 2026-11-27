"""Make an existing account the FIRST Super Admin (owner decision D). Dry run by default.

After migration 0065, Super Admin is an ordinary role that a Super Admin grants
from user management — but a database with none yet needs one to start from.
This script is that start, and nothing more:

  * it names no account itself: the owner passes `--email` or `--staff-ref`;
  * it refuses when an active Super Admin already exists (every later grant
    goes through PATCH /admin/users/{id}/role, audited with a human actor);
  * it refuses a claimed seller (§9) and an account that does not exist;
  * `--apply` is required to write; the change and its audit row
    (`role_grant`, event `bootstrap`) commit together;
  * production is refused unless `--allow-production` is passed, and even then
    the target is printed first. Running it against production is the owner's
    decision, recorded in docs/ADMIN_SUPERADMIN_MIGRATION.md — never automatic.

    python -m scripts.bootstrap_super_admin --email owner@example.org
    python -m scripts.bootstrap_super_admin --email owner@example.org --apply
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.core.env_guard import guard_cli
from app.db.session import SessionLocal
from app.models.enums import MemberRole
from app.models.user import User
from app.services.staff_directory_service import normalise_staff_ref
from app.services.staff_roles import active_super_admins, audit_role_change


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--email", help="the account's email address")
    who.add_argument("--staff-ref", help="the account's staff reference (USR-000123)")
    ap.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    ap.add_argument("--allow-production", action="store_true",
                    help="Required against production; the owner's explicit decision.")
    args = ap.parse_args(argv)
    guard_cli("bootstrap_super_admin", argv=argv if argv is not None else sys.argv[1:],
              production_is_legitimate=True)

    with SessionLocal() as db:
        existing = active_super_admins(db, lock=True)
        if existing:
            print(f"refused: {existing} active Super Admin(s) already exist. Grant further "
                  "Super Admins from user management, where the change is audited with "
                  "its actor.", file=sys.stderr)
            return 1
        if args.email:
            target = db.scalar(select(User).where(func.lower(User.email) == args.email.lower()))
        else:
            target = db.scalar(select(User).where(
                User.staff_ref == normalise_staff_ref(args.staff_ref)))
        if target is None:
            print("refused: no such account. The person signs up first.", file=sys.stderr)
            return 1
        if target.is_claimed_seller:
            print("refused: a claimed seller's account can't hold a staff role (§9).",
                  file=sys.stderr)
            return 1
        if target.is_suspended:
            print("refused: the account is suspended.", file=sys.stderr)
            return 1
        print(f"target: {target.staff_ref} (@{target.username or '-'}), "
              f"role {target.role.value} -> super_admin")
        if not args.apply:
            print("dry run: nothing written. Re-run with --apply.")
            return 0
        previous = target.role
        target.role = MemberRole.super_admin
        audit_role_change(db, None, target, previous, MemberRole.super_admin,
                          event="bootstrap")
        db.commit()
        print("done: the account is the Super Admin; the grant is audited (role_grant).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
