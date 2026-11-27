"""Branded email templates (Slice 1 Phase A).

Email is not the web. The constraints below are why this looks nothing like the
app's markup:

* **Tables, not flex/grid.** Outlook renders through Word's HTML engine, which
  has no modern layout support at all.
* **Inline styles.** Gmail strips <style> blocks in several contexts, notably
  the mobile apps and forwarded mail.
* **Poppins will not load.** Almost no client honours @font-face or a Google
  Fonts link, so the brand face is declared first and a web-safe stack carries
  the actual rendering.
* **The wordmark is the real PNG**, served from the production host and shown
  on the orange band (white artwork). `alt="bluntly"` covers the ~half of
  inboxes that block remote images.
* **A gradient needs a solid fallback.** `background-color` is declared before
  `background-image` so clients that drop gradients still get brand orange
  rather than white.

Every message ships both an HTML and a plain-text part: a text alternative is a
real deliverability signal, and some recipients genuinely read text only.
"""

from __future__ import annotations

# Brand values, matching app/tokens/colors.css.
_ORANGE = "#ef5821"
_ORANGE_DEEP = "#963719"
_INK = "#202020"
_SURFACE = "#f2f2f2"
_WHITE = "#ffffff"
_MUTED = "rgba(32,32,32,0.62)"

# The wordmark PNG, served from the production site. White artwork, shown on the
# orange band. Override with EMAIL_LOGO_URL if the canonical domain changes.
_LOGO_URL = "https://www.bluntly.ph/bluntly-logo.png"

# Kept as its own constant so the style attribute stays inside the line limit.
_BRAND_GRADIENT = (
    f"linear-gradient(135deg,#ffc596 0%,{_ORANGE} 45%,{_ORANGE_DEEP} 100%)"
)

