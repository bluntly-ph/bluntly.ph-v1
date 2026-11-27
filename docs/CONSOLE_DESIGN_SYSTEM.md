# Console design system (Admin and Seller)

The Admin console (`/admin/*`) and the Seller console (`/seller/[storeId]/*`) share one
visual language, drawn in the Figma file `lso4Ri4hDaZxvCebhUqlY5` (library "bluntly.ph":
Admin/Chip, Shadow/Modal, the `status/*` variables, Pagination, Admin Components · States
8265:27081). This page says where each piece lives in code, so a screen reuses it instead
of copying class strings.

Rules:

- Colours, shadows and radii come from tokens (`app/tokens/*.css`), never a hex or an
  `rgba()` in a component. If a value is missing, add a token here first.
- A pattern used on two screens belongs in `components/console/` (or the Admin component
  that both consoles already import). Don't copy its classes into a third screen.
- A frame's number or state is drawn only when real data stands behind it. Otherwise show
  the truthful empty state.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `--surface-app` | #f2f2f2 | page ground, callouts, segmented-control track, disabled fields |
| `--surface-card` | #ffffff | cards, modals, menus, fields |
| `--text-primary` / `--text-secondary` / `--text-muted` | ink 800 at 100 / 70 / 40 % | body, labels and hints, placeholders |
| `--line-hairline-30` | ink at 30 % | field border (default state) |
| `--border-subtle` | ink at 10 % | card and menu hairlines, row dividers |
| `--accent-primary` | brand 600 #ef5821 | primary button, focus border, current step |
| `--accent-danger` | #d80027 | error border, error text, over-limit counter |
| `--border-input` / `--border-input-hover` / `--border-input-disabled` | ink 30 / 50 / 10 % | field borders (Figma border/input, hover, disabled) |
| `--text-disabled` | ink 50 % | disabled field text |
| `--ring-field-focus` / `--ring-field-error` | 3px brand 16 % / danger 14 % | field focus and error rings |
| `--status-neutral-bg/fg` | #f2f2f2 / #202020 | Chip `neutral` |
| `--status-baseline-bg/fg` | #e8f3e8 / #1faf38 | Chip `success` |
| `--status-high-bg/fg` | #fbede3 / #e94f1d | Chip `warning` ("needs attention") |
| `--status-critical-bg/fg` | #fbe6e9 / #d80027 | Chip `critical` (flagged / negative) |
| `--status-watch-bg/fg` | #fcf8e7 / #f17a23 | watch tier (priority tiers) |
| `--shadow-modal` | 0 8 12 0 ink 10 % | Figma Shadow/Modal: modals, confirms, menus, popovers |
| `--shadow-segment` | 0 1 1 0 ink 6 % | the selected segment of a segmented control |
| `--disabled-surface` / `--disabled-text` | #dddddd / #7f7f7f | disabled primary controls |

Radii used in the consoles: 8 px (icon buttons, segments), 12 px (fields, callouts, inner
cards), 16 px (cards, menus, confirms), 24 px (large modals), full (pills, chips, buttons).

## Components

