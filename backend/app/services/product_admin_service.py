"""Staff add products to the catalogue: one by hand, or many from a CSV file.

Owner request, 2026-10-03: Products needs "Add product" and "Import products".
Until now a product only reached the catalogue as a member's submission named
from the Queue (canonicalize), or through POST /products, which a staff caller
used without the name parts, specs or aliases the catalogue stores.

Both paths here build the product exactly as the Edit modal names one — brand,
line, variant, type, category, specs (with "In name"), aliases and the listing
link — in one transaction, so there is never a half-named product. Neither ever
creates a duplicate silently: a product whose listing link, or whose name once
case, spacing and punctuation are set aside, is already in the catalogue is
refused (one product: 409 `product_exists`) or reported as "exists" (import),
using the same matching every submission goes through (product_matching).

Who added a product is recorded as before: `products.submitted_by` and
`created_at` (product creation has never had a moderation-log action; aliases
keep theirs, `alias_add`). No migration.

There is no image column in the file: product images are uploaded (POST
/products/{id}/image) and never fetched from a URL (the no-scraping rule,
docs/MILESTONES.md 2026-07-15; every catalogue image lives in the
product-images bucket).

The file format is documented column by column in docs/PRODUCT_CSV_IMPORT.md;
COLUMNS, REQUIRED and EXAMPLE below are its source, and the template the admin
downloads is generated from them. In short: a header row (any order, any case;
spaces and hyphens read as "_"; `listing_url` is read as `source_url`), then
brand*, line*, category*, variant, type, aliases ("a | b"), source_url, specs
("Label: Value | Label: Value"). Unknown columns are reported and ignored. At
most MAX_IMPORT_ROWS rows and MAX_IMPORT_BYTES bytes.

Preview never writes. Each row is `new`, `exists` (the catalogue already has it,
by its listing link or its name — never created again), `duplicate` (an earlier
row of this file), `conflict` (its listing belongs to one product and its name
to another, or the listing is on two products: never written) or `error`.
An `exists` row may be ATTACHED instead of skipped: the row's listing link
becomes another listing of that product and its name and aliases become
aliases. Nothing else of the product changes — not its name, category, specs or
photo. Applying re-checks every row against the catalogue as it is then, writes
the new and attached rows in ONE transaction (if any row fails, nothing is
written and the failing rows say why), and records one `product_import` entry in
the Activity log with the counts (never the file).
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import ModerationAction, ProductStatus
from app.models.moderation import ModerationLog
from app.models.product import Product, ProductAlias, ProductPlatform
from app.models.user import User
from app.schemas.product import ProductCanonicalize, ProductSpec
from app.schemas.urls import web_url_or_none
from app.services import canonical_service, product_matching
from app.services.canonical_service import marketplace_for_url
from app.services.product_search import normalize

MAX_IMPORT_ROWS = 500
MAX_IMPORT_BYTES = 1024 * 1024
COLUMNS = ("brand", "line", "variant", "type", "category", "aliases", "source_url", "specs")
REQUIRED = ("brand", "line", "category")
#: Other spellings of a column's header that mean the same column.
HEADER_SYNONYMS = {"listing_url": "source_url"}
#: The template's example row (GET /admin/products/import/template).
EXAMPLE = {
    "brand": "Jisulife", "line": "Handheld Fan", "variant": "Life 9", "type": "",
    "category": "home-appliances", "aliases": "jisulife fan | life9",
    "source_url": "https://shopee.ph/example-i.1.2",
    "specs": "Battery: 4000 mAh | Weight: 160 g",
}


@dataclass
class NewProduct:
    """A product as staff name it, before it exists."""

    naming: ProductCanonicalize
    source_url: str | None = None

    @property
    def name(self) -> str:
        return self.naming.canonical_name()


@dataclass
class ImportRow:
    line: int  # the file's line number (the header is line 1)
    #: Preview: new | exists | duplicate | conflict | error.
    #: After applying: created | attached (an exists row the admin attached) |
    #: failed (nothing was written); the others keep their preview outcome.
    outcome: str
    name: str | None = None
    category: str | None = None
    errors: list[str] = field(default_factory=list)
    product_id: uuid.UUID | None = None  # exists/attached: the match; created: the new product
    existing_name: str | None = None
    duplicate_of_line: int | None = None
    #: exists: how it matched — "listing", "name" or "listing and name".
    matched_by: str | None = None
    #: exists: what attaching would add (empty: nothing new, so it can only be skipped).
    attach_adds: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    applied: bool
    rows: list[ImportRow]
    ignored_columns: list[str] = field(default_factory=list)
    #: When applying failed: why nothing was written.
    failure: str | None = None

    def count(self, outcome: str) -> int:
        return sum(1 for r in self.rows if r.outcome == outcome)

    def summary(self) -> dict[str, int]:
        """The counts the result screen shows (TOTAL / IMPORTED / ATTACHED /
        SKIPPED / INVALID / FAILED) beside every outcome's own count."""
        counts = {k: self.count(k) for k in ("new", "exists", "duplicate", "conflict", "error",
                                             "created", "attached", "failed")}
        counts.update(total=len(self.rows), imported=counts["created"],
                      skipped=counts["exists"] + counts["duplicate"] + counts["conflict"],
                      invalid=counts["error"])
        return counts