_FONT = (
    "'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)

OTP_SUBJECT = "{code} is your bluntly verification code"


def otp_subject(code: str) -> str:
    """Leading the subject with the code lets people verify from the preview."""
    return OTP_SUBJECT.format(code=code)


def otp_text(code: str, ttl_minutes: int) -> str:
    return (
        f"Your bluntly verification code is {code}\n\n"
        f"Enter it in the app to finish signing in. "
        f"It expires in {ttl_minutes} minutes and can only be used once.\n\n"
        "If you didn't request this, you can ignore this email — "
        "nobody can access your account without the code.\n\n"
        "---\n"
        "bluntly.ph — Honest reviews. Real Payouts.\n"
        "No sponsorships. No bias. Ever.\n"
    )


def otp_html(code: str, ttl_minutes: int) -> str:
    spaced_code = " ".join(code)
    return f"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="color-scheme" content="light" />
<meta name="supported-color-schemes" content="light" />
<title>Your bluntly verification code</title>
</head>
<body style="margin:0; padding:0; background-color:{_SURFACE};">

<!-- Preheader: the preview line in the inbox list. Hidden in the body itself. -->
<div style="display:none; font-size:1px; color:{_SURFACE}; line-height:1px;
            max-height:0; max-width:0; opacity:0; overflow:hidden;">
  Your code is {code}. It expires in {ttl_minutes} minutes.
</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:{_SURFACE};">
  <tr>
    <td align="center" style="padding:32px 16px;">

      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
             style="width:600px; max-width:100%; border-collapse:collapse;">

        <!-- Brand band. Solid colour first so gradient-blind clients still get orange. -->
        <tr>
          <td align="center"
              style="background-color:{_ORANGE};
                     background-image:{_BRAND_GRADIENT};
                     border-radius:20px 20px 0 0; padding:34px 32px;">
            <!-- The real wordmark (white PNG) on the orange band. `alt` carries
                 the brand for the ~half of inboxes that block remote images. -->
            <img src="{_LOGO_URL}" alt="bluntly" width="132" height="41"
                 style="display:block; width:132px; height:41px; border:0;
                        margin:0 auto; outline:none; text-decoration:none;" />
          </td>
        </tr>

        <!-- Code card -->
        <tr>
          <td style="background-color:{_WHITE}; padding:40px 32px 32px;">
            <p style="margin:0 0 8px; font-family:{_FONT}; font-size:20px;
                      font-weight:600; color:{_INK};">Verify it&rsquo;s really you</p>
            <p style="margin:0 0 28px; font-family:{_FONT}; font-size:14px;
                      line-height:22px; color:{_MUTED};">
              Enter this code in the app to finish signing in.
            </p>

            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td align="center"
                    style="background-color:{_SURFACE}; border-radius:12px; padding:24px 16px;">
                  <span style="font-family:{_FONT}; font-size:34px; font-weight:700;
                               letter-spacing:10px; color:{_INK};
                               mso-line-height-rule:exactly; line-height:40px;">{spaced_code}</span>
                </td>
              </tr>
            </table>

            <p style="margin:24px 0 0; font-family:{_FONT}; font-size:13px;
                      line-height:20px; color:{_MUTED};">
              This code expires in <strong style="color:{_INK};">{ttl_minutes} minutes</strong>
              and can only be used once.
            </p>
            <p style="margin:12px 0 0; font-family:{_FONT}; font-size:13px;
                      line-height:20px; color:{_MUTED};">
              Didn&rsquo;t request it? You can ignore this email — nobody can get
              into your account without the code.
            </p>
          </td>
        </tr>

        <!-- Why we exist. Short, and in the product's own voice. -->
        <tr>
          <td style="background-color:{_WHITE}; padding:0 32px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td style="border-top:1px solid rgba(32,32,32,0.10); padding-top:24px;">
                <p style="margin:0 0 6px; font-family:{_FONT}; font-size:15px;
                          font-weight:600; color:{_INK};">
                  Honest reviews. Real Payouts.
                </p>
                <p style="margin:0; font-family:{_FONT}; font-size:13px;
                          line-height:20px; color:{_MUTED};">
                  Filipinos making smarter purchases — and reviewers earning a
                  commission when their honest write-up drives a sale.
                </p>
              </td></tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td align="center"
              style="background-color:{_INK}; border-radius:0 0 20px 20px; padding:24px 32px;">
            <p style="margin:0 0 6px; font-family:{_FONT}; font-size:13px;
                      font-weight:600; color:{_SURFACE};">bluntly.ph</p>
            <p style="margin:0; font-family:{_FONT}; font-size:11px;
                      line-height:18px; color:rgba(242,242,242,0.62);">
              No sponsorships. No bias. Ever.
            </p>
          </td>
        </tr>

        <tr>
          <td align="center" style="padding:20px 16px 0;">
            <p style="margin:0; font-family:{_FONT}; font-size:11px;
                      line-height:18px; color:{_MUTED};">
              You received this because someone asked for a sign-in code for this
              address. This is a one-off security message, not a newsletter.
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


# --- Shared layout (2026-10-04) ---------------------------------------------------
#
# Every message after the sign-in code is built from the same frame: the orange band
# with the wordmark, a white card, the dark footer and a footnote saying why the
# person received it. Content is escaped here, once: callers pass plain text (and
# `code_block` / `button` pieces built by the helpers below), never raw HTML from
# members, so a review title or a store name cannot inject markup into an email.

from html import escape as _escape  # noqa: E402


def paragraph(text: str, *, muted: bool = False) -> str:
    color = _MUTED if muted else _INK
    size = "13px" if muted else "14px"
    return (f'<p style="margin:0 0 14px; font-family:{_FONT}; font-size:{size}; '
            f'line-height:22px; color:{color};">{_escape(text)}</p>')


def code_block(code: str) -> str:
    spaced = " ".join(code)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:8px 0 22px;"><tr>'
        f'<td align="center" style="background-color:{_SURFACE}; border-radius:12px; '
        'padding:24px 16px;">'
        f'<span style="font-family:{_FONT}; font-size:34px; font-weight:700; '
        f'letter-spacing:10px; color:{_INK}; line-height:40px;">{_escape(spaced)}</span>'
        '</td></tr></table>')


