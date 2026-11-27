# Financial report PDF assets

Used only by `app/services/reporting/financial_pdf.py` (Reports → Generate report).

| File | What | Source / licence |
|---|---|---|
| `Poppins-{Regular,Medium,SemiBold}.ttf` | The site's typeface, Latin + Latin Extended | Google Fonts (fonts.gstatic.com, v24). SIL OFL 1.1, `OFL-Poppins.txt` |
| `DejaVuSans-Peso.ttf` | One glyph, ₱ (U+20B1): Poppins has none, so the PDF draws the peso sign in this | DejaVu Sans subset with fontTools (`pyftsubset --unicodes=U+20B1`). `LICENSE-DejaVu.txt` |
| `bluntly-wordmark.png` | The `bluntly` wordmark with the swoosh, brand orange (#EF5821) | `public/bluntly-logo.png` recoloured (its alpha kept); owner's artwork |

The meeting of 2026-10-02 (18:06) asked for the Bluntly swoosh in place of the Figma
template's placeholder "b" tile; the wordmark is that logo.