def _existing(db: Session, new: NewProduct) -> Product | None:
    return product_matching.find_existing_product(db, name=new.name, source_url=new.source_url)


def _build(db: Session, actor: User, new: NewProduct) -> Product:
    naming = new.naming
    product = Product(
        canonical_name=new.name, category=naming.category, brand=naming.brand.strip() or None,
        line=naming.product_line.strip()[:120] or None,
        key_spec=(naming.key_spec or "").strip() or None,
        descriptor=(naming.descriptor or "").strip() or None,
        specs=[s.model_dump() for s in (naming.specs or [])] or None,
        source_url=new.source_url, submitted_by=actor.id,
        status=ProductStatus.canonicalized, product_id=f"prd_{uuid.uuid4().hex[:10]}",
    )
    db.add(product)
    db.flush()
    canonical_service.record_source_listing(db, product)
    canonical_service.add_aliases(db, product, naming.aliases, actor.id)
    return product


def create(db: Session, actor: User, new: NewProduct) -> Product:
    """Add one named product to the catalogue, or refuse a duplicate (409)."""
    if not new.naming.category:
        raise AppError("Choose a category for this product.", code="category_required",
                       status_code=422, title="Invalid product")
    match = _existing(db, new)
    if match is not None:
        raise AppError(
            f"“{match.canonical_name}” is already in the catalogue. Edit it instead.",
            code="product_exists", status_code=409, title="Conflicting state",
            extra={"product_id": str(match.id), "canonical_name": match.canonical_name})
    product = _build(db, actor, new)
    db.commit()
    db.refresh(product)
    return product