def button(label: str, href: str) -> str:
    """A link styled as the brand button. `href` must be an absolute https URL we built."""
    if not href.startswith("https://"):
        raise ValueError("email buttons link only to absolute https URLs")
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:8px 0 22px;"><tr>'
        f'<td style="background-color:{_ORANGE}; border-radius:999px;">'
        f'<a href="{_escape(href, quote=True)}" style="display:inline-block; padding:12px 22px; '
        f'font-family:{_FONT}; font-size:14px; font-weight:600; color:{_WHITE}; '
        f'text-decoration:none;">{_escape(label)}</a></td></tr></table>')


def rows(items: list[tuple[str, str]]) -> str:
    """Label / value lines (the weekly summary's figures)."""
    out = ['<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
           'border="0" style="margin:4px 0 18px;">']
    for label, value in items:
        out.append(
            '<tr>'
            f'<td style="padding:8px 0; border-bottom:1px solid rgba(32,32,32,0.10); '
            f'font-family:{_FONT}; font-size:14px; color:{_MUTED};">{_escape(label)}</td>'
            f'<td align="right" style="padding:8px 0; border-bottom:1px solid '
            f'rgba(32,32,32,0.10); font-family:{_FONT}; font-size:14px; font-weight:600; '
            f'color:{_INK};">{_escape(value)}</td></tr>')
    out.append("</table>")
    return "".join(out)


def layout_html(*, title: str, preheader: str, heading: str, body: str, footnote: str) -> str:
    """The branded frame. `body` is built only from the helpers above (already escaped)."""
    return f"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="color-scheme" content="light" />
<meta name="supported-color-schemes" content="light" />
<title>{_escape(title)}</title>
</head>
<body style="margin:0; padding:0; background-color:{_SURFACE};">
<div style="display:none; font-size:1px; color:{_SURFACE}; line-height:1px;
            max-height:0; max-width:0; opacity:0; overflow:hidden;">{_escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:{_SURFACE};">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
             style="width:600px; max-width:100%; border-collapse:collapse;">
        <tr>
          <td align="center"
              style="background-color:{_ORANGE}; background-image:{_BRAND_GRADIENT};
                     border-radius:20px 20px 0 0; padding:34px 32px;">
            <img src="{_LOGO_URL}" alt="bluntly" width="132" height="41"
                 style="display:block; width:132px; height:41px; border:0;
                        margin:0 auto; outline:none; text-decoration:none;" />
          </td>
        </tr>
        <tr>
          <td style="background-color:{_WHITE}; padding:36px 32px 22px;">
            <p style="margin:0 0 14px; font-family:{_FONT}; font-size:20px;
                      font-weight:600; color:{_INK};">{_escape(heading)}</p>
            {body}
          </td>
        </tr>
        <tr>
          <td align="center"
              style="background-color:{_INK}; border-radius:0 0 20px 20px; padding:24px 32px;">
            <p style="margin:0 0 6px; font-family:{_FONT}; font-size:13px;
                      font-weight:600; color:{_SURFACE};">bluntly.ph</p>
            <p style="margin:0; font-family:{_FONT}; font-size:11px;
                      line-height:18px; color:rgba(242,242,242,0.62);">
              Honest reviews. Real Payouts. No sponsorships. No bias. Ever.
            </p>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:20px 16px 0;">
            <p style="margin:0; font-family:{_FONT}; font-size:11px;
                      line-height:18px; color:{_MUTED};">{_escape(footnote)}</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


def mask_email(email: str) -> str:
    """"m•••@gmail.com": enough to recognise an address, not enough to harvest it."""
    user, _, domain = email.partition("@")
    return f"{user[:1]}•••@{domain}" if domain else "•••"