| Figma component | Code | Notes |
| --- | --- | --- |
| Field (input) | `FIELD_INPUT` (44 px), `FIELD_INPUT_COMPACT` (40 px) in `components/console/fields.ts` | `FIELD_LABEL` above it, `FIELD_HINT` / `FIELD_ERROR` under it |
| Field (textarea) + counter | `CountedTextarea` in `components/console/CountedTextarea.tsx`; `countState` / `countProblem` in `counted-model.ts` | see Field states below |
| Admin/Chip | `Chip` (`components/console/Chip.tsx`) | tones neutral, muted, success, warning, critical, dark |
| Callout | `Callout` (`components/console/Callout.tsx`) | Info icon by default; Lock for privacy notes |
| IconButton | `ICON_BUTTON` (`components/console/popover.ts`) | 32 px, 8 px radius |
| Menu (Sort / Filter / Search) | `MENU` + `usePopover` (`popover.ts`); `ListControls` for the toolbar trio | closes on outside click and Escape |
| Pagination | `Pagination` + `pagination-model.ts` | range, pages, 10 / 25 / 50 per page. URL mode (`basePath` + `query`) or `onChange`. Used by People, Products, Payouts, Sellers, Affiliate, Seller Reviews/Products. Never a native `<select>` for the page size. The review queue keeps its offset pager (real links) |
| Toggle | `Switch` (`components/console/Switch.tsx`) | 36×20, brand when on; `role="switch"`, named by `labelledBy` or `label`. Seller Settings, PayMongo test mode, product spec "in the name". Don't disable it while saving (focus would drop) |
| Product Thumbnail | `ProductThumbnail` | 30 / 32 / 40 px |
| Compare Row | `CompareRow` (`components/console/CompareRow.tsx`) | dot = this store / product, tick = peers / category; `toned` only when higher is better; `dense` inside a product card |
| Modal | `AdminModal` (`components/admin/AdminModal.tsx`) | native `<dialog>`; focus stays inside; Escape closes |
| Confirm | `ConfirmDialog` + `Consequence` (`components/admin/ConfirmDialog.tsx`) | tones primary, danger, ink; `disabled` keeps the confirm off |
| Nav row / rail | `NavRow` (`components/admin/AdminNav.tsx`); the Seller rail reuses it | inert items say "Soon" and why |
| Image viewer | `ImageViewer` | signed links only |
| Top-bar search | `GlobalSearch` | as you type, keyboard navigation |
| Skeletons | `Skeleton` (`components/ui/Skeleton.tsx`); Seller screens in `components/seller/console/SellerSkeletons.tsx` | real frames, grey content |

Still drawn inline (one screen each today; extract when a second screen needs them):
Meter (`SellerOverview`), Quick action item (`SellerShell`), Notification item
(`StoreNotifications`), Step list (`ClaimStatusDialog`), Option row / Radio
(`StoreProfileActions`), Inline reply (`components/messages/Thread.tsx`).

## Field states

Figma Admin/Input and Admin/Textarea (Admin Components · States 8265:27081, read 2026-10-04).
One class string sets every state:

| State | How it is set | Look (token) |
| --- | --- | --- |
| Default | — | `--border-input` (ink 30 %), white |
| Hover | `:hover` | `--border-input-hover` (ink 50 %) |
| Focus | `:focus` | `--accent-primary` border + `--ring-field-focus` (3px, brand 16 %) |
| Error / over the limit | `aria-invalid="true"` | `--accent-danger` border + `--ring-field-error` (3px, danger 14 %), also while focused or hovered |
| Disabled | `disabled` | `--surface-app` fill, `--border-input-disabled` (ink 10 %), `--text-disabled` (ink 50 %) |

The error look comes from `aria-invalid`, so what a screen reader announces always
matches what is drawn. Admin/Field draws a 12px Medium label, 6px gap, the 40px input and a
12px helper that turns danger in the Error tone. The Seller overlays (Respond 8197:21320,
EditAnswer 8202:22530) put an uppercase 12px label above a textarea, with the hint on the
left under it and the counter on the right. `CountedTextarea` follows the overlays.

### Counted textarea

- Use no `maxLength`. It blocks the over-limit state from ever showing, and it cuts a long
  paste without saying so. `CountedTextarea` lets the text run over. It then shows the
  danger border, the counter in danger ("1,020 / 1,000") and "20 characters over the
  limit. Shorten it to send." in place of the hint.
- The screen keeps its submit off while `countState(value, max).over` is true. A `min`
  shows "At least N characters." once something is typed. The API enforces the same
  limits, so the client is a convenience, not the guard.
- Counting is by code point, like the API (Python `len`), so an emoji counts as one
  character.
- Short single-line inputs (names, usernames, links) keep `maxLength`: no counter is drawn
  for them.

Used by: Seller Respond / Flag as fake / Answer / Request a change; Admin Reject earnings /
Take down / Unmark best answer / Product link decision / Suspend / Mark payout failed /
Support reply and internal note. The reviewer New message form draws its counter inside
the field (Figma 8276:29363) and uses `countState` for the same over-limit state.

## Security-driven presentation

- A report's `evidence_url` is reporter-supplied. It is shown as a labelled external link
  and is never loaded as an image in a staff browser: an outside host would learn who is
  looking (`components/admin/ReportDetailPanel.tsx`). Images that Bluntly stores (message
  attachments, receipts) open in `ImageViewer` through short-lived signed links.