def _cell(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _specs(text: str) -> list[ProductSpec]:
    out = []
    for part in [p for p in text.split("|") if p.strip()]:
        label, sep, value = part.partition(":")
        if not sep:
            raise ValueError(f"Spec “{part.strip()}” needs a label and a value, as “Label: Value”.")
        out.append(ProductSpec(label=label, value=value))
    return out


def _parse_row(row: dict[str, str]) -> NewProduct:
    """One CSV row as a NewProduct, or ValueError with the reasons, each a sentence."""
    errors = [f"{col.capitalize()} is required." for col in REQUIRED if not _cell(row, col)]
    if errors:
        raise ValueError(" ".join(errors))
    try:
        specs = _specs(_cell(row, "specs")) if _cell(row, "specs") else None
        naming = ProductCanonicalize(
            brand=_cell(row, "brand"), product_line=_cell(row, "line"),
            key_spec=_cell(row, "variant") or None, descriptor=_cell(row, "type") or None,
            category=_cell(row, "category"),
            aliases=[a.strip() for a in _cell(row, "aliases").split("|") if a.strip()],
            specs=specs)
        source_url = web_url_or_none(_cell(row, "source_url") or None, field="Listing links")
    except ValidationError as exc:
        raise ValueError(" ".join(_message(e) for e in exc.errors())) from exc
    return NewProduct(naming=naming, source_url=source_url)


def _message(err: dict) -> str:
    where = ".".join(str(p) for p in err.get("loc", ()) if not isinstance(p, int))
    msg = str(err.get("msg", "is invalid")).removeprefix("Value error, ")
    column = {"product_line": "line", "key_spec": "variant", "descriptor": "type"}.get(where, where)
    return f"{column.capitalize()}: {msg}." if column else f"{msg}."


def _header(raw: str | None) -> str:
    key = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    return HEADER_SYNONYMS.get(key, key)


def _read(data: bytes) -> tuple[list[tuple[int, dict[str, str]]], list[str]]:
    """(rows as (line, {column: cell}), ignored column headers)."""
    if len(data) > MAX_IMPORT_BYTES:
        raise AppError(f"That file is larger than {MAX_IMPORT_BYTES // 1024} KB.",
                       code="import_too_large", status_code=413, title="File too large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("Save the file as UTF-8 CSV and try again.", code="import_not_utf8",
                       status_code=422, title="Unreadable file") from exc
    reader = csv.reader(io.StringIO(text))
    header = [_header(h) for h in next(reader, [])]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise AppError(
            "The first row must name the columns; missing: " + ", ".join(missing) + ".",
            code="import_columns_missing", status_code=422, title="Invalid file",
            extra={"columns": list(COLUMNS), "required": list(REQUIRED)})
    twice = sorted({h for h in header if h in COLUMNS and header.count(h) > 1})
    if twice:
        raise AppError("Each column may appear once; repeated: " + ", ".join(twice) + ".",
                       code="import_columns_repeated", status_code=422, title="Invalid file")
    ignored = [h for h in dict.fromkeys(header) if h and h not in COLUMNS]
    rows = []
    for cells in reader:
        row = {h: (cells[i] if i < len(cells) else "") for i, h in enumerate(header)
               if h in COLUMNS}
        if not any(_cell(row, c) for c in COLUMNS):
            continue  # a blank line is not a product
        rows.append((reader.line_num, row))
    if len(rows) > MAX_IMPORT_ROWS:
        raise AppError(
            f"A file holds at most {MAX_IMPORT_ROWS} products; this one has {len(rows)}.",
            code="import_too_many_rows", status_code=422, title="Invalid file")
    return rows, ignored


def template_csv() -> str:
    """The template file: the header and the example row, from COLUMNS."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerow([EXAMPLE.get(c, "") for c in COLUMNS])
    return out.getvalue()


def _quoted(product: Product) -> str:
    return f"“{product.canonical_name or 'an unnamed product'}”"


def _classify(db: Session, out: ImportRow, new: NewProduct) -> Product | None:
    """Set out.outcome to new / exists / conflict from the catalogue as it is now;
    return the matched product (exists)."""
    by_listing = product_matching.products_for_listing(db, new.source_url)
    by_name = product_matching.product_for_name(db, new.name)
    if len(by_listing) > 1:
        out.outcome = "conflict"
        out.errors = [f"This listing is on {len(by_listing)} products already: "
                      + ", ".join(_quoted(p) for p in by_listing[:3])
                      + ". Merge them in Products first."]
        return None
    listing = by_listing[0] if by_listing else None
    if listing is not None and by_name is not None and by_name.id != listing.id:
        out.outcome = "conflict"
        out.errors = [f"The listing belongs to {_quoted(listing)}, but the name matches "
                      f"{_quoted(by_name)}. Fix the row, or merge the two products."]
        return None
    match = listing or by_name
    if match is None:
        out.outcome = "new"
        return None
    out.outcome = "exists"
    out.product_id, out.existing_name = match.id, match.canonical_name
    out.matched_by = ("listing and name" if listing is not None and by_name is not None
                      else "listing" if listing is not None else "name")
    return match


def _attach_plan(db: Session, product: Product, new: NewProduct) -> tuple[str | None, list[str]]:
    """(the listing link attaching would add, the aliases it would add)."""
    listing = None
    key = product_matching.listing_key(new.source_url)
    if (key is not None and marketplace_for_url(new.source_url) is not None
            and key not in product_matching.product_listing_keys(db, product.id)):
        listing = new.source_url
    have = set(db.scalars(select(ProductAlias.normalized)
                          .where(ProductAlias.product_id == product.id)))
    have.add(normalize(product.canonical_name))
    aliases: list[str] = []
    for alias in [new.name, *new.naming.aliases]:
        key = normalize(alias)
        if key and key not in have:
            have.add(key)
            aliases.append(alias.strip())
    return listing, aliases


def _describe(listing: str | None, aliases: list[str]) -> list[str]:
    out = [f"listing {listing}"] if listing else []
    out += [f"alias “{a}”" for a in aliases]
    return out


def _attach(db: Session, actor: User, product: Product, new: NewProduct) -> None:
    listing, aliases = _attach_plan(db, product, new)
    if listing is not None:
        platform = marketplace_for_url(listing)
        db.add(ProductPlatform(product_id=product.id, platform=platform, platform_url=listing))
        db.add(ModerationLog(target_type=None, target_ref=product.id, moderator_id=actor.id,
                             action=ModerationAction.listing_attach,
                             context={"listing": listing, "via": "product_import"}))
    canonical_service.add_aliases(db, product, aliases, actor.id)


def import_products(db: Session, actor: User, data: bytes, *, apply: bool,
                    attach: set[int] | None = None, filename: str | None = None) -> ImportResult:
    """Preview (apply=False: nothing is written) or apply a product CSV.

    `attach` names the lines (file line numbers) of `exists` rows the admin
    chose to attach; every other `exists` row is skipped. Applying re-reads the
    file and re-checks every row against the catalogue as it is now: a line
    asked to attach that is no longer an `exists` row with something to add is
    simply not attached. New rows are created and attached rows attached in one
    transaction; if any write fails, everything is rolled back and the failing
    rows are marked `failed` with the reason.
    """
    attach = attach or set()
    rows, ignored = _read(data)
    results: list[ImportRow] = []
    seen: dict[str, int] = {}
    to_create: list[tuple[ImportRow, NewProduct]] = []
    to_attach: list[tuple[ImportRow, NewProduct, Product]] = []
    for line, row in rows:
        try:
            new = _parse_row(row)
        except ValueError as exc:
            # What the file said, so the admin can find the row to fix.
            said = " ".join(_cell(row, c) for c in ("brand", "line", "variant", "type")).split()
            results.append(ImportRow(line=line, outcome="error", name=" ".join(said) or None,
                                     errors=[str(exc)]))
            continue
        out = ImportRow(line=line, outcome="new", name=new.name, category=new.naming.category)
        keys = [k for k in (product_matching.name_key(new.name),
                            f"url:{product_matching.listing_key(new.source_url)}"
                            if new.source_url else None) if k]
        first = next((seen[k] for k in keys if k in seen), None)
        if first is not None:
            out.outcome, out.duplicate_of_line = "duplicate", first
        else:
            match = _classify(db, out, new)
            if match is not None:
                out.attach_adds = _describe(*_attach_plan(db, match, new))
                if line in attach and out.attach_adds:
                    to_attach.append((out, new, match))
            elif out.outcome == "new":
                to_create.append((out, new))
        for k in keys:
            seen.setdefault(k, line)
        results.append(out)

    result = ImportResult(applied=False, rows=results, ignored_columns=ignored)
    if not apply or not (to_create or to_attach):
        result.applied = apply
        return result

    failed: list[ImportRow] = []
    for out, new in to_create:
        try:
            with db.begin_nested():
                out.product_id = _build(db, actor, new).id
        except Exception as exc:  # noqa: BLE001 - reported per row, then all rolled back
            out.errors = [f"Couldn't be saved: {type(exc).__name__}."]
            failed.append(out)
    for out, new, match in to_attach:
        try:
            with db.begin_nested():
                _attach(db, actor, match, new)
        except Exception as exc:  # noqa: BLE001
            out.errors = [f"Couldn't be attached: {type(exc).__name__}."]
            failed.append(out)
    if failed:
        db.rollback()
        for out in failed:
            out.outcome = "failed"
        for out, _ in to_create:
            if out.outcome != "failed":
                out.product_id = None
        result.failure = (f"Nothing was imported: {len(failed)} row"
                          f"{'' if len(failed) == 1 else 's'} couldn't be saved. "
                          "Fix them and import again.")
        return result

    for out, _ in to_create:
        out.outcome = "created"
    for out, _, _ in to_attach:
        out.outcome = "attached"
    result.applied = True
    summary = result.summary()
    db.add(ModerationLog(
        target_type=None, target_ref=None, moderator_id=actor.id,
        action=ModerationAction.product_import,
        notes=(f"{(filename or 'A file')[:120]}: {summary['total']} rows — "
               f"{summary['imported']} added, {summary['attached']} attached, "
               f"{summary['skipped']} skipped, {summary['invalid']} couldn't be imported."),
        context={"file": (filename or "")[:120] or None,
                 **{k: summary[k] for k in ("total", "imported", "attached", "skipped",
                                            "invalid")},
                 "created_ids": [str(o.product_id) for o, _ in to_create][:50]}))
    db.commit()
    return result