def email_change_code(*, code: str, ttl_minutes: int, to_new: bool,
                      new_email: str) -> tuple[str, str, str]:
    """(subject, text, html) for one of the two codes of an email change."""
    if to_new:
        subject = f"{code} confirms your new bluntly sign-in email"
        lead = ("Someone signed in to bluntly asked to use this address to sign in. "
                "If that was you, enter this code in the app. It proves you own this inbox.")
        footnote = ("You received this because this address was entered as a new sign-in "
                    "email on bluntly.ph. If it wasn't you, ignore it: nothing changes.")
    else:
        subject = f"{code} — confirm changing your bluntly sign-in email"
        lead = (f"You asked to change the address you sign in with to {mask_email(new_email)}. "
                "Enter this code in the app, with the one sent to the new address.")
        footnote = ("You received this because someone asked to change this account's "
                    "sign-in email. If it wasn't you, ignore it and nothing changes; "
                    "consider changing your password.")
    text = (f"{lead}\n\nYour code: {code}\n\nIt expires in {ttl_minutes} minutes and works "
            f"once.\n\n{footnote}\n\n---\nbluntly.ph — Honest reviews. Real Payouts.\n")
    html = layout_html(
        title=subject, preheader=f"Your code is {code}. It expires in {ttl_minutes} minutes.",
        heading="Confirm the new address" if to_new else "Confirm it's you",
        body=paragraph(lead) + code_block(code)
        + paragraph(f"It expires in {ttl_minutes} minutes and works once.", muted=True),
        footnote=footnote)
    return subject, text, html


def email_changed_notice(*, new_email: str, support_url: str) -> tuple[str, str, str]:
    """(subject, text, html) sent to the OLD address once the change is done."""
    subject = "Your bluntly sign-in email was changed"
    lead = (f"The address you sign in with to bluntly is now {mask_email(new_email)}. "
            "Every other signed-in browser was signed out.")
    warn = ("If you didn't do this, contact us right away: reply to this email or write to "
            "the Bluntly team from the site.")
    text = f"{lead}\n\n{warn}\n{support_url}\n\n---\nbluntly.ph\n"
    html = layout_html(
        title=subject, preheader=f"Now {mask_email(new_email)}.", heading="Sign-in email changed",
        body=paragraph(lead) + paragraph(warn)
        + (button("Contact the Bluntly team", support_url)
           if support_url.startswith("https://") else ""),
        footnote="A security notice about your account. It is sent once, for this change.")
    return subject, text, html


def notification_email(*, title: str, body: str | None, open_url: str | None,
                       settings_url: str, unsubscribe_url: str) -> tuple[str, str, str]:
    """(subject, text, html) for one store notice ("New 2★ review", "New question").

    The title is the in-app notice's own title, so the email and the bell say the
    same thing. Store names, buyer names and excerpts arrive escaped by the layout."""
    subject = title[:200]
    parts = [paragraph(body)] if body else []
    if open_url and open_url.startswith("https://"):
        parts.append(button("Open in bluntly", open_url))
    footnote = ("You get this because email is on for store notices. Turn it off in "
                f"Settings ({settings_url}) or unsubscribe: {unsubscribe_url}")
    text = (f"{title}\n\n" + (f"{body}\n\n" if body else "")
            + (f"Open: {open_url}\n\n" if open_url else "")
            + f"---\n{footnote}\n")
    html = layout_html(title=subject, preheader=body or title, heading=title,
                       body="".join(parts), footnote=footnote)
    return subject, text, html


def weekly_summary_email(*, store: str, week: str, figures: list[tuple[str, str]],
                         waiting_line: str, open_url: str, unsubscribe_url: str
                         ) -> tuple[str, str, str]:
    """(subject, text, html) for the Monday summary (Figma Settings "Weekly summary":
    rating, new reviews and what's waiting)."""
    subject = f"Your week on bluntly: {store}"[:200]
    footnote = ("You get this every Monday because the weekly summary is on in your store "
                f"Settings. Unsubscribe: {unsubscribe_url}")
    text = (f"{store} — week of {week}\n\n"
            + "".join(f"{label}: {value}\n" for label, value in figures)
            + f"\n{waiting_line}\n\nOpen your console: {open_url}\n\n---\n{footnote}\n")
    body = paragraph(f"Week of {week}.", muted=True) + rows(figures) + paragraph(waiting_line)
    if open_url.startswith("https://"):
        body += button("Open your store console", open_url)
    html = layout_html(title=subject, preheader=waiting_line, heading=store, body=body,
                       footnote=footnote)
    return subject, text, html
