"""The defense dataset: who, what and when. Content only; `seed` does the writing.

A small Filipino consumer-review community, eight months old, centred on the
PRD's pilot category (power banks, earphones, fans, chargers) with enough of
everything else to show categories, both marketplaces, both earning tracks,
moderation and money moving. Every person and store here is fictional. The
products are real, with images from each manufacturer's own site and, where
the owner has one, the real affiliate link the showcase seed already vetted.

Rules the content keeps, so the gibberish sweep in `verify` stays empty:
  * no "test", "sample", "dummy", "placeholder" or lorem text anywhere visible;
  * no real person's name, and no store name that belongs to a real business;
  * prices, dates and ratings agree with each other (a price paid appears in
    the product's price history; nobody reviews before they joined);
  * no 2.5-star "it depends" review - that earning rule is still the owner's.

Time is expressed as days before the seed runs, so a re-seed stays coherent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# ---------------------------------------------------------------- people


@dataclass(frozen=True)
class Person:
    key: str
    username: str
    display_name: str
    joined_days_ago: int
    interests: tuple[str, ...]
    role: str = "user"
    #: Personas the team signs in as. Their email is a "+" alias of the
    #: defense inbox, so the one-time codes arrive where the team can read them.
    login: bool = False


#: The accounts a presenter signs in as (docs/DEFENSE_DATA_MANIFEST.md).
PERSONAS: tuple[Person, ...] = (
    Person("maria", "mariareyes", "Maria Reyes", 210,
           ("electronics-tech", "home-living", "beauty"), login=True),
    Person("paolo", "paolo_mendoza", "Paolo Mendoza", 6,
           ("electronics-tech", "sports-outdoors"), login=True),
    Person("kristine", "kristinev", "Kristine Villanueva", 235,
           ("audio", "electronics-tech", "gaming"), login=True),
    Person("rico", "rico_powerhub", "Rico Tan", 180,
           ("electronics-tech",), login=True),
    Person("administrator", "admin_joanna", "Joanna Lim", 240,
           ("electronics-tech",), role="administrator", login=True),
    # The deterministic TEST Super Admin (owner decision D): user management
    # and the 2.5-star routing queue. A TEST persona only — production's first
    # Super Admin is bootstrapped by the owner (scripts/bootstrap_super_admin.py).
    Person("superadmin", "super_andrea", "Andrea Santos", 260,
           ("electronics-tech",), role="super_admin", login=True),
    Person("jomar", "jomar_deals", "Jomar Aquino", 150,
           ("electronics-tech",), login=True),
)

#: Everyone else: the community whose reviews, votes and answers fill the site.
#: Emails live on the defense subdomain, which receives no mail; these
#: accounts are never signed into.
COMMUNITY: tuple[Person, ...] = (
    Person("jaymie", "jaymie_santos", "Jaymie Santos", 228,
           ("office-productivity", "electronics-tech")),
    Person("renz", "renz_delacruz", "Renz Dela Cruz", 224, ("electronics-tech", "gaming")),
    Person("bea", "bea_gonzales", "Bea Gonzales", 219, ("beauty", "electronics-tech")),
    Person("miguel", "miguel_ramos", "Miguel Ramos", 216, ("audio", "sports-outdoors")),
    Person("trisha", "trisha_navarro", "Trisha Navarro", 212, ("electronics-tech", "home-living")),
    Person("ken", "ken_bautista", "Ken Bautista", 205, ("electronics-tech",)),
    Person("aira", "aira_castillo", "Aira Castillo", 201, ("electronics-tech", "beauty")),
    Person("joshua", "joshua_lim", "Joshua Lim", 197, ("audio", "electronics-tech")),
    Person("camille", "camille_torres", "Camille Torres", 193, ("electronics-tech", "home-living")),
    Person("nico", "nico_ramos", "Nico Ramos", 188, ("electronics-tech",)),
    Person("patrice", "patrice_uy", "Patrice Uy", 184, ("electronics-tech", "audio")),
    Person("dennis", "dennis_ocampo", "Dennis Ocampo", 179, ("home-living", "electronics-tech")),
    Person("lara", "lara_fernandez", "Lara Fernandez", 174, ("audio", "beauty")),
    Person("vince", "vince_aguilar", "Vince Aguilar", 170,
           ("electronics-tech", "office-productivity")),
    Person("hazel", "hazel_domingo", "Hazel Domingo", 166, ("audio", "home-living")),
    Person("mark", "mark_soriano", "Mark Soriano", 161, ("electronics-tech",)),
    Person("rina", "rina_manalo", "Rina Manalo", 157, ("office-productivity", "electronics-tech")),
    Person("gio", "gio_salazar", "Gio Salazar", 152, ("electronics-tech", "gaming")),
    Person("steph", "steph_rivera", "Steph Rivera", 148, ("electronics-tech", "beauty")),
    Person("ella", "ella_morales", "Ella Morales", 143, ("office-productivity",)),
    Person("raf", "raf_villareal", "Raf Villareal", 139, ("sports-outdoors", "electronics-tech")),
    Person("joan", "joan_pascual", "Joan Pascual", 134,
           ("electronics-tech", "office-productivity")),
    Person("ivan", "ivan_dizon", "Ivan Dizon", 130, ("sports-outdoors", "electronics-tech")),
    Person("carla", "carla_mercado", "Carla Mercado", 126, ("gaming", "electronics-tech")),
    Person("amiel", "amiel_sy", "Amiel Sy", 121, ("gaming",)),
    Person("kathleen", "kathleen_go", "Kathleen Go", 117, ("gaming", "beauty")),
)

PEOPLE: dict[str, Person] = {p.key: p for p in (*PERSONAS, *COMMUNITY)}

#: The five accounts that voted on every one of Jomar's reviews (§11 ADR-016:
#: a repeating cohort holds promotion for a moderator). They look ordinary on
#: their own - that is the point of detecting the pattern.
RING: tuple[str, ...] = ("gio", "raf", "amiel", "ivan", "kathleen")

# ---------------------------------------------------------------- stores


@dataclass(frozen=True)
class Store:
    key: str
    name: str
    platform: str
    #: 'approved' (owned by `owner`), 'pending' (claimed by `owner`, awaiting a
    #: moderator), or None (unclaimed).
    claim: str | None = None
    owner: str | None = None
    registration_number: str | None = None
    registered_business_name: str | None = None
    added_by: str = "trisha"


STORES: tuple[Store, ...] = (
    Store("powerhub", "PowerHub PH", "shopee", claim="approved", owner="rico",
          registration_number="DTI-3318207", registered_business_name="PowerHub Trading",
          added_by="maria"),
    Store("galaxy", "Gadget Galaxy Manila", "lazada", added_by="ivan"),
    Store("cebuhub", "Cebu Gadget Hub", "shopee", claim="pending", owner="nico",
          registration_number="DTI-5902144", registered_business_name="Ramos Gadget Trading",
          added_by="nico"),
    Store("tahanan", "Tahanan Home Finds", "lazada", added_by="dennis"),
    Store("glowup", "GlowUp Skin Hub", "shopee", added_by="bea"),
)

# ---------------------------------------------------------------- products


@dataclass(frozen=True)
class ProductSpec:
    key: str
    #: What the first reviewer typed when they submitted it (pending), before a
    #: moderator gave it its canonical name.
    submitted_name: str
    submitter: str
    brand: str
    line: str
    key_spec: str | None
    descriptor: str | None
    category: str
    #: Official manufacturer image (downloaded and re-hosted by the seed).
    image_url: str
    #: The manufacturer page it came from, recorded for provenance.
    image_page: str
    shopee_url: str | None = None
    lazada_url: str | None = None
    aliases: tuple[str, ...] = ()


# Real affiliate links, verbatim from scripts/seed_showcase.py where the owner
# resolved each one to its listing on 2026-09-10. A product without one is
# seeded without one: a buy button that leads nowhere is QA-006.
PRODUCTS: tuple[ProductSpec, ...] = (
    ProductSpec(
        "anker_737", "anker 737 powercore 24k", "maria",
        "Anker", "737 Power Bank", "24,000mAh, 140W", "PowerCore 24K", "electronics-tech",
        "https://cdn.shopify.com/s/files/1/0493/9834/9974/products/A1289011-Anker_737_Power_Bank_PowerCore_24K_1.png?v=1775967275",
        "https://www.anker.com/products/a1289",
        aliases=("powercore 24k", "anker 737", "anker 24000")),
    ProductSpec(
        "anker_nano_10k", "Anker Nano power bank 10000 30W with cable", "kristine",
        "Anker", "Nano Power Bank", "10,000mAh, 30W", "Built-in USB-C cable", "electronics-tech",
        "https://cdn.shopify.com/s/files/1/0493/9834/9974/files/5_a7a61bbb-8693-46f2-8d44-de814496fc62.png?v=1764230004",
        "https://www.anker.com/products/a1259-built-in-cable-power-bank-10000mah",
        aliases=("anker nano", "anker nano powerbank", "anker 10000")),
    ProductSpec(
        "jisulife_life9", "jisulife handheld fan life 9", "maria",
        "Jisulife", "Life9 Handheld Fan", "4,800mAh", None, "electronics-tech",
        "https://jisulife.com/cdn/shop/files/grey-handheld_fan-FHL09R.webp?v=1781511860&width=2048",
        "https://jisulife.com/products/jisulife-handheld-fan-9",
        aliases=("jisulife", "jisulife fan", "life9 fan", "mini fan")),
    ProductSpec(
        "soundcore_p20i", "soundcore p20i earbuds", "kristine",
        "Soundcore", "P20i", None, "True Wireless Earbuds", "audio",
        "https://cdn.shopify.com/s/files/1/0516/3761/6830/files/20260304-121406.png?v=1772597724",
        "https://www.soundcore.com/products/p20i",
        aliases=("p20i", "soundcore budget earbuds")),
    ProductSpec(
        "soundcore_liberty4nc", "Soundcore Liberty 4 NC", "kristine",
        "Soundcore", "Liberty 4 NC", None, "Noise-Cancelling Earbuds", "audio",
        "https://cdn.shopify.com/s/files/1/0516/3761/6830/files/A3947Z11_4088025e-9f6e-4ec4-ad98-69d8d7dbf357.png?v=1749638576",
        "https://www.soundcore.com/products/liberty-4-nc-a3947z11",
        aliases=("liberty 4nc", "l4nc", "soundcore anc")),
    ProductSpec(
        "ugreen_nexode_65w", "ugreen nexode 65w gan charger 3 port", "kristine",
        "UGREEN", "Nexode Charger", "65W", "3-Port GaN", "electronics-tech",
        "https://cdn.shopify.com/s/files/1/0257/5246/9566/products/ugreen-nexode-65w-usb-c-gan-charger-3-ports-wall-charger-276386.png?v=1764234605",
        "https://us.ugreen.com/products/65w-3-ports-gan-fast-charger",
        aliases=("ugreen 65w", "gan charger", "nexode")),
    ProductSpec(
        "iphone_17", "iPhone 17", "maria",
        "Apple", "iPhone 17", None, None, "electronics-tech",
        "https://www.apple.com/v/iphone-17/i/images/meta/iphone-17_overview__cg0rlzmbhl7m_og.png?202609231324",
        "https://www.apple.com/iphone-17/",
        shopee_url="https://s.shopee.ph/7AdQOJz8uS",
        aliases=("iphone17", "ip17")),
    ProductSpec(
        "ipad_11_a16", "ipad 11th gen a16 wifi", "rina",
        "Apple", "iPad", "11th Gen, A16", "Wi-Fi", "electronics-tech",
        "https://www.apple.com/v/ipad-11/d/images/meta/ipad-11_overview__brh97xhhd8b6_og.png?202608111253",
        "https://www.apple.com/ipad-11/",
        shopee_url="https://s.shopee.ph/70K0C1GTxw",
        aliases=("ipad a16", "ipad 11")),
    ProductSpec(
        "dji_osmo_action6", "DJI osmo action 6", "jomar",
        "DJI", "Osmo Action 6", None, "Action Camera", "electronics-tech",
        "https://www-cdn.djiits.com/cms/uploads/ae781cd30b6dc794eb49ad3d44e26845@374*374.png",
        "https://www.dji.com/osmo-action-6",
        shopee_url="https://s.shopee.ph/7pt7BWX1Ta",
        aliases=("osmo action 6", "dji action cam")),
    ProductSpec(
        "steam_deck_oled", "steam deck oled 512gb", "kristine",
        "Valve", "Steam Deck OLED", None, "Handheld Console", "gaming",
        "https://cdn.fastly.steamstatic.com/steamdeck/images/oled/social_media_image.jpg",
        "https://www.steamdeck.com/en/oled",
        lazada_url="https://s.lazada.com.ph/s.ZSIokl?c=t&t=p-i4dE7F3-sPq9a3M",
        aliases=("steamdeck", "steam deck")),
    ProductSpec(
        "ps5_digital", "ps5 digital edition", "kristine",
        "Sony", "PlayStation 5", None, "Digital Edition", "gaming",
        "https://gmedia.playstation.com/is/image/SIEPDC/ps5-product-thumbnail-01-en-14sep21?$facebook$",
        "https://www.playstation.com/en-ph/ps5/",
        lazada_url="https://s.lazada.com.ph/s.ZSIooE?c=q&t=p-i513gmy-s2LOIzFD",
        aliases=("ps5", "playstation 5 digital")),
    ProductSpec(
        "akko_5075b", "akko 5075b plus keyboard", "kristine",
        "Akko", "5075B Plus", None, "Mechanical Keyboard", "office-productivity",
        "https://en.akkogear.com/wp-content/uploads/2023/07/BlackSilver-5075B-Plus.png",
        "https://en.akkogear.com/product/blacksilver-5075b-plus-mechanical-keyboard/",
        aliases=("akko 5075", "akko keyboard")),
    ProductSpec(
        "macbook_air_m2", "macbook air m2 13 inch", "kristine",
        "Apple", "MacBook Air", "M2, 13-inch", None, "electronics-tech",
        "https://www.apple.com/newsroom/images/product/mac/standard/Apple-WWDC22-MacBook-Air-lp-220606.jpg.og.jpg?202608191700",
        "https://www.apple.com/newsroom/2022/06/apple-unveils-all-new-macbook-air-supercharged-by-the-new-m2-chip/",
        aliases=("mba m2", "macbook air")),
    ProductSpec(
        "cerave_foaming", "cerave foaming cleanser 473ml", "maria",
        "CeraVe", "Foaming Facial Cleanser", "473mL", "Normal to Oily Skin", "beauty",
        "https://www.cerave.com/-/media/project/loreal/brand-sites/cerave/americas/us/skincare/cleansers/foaming-facial-cleanser/photos/2026/700x785/ffc-atf-1-700x785-v1.jpg?rev=f0923e1e888a44b5ac66d4bb8025218a",
        "https://www.cerave.com/skincare/cleansers/foaming-facial-cleanser",
        aliases=("cerave", "cerave foaming")),
    ProductSpec(
        "uratex_classic", "uratex classic foam 6 inches", "maria",
        "Uratex", "Classic Mattress", "6 inches", "Tricot Cover", "home-living",
        "https://cdn.shopify.com/s/files/1/0505/8897/5259/files/UratexTricot_TealGray.jpg?v=1749545769",
        "https://uratex.com.ph/products/uratex-polycotton",
        shopee_url="https://s.shopee.ph/2gB11yLwBg",
        aliases=("uratex foam", "uratex mattress")),
)

PRODUCT: dict[str, ProductSpec] = {p.key: p for p in PRODUCTS}

#: Submitted by reviewers and still waiting for a moderator, so the defense can
#: show a submission being canonicalized and a duplicate being attached.
PENDING_SUBMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    # (key, submitter, name as typed, category)
    ("xiaomi_pb_20k", "camille", "xiaomi power bank 20000mah 22.5w", "electronics-tech"),
    ("dup_anker_nano", "hazel", "anker nano powerbank 10k w/ built in cable", "electronics-tech"),
)

#: Where readers open reviews from, for the moderator's traffic geography:
#: (region, city, latitude, longitude, relative weight).
READER_CITIES: tuple[tuple[str, str, float, float, int], ...] = (
    ("Metro Manila", "Quezon City", 14.676, 121.044, 9),
    ("Metro Manila", "Manila", 14.599, 120.984, 7),
    ("Metro Manila", "Makati", 14.555, 121.024, 5),
    ("Metro Manila", "Pasig", 14.576, 121.085, 4),
    ("Metro Manila", "Taguig", 14.517, 121.051, 4),
    ("Calabarzon", "Bacoor", 14.459, 120.936, 3),
    ("Calabarzon", "Antipolo", 14.586, 121.176, 2),
    ("Central Luzon", "Angeles", 15.145, 120.588, 2),
    ("Central Visayas", "Cebu City", 10.316, 123.885, 5),
    ("Western Visayas", "Iloilo City", 10.720, 122.562, 2),
    ("Davao Region", "Davao City", 7.190, 125.455, 4),
    ("Northern Mindanao", "Cagayan de Oro", 8.454, 124.632, 2),
    ("Cordillera Administrative Region", "Baguio", 16.402, 120.596, 1),
)

# ---------------------------------------------------------------- reviews


@dataclass(frozen=True)
class UpdateSpec:
    """A later entry in the review's thread (Business Rules: every 3 months)."""
    days_ago: int
    title: str
    verdict: str
    stars: float
    discussion: str
    pros: tuple[str, ...] = ()
    cons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewSpec:
    key: str
    author: str
    product: str
    days_ago: int
    title: str
    verdict: str
    stars: float
    explanation: str
    target: str
    anti: str
    discussion: str
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    price: str | None
    platform: str | None
    #: A proof photo makes the review verified (and able to earn).
    photo: bool = True
    #: What the moderator decided, and so the earning state the page shows:
    #:   monetized    - approved with the product's real affiliate link
    #:   approved     - earnings approved, no link (>=3 stars)
    #:   honesty_fund - earnings approved on the fund track (<=2 stars)
    #:   rejected     - earnings refused with `reject_reason` (stays public)
    #:   pending      - verified, and helpful enough to trusted readers that the
    #:                  community gate queues it for a moderator (Post-Seeding,
    #:                  the owner's rule of 2026-09-22); `seed` keeps casting real
    #:                  up-votes until the gate itself admits it
    #:   None         - unverified: publishes, never earns
    decision: str | None = "approved"
    reject_reason: str | None = None
    ups: int = 4
    downs: int = 0
    update: UpdateSpec | None = None
    #: Removed by its own author afterwards (the aggregate must forget it).
    author_deletes: bool = False


REVIEWS: tuple[ReviewSpec, ...] = (
    # ---- Maria: established reviewer, both earning tracks, one update --------
    ReviewSpec(
        "m_uratex", "maria", "uratex_classic", 170,
        "Firm, no-nonsense foam for a small spare room", "it_depends", 4,
        "It depends on how you sleep: back and stomach sleepers will like the support, "
        "side sleepers may find it too hard.",
        "Back sleepers, spare rooms, dorms and first apartments on a budget.",
        "Side sleepers or anyone who wants a plush, sink-in feel.",
        "Bought the 6-inch single for my son's room when he moved into our spare room in "
        "Quezon City. It's firm - really firm for the first two weeks - then it settles into "
        "something his back actually likes. The tricot cover looks nicer than expected and "
        "wipes clean, but it's thin, so I added a mattress protector after the first spill. "
        "It arrived roll-packed after four days and needed a full day to expand, so don't "
        "sleep on it the same night. Honest value for the price, just don't expect hotel "
        "softness.",
        ("Firm, even support", "Cover wipes clean", "Light enough for one person to move"),
        ("Thin cover, so budget for a protector", "Needs a full day to expand"),
        "3850", "shopee", decision="monetized", ups=6, downs=1),
    ReviewSpec(
        "m_anker737", "maria", "anker_737", 150,
        "Anker 737: the brick that got us through brownouts", "yes_absolutely", 5,
        "If you need real backup power at home or on trips, it's worth every peso.",
        "Families dealing with brownouts, travellers, laptop users.",
        "Anyone who wants something light for a pocket or a small sling bag.",
        "We get two- to three-hour brownouts in our barangay every summer, so I finally "
        "bought a proper power bank. The 737 charges my phone from 10% to full about four "
        "times, and it kept our small USB fan running through a whole outage. The display "
        "that shows watts and the remaining percentage is honestly the feature I use most - "
        "you always know how much is left. It's heavy, around 630 grams, so it lives at home "
        "rather than in my bag. Refilling it with a 65W charger takes a little over two hours.",
        ("Charges a laptop at full speed", "Accurate percentage and wattage display",
         "About four full phone charges"),
        ("Heavy, not for pockets", "Needs a strong charger to refill quickly"),
        "4799", "shopee", decision="approved", ups=9, downs=1,
        update=UpdateSpec(
            32, "Five months later: still our brownout hero", "yes_absolutely", 4.5,
            "Update after five months of weekly use: capacity still feels the same, around "
            "four phone charges. The only wear is a small scratch on the display. I'm taking "
            "off half a star because the included cable frayed near the connector after four "
            "months; I replaced it with a UGREEN cable. The power bank itself, zero complaints.",
            ("Capacity hasn't dropped",), ("Included cable frayed after four months",))),
    ReviewSpec(
        "m_jisulife", "maria", "jisulife_life9", 95,
        "A pocket fan that actually survives the MRT", "yes_absolutely", 4,
        "Yes, if you commute or work somewhere without aircon.",
        "Commuters, students, anyone who waits in long lines outdoors.",
        "People who need silence - the top speed is noisy.",
        "Commuting from Cubao to Makati in May is its own endurance sport, so I bought the "
        "Life9 after seeing it everywhere. On speed 2 it lasts my whole round trip with "
        "battery to spare, and the airflow dries sweat in a few minutes. Speed 4 is powerful "
        "but loud; people on the train will look. The strap and the little stand are useful "
        "when I'm working at my desk at home. My only gripe is the USB-C port cover, which "
        "feels flimsy.",
        ("Strong airflow for its size", "Battery lasts a full commute", "Works as a desk fan"),
        ("Loud on the highest speed", "Port cover feels flimsy"),
        "849", "shopee", decision="pending", ups=5),
    ReviewSpec(
        "m_cerave", "maria", "cerave_foaming", 60,
        "Great for oily skin, rough on my dry cheeks", "hard_pass", 2,
        "Hard pass for dry or combination skin like mine; fine if you're truly oily.",
        "People with genuinely oily skin in humid weather.",
        "Dry or combination skin - the hydrating version is the better pick.",
        "Everyone recommends this, so I used it for six weeks. My T-zone loved it: less shine "
        "by lunchtime. But my cheeks are dry, and after the second week they felt tight and "
        "flaky even with moisturiser right after washing. I switched back to a hydrating "
        "cleanser and the flakiness went away within days. It's a good product for the right "
        "skin; it just wasn't mine, and I think the hype makes people buy it without checking "
        "their skin type first.",
        ("Controls oil well", "Fragrance-free", "Big bottle lasts months"),
        ("Tight, flaky feeling on dry areas", "Easy to buy on hype alone"),
        "1299", "shopee", decision="honesty_fund", ups=8),
    ReviewSpec(
        "m_iphone17", "maria", "iphone_17", 40,
        "iPhone 17 after a month: the battery finally keeps up", "yes_absolutely", 5,
        "Yes if your phone is three or more years old; skip it if you have a 15 or 16.",
        "Anyone upgrading from an older iPhone.",
        "Owners of an iPhone 15 or 16 - the jump is small.",
        "I upgraded from an iPhone 12 that couldn't make it past 3 p.m. anymore. The 17 ends "
        "my day with 30 to 40 percent left, even with Waze, Grab and a lot of photos of my "
        "kids. The 120Hz screen was the surprise; scrolling feels smoother than I expected to "
        "care about. The camera is great in daylight, and indoor party shots are better than "
        "my old phone's but not magic. I bought it during a Shopee sale with vouchers, and "
        "the unit was the PH version with local warranty.",
        ("All-day battery", "Smooth 120Hz display", "Reliable daytime camera"),
        ("Still pricey even on sale", "No charger in the box"),
        "58990", "shopee", decision="monetized", ups=7),

    # ---- Kristine: advanced reviewer, reaches Stage 3 on real evidence -------
    ReviewSpec(
        "k_liberty4nc", "kristine", "soundcore_liberty4nc", 200,
        "Liberty 4 NC: the noise-cancelling sweet spot under ₱5k", "yes_absolutely", 4.5,
        "Yes, if you want strong noise cancelling without flagship pricing.",
        "Commuters and remote workers who want quiet on a budget.",
        "Listeners who want a neutral sound, or people who dislike touch controls.",
        "I tried three noise-cancelling earbuds before settling on these. The ANC handles "
        "jeepney engines and aircon hum really well - not the best on the market, but close "
        "for half the price. The sound is warm and bassy out of the box; I use the app's "
        "equaliser to pull the bass down a notch. The battery gets me through a full work day "
        "of calls and music. The case is a little bulky and the touch controls take about a "
        "week to learn.",
        ("Strong noise cancelling for the price", "Full-day battery", "Useful app equaliser"),
        ("Bulky case", "Touch controls take getting used to"),
        "4995", "lazada", ups=8),
    ReviewSpec(
        "k_p20i", "kristine", "soundcore_p20i", 185,
        "P20i: great for the price, just don't expect ANC", "it_depends", 4,
        "Worth it as a second pair or for workouts, not as your only commute earbuds.",
        "Students and gym-goers on a tight budget.",
        "Daily commuters who need noise cancelling.",
        "I bought these as my gym and backup pair. For ₱1,199 they sound surprisingly full, "
        "connect fast, and the lanyard case is handy. But there's no noise cancelling, so on "
        "the bus you'll end up turning the volume way up. The mic is fine indoors and weak "
        "outside. They've survived six months of sweaty workouts so far.",
        ("Full sound for ₱1.2k", "Fast pairing", "Survives workouts"),
        ("No noise cancelling", "Mic struggles outdoors"),
        "1199", "shopee", ups=7),
    ReviewSpec(
        "k_ugreen", "kristine", "ugreen_nexode_65w", 160,
        "One charger for my laptop, phone and earbuds", "yes_absolutely", 5,
        "Yes - the best travel upgrade I made this year.",
        "Laptop users who travel or work in cafés.",
        "People who only charge a phone; a 20W charger is enough for that.",
        "This replaced three chargers in my bag. It charges my MacBook Air at full speed on "
        "one port, and when I plug in my phone too, the laptop slows a little but both still "
        "charge quickly. It gets warm, never hot. The folding prongs are a small thing that "
        "matters when it shares a pouch with everything else.",
        ("Charges a laptop and a phone together", "Compact with folding prongs",
         "Warm, never hot"),
        ("Laptop charging slows when all ports are used",),
        "2395", "lazada", ups=6),
    ReviewSpec(
        "k_akko", "kristine", "akko_5075b", 130,
        "My first mechanical keyboard, and I'm not going back", "yes_absolutely", 4.5,
        "Yes for first-time buyers who want a premium feel without the premium price.",
        "Writers, students and office workers new to mechanical keyboards.",
        "People who need a compact 60% board for travel.",
        "The 5075B Plus sounds and feels far more expensive than it is. Typing is soft and "
        "deep thanks to the gasket mount, and switching between my laptop over Bluetooth and "
        "my desktop over the 2.4GHz dongle is one key combination. The battery lasts about "
        "two weeks with the backlight off. The configuration software is clunky and the stock "
        "keycaps are thin, but both are easy to live with.",
        ("Soft, quiet typing feel", "Three connection modes", "Long wireless battery"),
        ("Clunky configuration software", "Thin stock keycaps"),
        "3799", "shopee", ups=6),
    ReviewSpec(
        "k_steamdeck", "kristine", "steam_deck_oled", 110,
        "Steam Deck OLED: my PC library, finally portable", "yes_absolutely", 5,
        "Yes if you already own games on Steam; less so if you mostly play console exclusives.",
        "PC gamers with a Steam library who want to play in bed or on trips.",
        "People who mainly play PlayStation or Nintendo exclusives.",
        "I have a big Steam library I never had time for at my desk. The OLED screen is "
        "gorgeous - dark scenes actually look dark - and battery life is clearly better than "
        "my friends' LCD models: indie games last five hours or more. Heavy recent games "
        "drain it in about two. Setup was easy and most of my games ran without any tweaking. "
        "Get a case; it's a big device.",
        ("Beautiful OLED screen", "Better battery than the LCD model",
         "Most Steam games just work"),
        ("Heavy for long sessions", "Big games drain it fast"),
        "32990", "lazada", decision="monetized", ups=8),
    ReviewSpec(
        "k_macbook", "kristine", "macbook_air_m2", 90,
        "M2 Air in 2026: still great, but mind the 8GB", "it_depends", 4,
        "It depends on your workload: great for students, limiting for heavy multitaskers.",
        "Students and writers who want a light, quiet laptop.",
        "Designers and video editors who need 16GB or more.",
        "I bought a sealed M2 Air at a discount now that newer models are out. It's silent, "
        "light, and the battery easily lasts a workday of documents and browsing. But the "
        "base 8GB of memory shows its age: with many browser tabs plus Figma, it starts to "
        "slow down. For school work and writing it's excellent value at today's price; for "
        "heavier creative work, look for a 16GB unit.",
        ("Silent and light", "All-day battery", "Excellent value at today's prices"),
        ("8GB memory limits heavy multitasking", "Only two ports"),
        "56990", "lazada", ups=6, downs=1),
    ReviewSpec(
        "k_ankernano", "kristine", "anker_nano_10k", 45,
        "Anker Nano 10K: the power bank I actually carry", "it_depends", 4,
        "It depends: perfect for phones and tablets, not a laptop power bank.",
        "Students and commuters who want a light everyday power bank.",
        "Laptop users who need real backup power.",
        "The built-in USB-C cable is the whole point: no more forgetting cables. It's small "
        "enough for a pouch and gives my phone about two full charges. 30W is fast for phones "
        "and fine for topping up a tablet, but don't expect it to charge a laptop - at best it "
        "slows the drain. After six weeks the cable still feels sturdy. If you need laptop "
        "charging, the Anker 737 is the one to get.",
        ("Built-in USB-C cable", "Pocket-friendly size", "About two full phone charges"),
        ("Too weak for laptops", "Gets warm while fast charging"),
        "1899", "shopee", ups=9, downs=1),
    ReviewSpec(
        "k_ps5", "kristine", "ps5_digital", 70,
        "PS5 Digital: fine console, bad deal for how I buy games", "hard_pass", 2,
        "Hard pass if you buy second-hand discs; fine if you only buy digital on sale.",
        "Players who already buy everything digitally.",
        "Anyone who trades or buys used physical games.",
        "The console itself is quiet and fast; no complaints about performance. The problem "
        "is that the Digital Edition locks you into the PlayStation Store, where games here "
        "rarely drop as low as physical copies at local shops or in buy-and-sell groups. "
        "Within four months I had spent more than the price difference on games I could have "
        "bought used. The built-in storage also filled up after five big games.",
        ("Quiet, fast console", "Cheaper upfront than the disc model"),
        ("Digital-only games cost more over time", "Storage fills up quickly"),
        "25990", "lazada", decision="honesty_fund", ups=7),

    # ---- Paolo: brand-new account, first review, no photo --------------------
    ReviewSpec(
        "p_jisulife", "paolo", "jisulife_life9", 2,
        "Okay fan for the price, battery shorter than advertised", "it_depends", 3,
        "Good fan, but the battery claims in the listing are optimistic.",
        "Short commutes and outdoor waiting.",
        "People who need it running all day without charging.",
        "First review ko dito. I bought it last week for my morning jog and commute. Airflow "
        "is good, sobrang lamig on speed 3. But the battery didn't last the whole day like "
        "the listing says - about five hours on speed 2 for me. Still useful, just manage "
        "your expectations.",
        ("Strong airflow", "Light"), ("Battery shorter than advertised",),
        "899", "lazada", photo=False, decision=None, ups=2),

    # ---- Jomar: the account under investigation ------------------------------
    ReviewSpec(
        "j_ankernano", "jomar", "anker_nano_10k", 140,
        "Best power bank ever!", "yes_absolutely", 5,
        "Highly recommended to everyone!", "Everyone.", "None.",
        "Sulit na sulit! Super bilis mag-charge, compact, and the quality is great. Highly "
        "recommended to everyone! Five stars for the product and the seller.",
        ("Fast charging", "Compact"), (), "1799", "shopee", ups=0),
    ReviewSpec(
        "j_ugreen", "jomar", "ugreen_nexode_65w", 125,
        "Super fast charger, sulit!", "yes_absolutely", 5,
        "Highly recommended to everyone!", "Everyone.", "None.",
        "Super bilis mag-charge ng laptop and phone! Compact and the quality is great. Highly "
        "recommended to everyone! Sulit na sulit sa presyo.",
        ("Fast charging", "Compact"), (), "2299", "shopee", ups=0),
    ReviewSpec(
        "j_p20i", "jomar", "soundcore_p20i", 110,
        "Premium sound, highly recommended!", "yes_absolutely", 5,
        "Highly recommended to everyone!", "Everyone.", "None.",
        "Premium sound quality with deep bass. Long battery life, comfortable fit, fast and "
        "stable Bluetooth connection. Highly recommended to everyone!",
        ("Deep bass", "Long battery life"), (), "1150", "shopee", ups=0),
    ReviewSpec(
        "j_jisulife", "jomar", "jisulife_life9", 95,
        "Sobrang lakas ng hangin!", "yes_absolutely", 5,
        "Highly recommended to everyone!", "Everyone.", "None.",
        "Sobrang lakas ng hangin! Compact and the quality is great. Highly recommended to "
        "everyone! Sulit na sulit.",
        ("Strong airflow", "Compact"), (), "799", "shopee", ups=0),
    ReviewSpec(
        "j_osmo", "jomar", "dji_osmo_action6", 80,
        "Crystal clear video, sulit!", "yes_absolutely", 5,
        "Highly recommended to everyone!", "Everyone.", "None.",
        "Crystal clear video, great stabilisation, waterproof. Highly recommended to everyone! "
        "Sulit na sulit sa presyo.",
        ("Clear video", "Stabilisation"), (), "27990", "shopee", ups=0),
    # A near copy of Carla's PS5 review, three days old: the integrity sweep's
    # copied-text check matches it against hers, and the ring's reciprocal
    # up-votes on it trip the collusion check (dev/QA sync 2026-09-29: both
    # system-detected cases the defense shows, from the real pipeline).
    ReviewSpec(
        "j_ps5", "jomar", "ps5_digital", 3,
        "Great first console, sulit!", "yes_absolutely", 5,
        "Highly recommended to everyone!", "Everyone.", "None.",
        "My first PlayStation. Setup took only ten minutes and the controller's feedback "
        "really surprised me. I added an SSD for storage later. Sulit!",
        ("Easy setup", "Great controller"), (), "25990", "lazada", photo=False,
        decision=None, ups=0),

    # ---- Community ------------------------------------------------------------
    ReviewSpec(
        "c_renz_737", "renz", "anker_737", 190,
        "Solid companion for weekend trips", "yes_absolutely", 4,
        "Yes if you travel with a laptop; overkill for phone-only use.",
        "Travellers who carry a laptop and a phone.",
        "Anyone who only needs a quick phone top-up.",
        "Brought this on a four-day trip to Siargao where outlets in our room were limited. "
        "It kept my laptop and phone alive the whole time and I only recharged it once. The "
        "build feels premium. It is heavy though, so it's a checked-bag or backpack item.",
        ("Keeps a laptop going", "Premium build"), ("Heavy",),
        "4999", "shopee", ups=5),
    ReviewSpec(
        "c_aira_737", "aira", "anker_737", 175,
        "Powerful, but more than I actually needed", "it_depends", 3.5,
        "It depends on whether you need laptop charging. I didn't, so it was overkill.",
        "Laptop users and people who lose power often.",
        "Phone-only users; a 10,000mAh bank is lighter and cheaper.",
        "The 737 is excellent at what it does, but I mostly charge my phone and it's too big "
        "to bring every day. I ended up leaving it at home most of the time. Great product, "
        "wrong fit for me.",
        ("Very high capacity", "Fast charging"), ("Too big for daily carry",),
        None, None, photo=False, decision=None, ups=3),
    ReviewSpec(
        "c_dennis_737", "dennis", "anker_737", 100,
        "Mine stopped charging after three months", "hard_pass", 1.5,
        "Hard pass for me, though Anker's warranty did replace it.",
        "Nobody until the batch issue is sorted out.",
        "Anyone who can't wait two weeks for a warranty replacement.",
        "It worked perfectly at first, then one morning it stopped charging anything and the "
        "screen showed an error. Anker's warranty process worked, but it took two weeks and a "
        "trip to the courier. The replacement has been fine for a month. I'm rating the "
        "experience of owning the first unit, which let me down during a typhoon brownout.",
        ("Warranty process works",), ("First unit failed after three months",
                                      "Two-week wait for a replacement"),
        "4599", "shopee", decision="honesty_fund", ups=6, downs=1),
    ReviewSpec(
        "c_bea_nano", "bea", "anker_nano_10k", 60,
        "Tiny, fast, and the cable is always there", "yes_absolutely", 4,
        "Yes for anyone who keeps forgetting their cable.",
        "Students and office workers.",
        "People who need to charge a laptop.",
        "It fits in my small crossbody bag and charges my phone from 20% to 80% during my "
        "commute. The attached cable means I never have to hunt for one. It gets warm while "
        "charging, but nothing alarming.",
        ("Built-in cable", "Small and light"), ("Gets warm",),
        "1799", "shopee", ups=5),
    ReviewSpec(
        "c_gio_nano", "gio", "anker_nano_10k", 20,
        "Sulit for everyday carry", "yes_absolutely", 4.5,
        "Yes, especially during sales.",
        "Commuters and students.", "Laptop users.",
        "Bought it during the 9.9 sale for ₱1,850. It charges fast and the cable feels sturdy. "
        "I like that I can see the battery level on the small indicator.",
        ("Fast charging", "Sturdy cable"), ("Indicator is hard to read in sunlight",),
        "1850", "shopee", ups=3),
    ReviewSpec(
        "c_trisha_nano", "trisha", "anker_nano_10k", 35,
        "The built-in cable frayed within a month", "hard_pass", 2,
        "Hard pass until the cable is sturdier.",
        "Light users who treat their gear gently.",
        "Anyone rough on cables or who wraps them tightly.",
        "I loved it for three weeks. Then the built-in cable started fraying right where it "
        "meets the body, and because it's built in, I can't just replace it. I did wrap it "
        "tightly around the bank, which probably didn't help, but a built-in cable should "
        "survive normal use.",
        ("Convenient while it lasted",), ("Cable frayed within a month",
                                          "Built-in cable can't be replaced"),
        "1999", "lazada", decision="honesty_fund", ups=6),
    ReviewSpec(
        "c_camille_life9", "camille", "jisulife_life9", 120,
        "My everyday fan for Cebu heat", "yes_absolutely", 4,
        "Yes for anyone outdoors a lot.",
        "Students and outdoor workers.",
        "People sensitive to fan noise.",
        "Used it every day for four months around Cebu. Battery lasts a school day on speed 2 "
        "and it charges fully in about two hours. I bought a second one for my mother.",
        ("Lasts a school day", "Charges quickly"), ("A bit noisy on max",),
        "799", "shopee", ups=5),
    ReviewSpec(
        "c_ken_life9", "ken", "jisulife_life9", 80,
        "Decent fan, strap broke early", "it_depends", 3,
        "It depends on how rough you are with it.",
        "Light daily use.", "Hikers and anyone hard on their gear.",
        "The fan itself works well, but the wrist strap snapped after a month. I use it on my "
        "desk now instead of carrying it.",
        ("Good airflow",), ("Strap broke after a month",),
        "899", "shopee", decision="rejected",
        reject_reason="The photo is the seller's listing image, not a photo of your own "
                      "unit. Upload a photo you took of the fan you received and ask for a "
                      "re-check.",
        ups=2),
    ReviewSpec(
        "c_joshua_p20i", "joshua", "soundcore_p20i", 150,
        "Best budget earbuds I've owned", "yes_absolutely", 4,
        "Yes for the price.", "Students on a budget.", "People who need ANC.",
        "For ₱1,199 these beat earbuds I bought for twice the price. Bass is punchy and they "
        "stay in during jogs. No ANC, as expected at this price.",
        ("Punchy bass", "Secure fit"), ("No ANC",),
        "1199", "shopee", photo=False, decision=None, ups=4),
    ReviewSpec(
        "c_hazel_p20i", "hazel", "soundcore_p20i", 88,
        "Nice sound, meh mic", "it_depends", 3.5,
        "It depends on whether you take calls on them.",
        "Music listeners.", "People who take a lot of calls outdoors.",
        "Music sounds great for the price, but callers said I sounded far away whenever I was "
        "outside. Indoors it's fine. Selling my extra unit, sealed pa, text me at "
        "0917 555 0182.",
        ("Good music quality",), ("Weak mic outdoors",),
        "1250", "lazada", ups=2, downs=2),
    ReviewSpec(
        "c_miguel_l4nc", "miguel", "soundcore_liberty4nc", 170,
        "Noise cancelling that makes commutes bearable", "yes_absolutely", 5,
        "Yes, the best purchase for my daily bus ride.",
        "Commuters.", "People who prefer a very neutral sound.",
        "The bus engine noise basically disappears. I use them two hours a day and charge the "
        "case once a week. The app is simple and the fit test helped me pick the right tips.",
        ("Excellent ANC", "Great battery"), ("Case is bulky",),
        "4995", "lazada", ups=5),
    ReviewSpec(
        "c_lara_l4nc", "lara", "soundcore_liberty4nc", 95,
        "Comfortable for long calls", "yes_absolutely", 4,
        "Yes for remote work.", "Remote workers.", "Gym use - they feel loose when sweaty.",
        "I take calls for six hours a day and these stay comfortable. My voice comes through "
        "clearly according to my team. They slip a little during workouts.",
        ("Comfortable", "Clear calls"), ("Slip during workouts",),
        "4799", "lazada", photo=False, decision=None, ups=3),
    ReviewSpec(
        "c_vince_ugreen", "vince", "ugreen_nexode_65w", 140,
        "Replaced my laptop brick completely", "yes_absolutely", 5,
        "Yes, one of the best chargers for the money.",
        "Laptop users.", "People who need more than 65W for a gaming laptop.",
        "My original laptop charger was twice the size. This one charges my ultrabook just as "
        "fast and has room for my phone and watch. Five months, no issues.",
        ("Small", "Three ports"), ("Not enough for gaming laptops",),
        "2395", "lazada", ups=4),
    ReviewSpec(
        "c_patrice_ugreen", "patrice", "ugreen_nexode_65w", 76,
        "Good charger, runs warm", "yes_absolutely", 4.5,
        "Yes, just give it some air.", "Anyone with a USB-C laptop.",
        "People who want a charger that stays cool.",
        "Charges everything I own quickly. It gets warm when all three ports are in use, so I "
        "keep it out of my bag while charging.",
        ("Fast", "Three ports"), ("Runs warm under full load",),
        "2350", "shopee", ups=3),
    ReviewSpec(
        "c_steph_iphone", "steph", "iphone_17", 80,
        "Worth the upgrade from an iPhone 12", "yes_absolutely", 4.5,
        "Yes for older-iPhone owners.", "iPhone 12 and 13 owners.",
        "Anyone happy with an iPhone 15 or newer.",
        "Battery life is the biggest change: I now finish the day with charge left. Photos of "
        "food and friends at night look much better than on my 12.",
        ("Battery life", "Low-light photos"), ("Expensive",),
        "57490", "shopee", decision="monetized", ups=5),
    ReviewSpec(
        "c_mark_iphone", "mark", "iphone_17", 12,
        "Great phone, but 128GB fills up fast", "it_depends", 4,
        "It depends on your storage needs - get 256GB if you shoot video.",
        "Light users.", "People who record a lot of video.",
        "Performance and battery are excellent. I went with 128GB to save money and I'm "
        "already at 90% after moving my photos over. Choose storage carefully.",
        ("Fast", "Long battery"), ("128GB fills quickly",),
        "59990", "lazada", decision="pending", ups=2),
    ReviewSpec(
        "c_rina_ipad", "rina", "ipad_11_a16", 110,
        "The iPad I use for school every day", "yes_absolutely", 4,
        "Yes for students who take notes by hand.",
        "College students.", "Artists who need a laminated screen.",
        "I take all my notes on it with a stylus and read my PDFs on the go. Battery lasts two "
        "school days. The screen isn't laminated, so writing feels a bit floaty.",
        ("Two-day battery", "Great for notes"), ("Screen isn't laminated",),
        "28990", "shopee", decision="monetized", ups=4),
    ReviewSpec(
        "c_joan_ipad", "joan", "ipad_11_a16", 66,
        "Perfect for my parents", "yes_absolutely", 5,
        "Yes for video calls and streaming.", "Parents and grandparents.",
        "Anyone who needs it for heavy work.",
        "Bought it for my parents in Pampanga. Big clear screen for video calls with us and "
        "easy enough for them to use on their own.",
        ("Easy to use", "Big clear screen"), (),
        "28990", "shopee", photo=False, decision=None, ups=3),
    ReviewSpec(
        "c_ivan_osmo", "ivan", "dji_osmo_action6", 100,
        "Stable footage for dive trips", "yes_absolutely", 4.5,
        "Yes for divers and bikers.", "Divers, bikers, travel vloggers.",
        "People who only shoot on land occasionally - your phone is enough.",
        "Took it diving in Anilao. The colours underwater came out better than my old camera "
        "and the stabilisation smoothed out my shaky hands. Battery gives about 90 minutes of "
        "4K recording.",
        ("Great underwater colour", "Smooth stabilisation"), ("Battery could be longer",),
        "27990", "shopee", decision="monetized", ups=5),
    ReviewSpec(
        "c_raf_osmo", "raf", "dji_osmo_action6", 58,
        "Good camera, overkill for me", "it_depends", 3,
        "It depends on how often you actually go out and shoot.",
        "People who shoot outdoors often.", "Casual users - a phone will do.",
        "The footage is excellent, but I only used it on two trips. For my needs a phone with "
        "a good gimbal would have been enough.",
        ("Excellent footage",), ("Expensive for occasional use",),
        "27990", "shopee", ups=2),
    ReviewSpec(
        "c_amiel_deck", "amiel", "steam_deck_oled", 90,
        "OLED makes all the difference", "yes_absolutely", 5,
        "Yes if you play on Steam.", "PC gamers.", "Console-only players.",
        "Colours are amazing and battery lasts longer than I expected. I play every night "
        "before bed now.",
        ("Amazing screen", "Good battery"), ("Heavy",),
        "33490", "lazada", ups=4),
    ReviewSpec(
        "c_kathleen_ps5", "kathleen", "ps5_digital", 85,
        "Happy with digital, buy games on sale", "yes_absolutely", 4,
        "Yes if you wait for sales.", "Patient gamers.", "Collectors of physical games.",
        "I only buy games during PlayStation Store sales and it works out fine. The console "
        "is quiet and loads fast.",
        ("Quiet", "Fast loading"), ("Storage fills up",),
        "25990", "lazada", ups=3),
    ReviewSpec(
        "c_carla_ps5", "carla", "ps5_digital", 105,
        "Great first console", "yes_absolutely", 5,
        "Yes for a first console.", "New players.", "People with big disc collections.",
        "My first PlayStation. Setup took ten minutes and the controller's feedback surprised "
        "me. I added an SSD for storage later.",
        ("Easy setup", "Great controller"), ("Needs extra storage",),
        "25990", "lazada", decision="monetized", ups=5),
    ReviewSpec(
        "c_jaymie_akko", "jaymie", "akko_5075b", 150,
        "Made my home office nicer to work in", "yes_absolutely", 4.5,
        "Yes for anyone who types all day.", "Writers and office workers.",
        "People who need a very quiet keyboard for shared rooms.",
        "I type reports all day and my fingers feel less tired. It's quieter than I expected "
        "for a mechanical keyboard, but my partner still hears it during late shifts.",
        ("Comfortable typing", "Premium feel"), ("Still audible at night",),
        "3799", "shopee", ups=4),
    ReviewSpec(
        "c_ella_macbook", "ella", "macbook_air_m2", 125,
        "Light, silent, lasts all day", "yes_absolutely", 5,
        "Yes for office work.", "Office workers and students.", "Heavy video editors.",
        "Replaced a heavy work laptop with this. It lasts all day, never makes noise, and "
        "wakes instantly. Perfect for spreadsheets and meetings.",
        ("Battery life", "Silent"), ("Few ports",),
        "58990", "lazada", ups=4),
    ReviewSpec(
        "c_nico_cerave", "nico", "cerave_foaming", 115,
        "Finally a cleanser that controls my oily skin", "yes_absolutely", 4,
        "Yes for oily skin.", "Oily and acne-prone skin.", "Dry skin.",
        "My skin gets very oily in Cebu's heat. This cleans it without stinging and my shine "
        "is under control until the afternoon.",
        ("Controls oil", "No stinging"), ("Pump bottle leaks when travelling",),
        "1299", "shopee", ups=5),
    ReviewSpec(
        "c_dennis_uratex", "dennis", "uratex_classic", 140,
        "Good guest-room mattress", "yes_absolutely", 4,
        "Yes for guest rooms.", "Occasional use and guest rooms.",
        "Someone who wants a soft mattress for nightly use.",
        "We keep it in our guest room. Relatives say it's firm but comfortable, and it still "
        "looks new after four months.",
        ("Keeps its shape", "Looks neat"), ("Firm",),
        "3850", "shopee", ups=3),
    # Written, then removed by its own author: the product's counts forget it.
    ReviewSpec(
        "c_kathleen_iphone", "kathleen", "iphone_17", 30,
        "Wrong model, will rewrite", "it_depends", 3,
        "Posted under the wrong model.", "iPhone buyers.", "None.",
        "I meant to review the iPhone 17 Pro I bought for my brother, not this one. Removing "
        "this and writing it again under the right product.",
        ("Fast",), ("Posted by mistake",),
        None, None, photo=False, decision=None, ups=0, author_deletes=True),
)

REVIEW: dict[str, ReviewSpec] = {r.key: r for r in REVIEWS}

# ---------------------------------------------------------------- comments


@dataclass(frozen=True)
class CommentSpec:
    author: str
    #: Days after the review was published.
    after_days: int
    body: str
    replies: tuple[CommentSpec, ...] = ()
    #: Members who up-voted the comment.
    liked_by: tuple[str, ...] = ()


C = CommentSpec
COMMENTS: dict[str, tuple[CommentSpec, ...]] = {
    "k_ankernano": (
        C("maria", 30, "Planning to buy this for my son who's starting college. Kaya ba nito "
          "i-charge yung iPad niya kahit papaano?",
          replies=(C("kristine", 30, "Yes, it tops up an iPad fine - about one full charge on "
                     "my 10th-gen iPad. Just not a laptop.", liked_by=("maria", "bea")),
                   C("maria", 31, "Perfect, iPad and phone lang naman. Thank you!"))),
        C("trisha", 12, "Mine's cable frayed after a month. Did yours hold up?",
          replies=(C("kristine", 13, "Six weeks in and still fine. I avoid bending it sharply "
                     "at the base, maybe that helped?", liked_by=("trisha",)),
                   C("trisha", 13, "Baka nga. I used to wrap it tightly around the power bank."))),
        C("bea", 8, "Agree about the warmth while fast charging. Anker support told me it's "
          "normal.", liked_by=("kristine", "renz")),
        C("renz", 20, "Nice comparison with the 737. I own both: the 737 stays home, the Nano "
          "goes in my bag.", liked_by=("kristine", "maria", "camille")),
        C("camille", 25, "This review is why I added it to my cart. Thanks!"),
    ),
    "m_anker737": (
        C("renz", 5, "Same experience during brownouts. Tip: charge it at night when the load "
          "is lower.", liked_by=("maria",)),
        C("dennis", 45, "Mine stopped charging after three months, but Anker replaced it under "
          "warranty. Glad yours is fine!",
          replies=(C("maria", 46, "Oh no! Good to know the warranty works, though."),)),
        C("aira", 20, "How long does it take to recharge the power bank itself?",
          replies=(C("maria", 20, "A little over two hours with a 65W charger. With a phone "
                     "charger it takes overnight.", liked_by=("aira",)),)),
    ),
    "k_liberty4nc": (
        C("miguel", 10, "Agree on the equaliser tip. The bass was too much for me too."),
        C("lara", 60, "How's the fit for small ears?",
          replies=(C("kristine", 61, "The smallest tips fit me well, and my ears are small. "
                     "Try the fit test in the app.", liked_by=("lara",)),)),
    ),
    "k_steamdeck": (
        C("amiel", 15, "OLED talaga. The colours in Hades are unreal."),
        C("carla", 40, "How's the heat when you play with it on your lap?",
          replies=(C("kristine", 41, "The back gets warm on big games, but never "
                     "uncomfortable."),)),
    ),
    "m_iphone17": (
        C("steph", 3, "Same upgrade path from a 12! The battery difference is night and day.",
          liked_by=("maria",)),
        C("mark", 20, "Did you get the 256GB? Wondering if 128 is enough.",
          replies=(C("maria", 21, "256. With two kids, photos fill it up fast."),)),
    ),
    "m_cerave": (
        C("nico", 7, "Same with my sister, who has dry skin. The hydrating one worked better "
          "for her.", liked_by=("maria",)),
        C("bea", 12, "Thanks for being honest. The hype can be a lot sometimes."),
    ),
    "k_ps5": (
        C("kathleen", 9, "Fair point about used discs. I went digital and don't regret it, but "
          "I only buy during sales."),
        C("carla", 18, "True, storage fills up fast. I added an SSD after two months."),
    ),
    "m_uratex": (
        C("dennis", 30, "We have the same one in our guest room. Agree about getting a "
          "protector."),
    ),
    "p_jisulife": (
        C("maria", 1, "Welcome to Bluntly, Paolo! Mine lasts longer on speed 2 - try a full "
          "charge cycle first.",
          replies=(C("paolo", 1, "Thank you po! I'll try that."),)),
    ),
    "j_p20i": (
        C("kristine", 20, "This reads almost exactly like the product listing's description."),
    ),
    "c_dennis_737": (
        C("renz", 4, "Good to know the warranty route works. How long did the courier pickup "
          "take?",
          replies=(C("dennis", 5, "They picked it up the next day. The replacement arrived "
                     "about two weeks later."),)),
    ),
    "c_trisha_nano": (
        C("kristine", 2, "Sorry to hear that. Did you try Anker's warranty? The cable is "
          "covered.",
          replies=(C("trisha", 3, "Filing one now, thanks for the tip."),)),
    ),
    "c_ivan_osmo": (
        C("raf", 6, "What housing did you use for the dive?",
          replies=(C("ivan", 7, "No housing - it's waterproof to 20m on its own. I stayed "
                     "above that."),)),
    ),
}

# ---------------------------------------------------------------- Q&A


@dataclass(frozen=True)
class AnswerSpec:
    author: str
    after_days: int
    body: str


@dataclass(frozen=True)
class QuestionSpec:
    key: str
    asker: str
    days_ago: int
    body: str
    product: str | None = None
    store: str | None = None
    directed_to: str = "buyers"
    answers: tuple[AnswerSpec, ...] = ()
    #: Index into `answers` the asker picked, if any.
    best: int | None = None
    #: Members who turned on "Notify me".
    subscribers: tuple[str, ...] = ()


A = AnswerSpec

#: Every member's answer to a product question carries a star rating (owner
#: 2026-10-05, structured Q&A): the answerer's own stars for the product, read
#: off what each answer says. Keyed by (question, answer position). A store's
#: answer, and answers to a question about a store, have none.
ANSWER_RATINGS: dict[tuple[str, int], str] = {
    ("q_nano_ipad", 0): "3", ("q_nano_ipad", 1): "3.5", ("q_nano_ipad", 2): "5",
    ("q_737_recharge", 0): "4", ("q_737_recharge", 1): "4.5",
    ("q_p20i_mic", 0): "3", ("q_p20i_mic", 1): "3",
    ("q_ugreen_dual", 0): "4", ("q_ugreen_dual", 1): "4.5",
    ("q_l4nc_hiss", 0): "4", ("q_l4nc_hiss", 1): "4.5",
    ("q_deck_upgrade", 0): "4.5", ("q_deck_upgrade", 1): "4",
    ("q_cerave_sensitive", 0): "4.5", ("q_cerave_sensitive", 1): "4",
    ("q_life9_battery", 0): "4",
}
QUESTIONS: tuple[QuestionSpec, ...] = (
    QuestionSpec(
        "q_nano_ipad", "maria", 3,
        "Kaya ba nitong i-charge ang 14-inch laptop kahit papaano? Planning to give it to my "
        "son for college.", product="anker_nano_10k",
        answers=(A("kristine", 0, "Not really. At 30W it only slows a laptop's drain. For a "
                   "laptop, look at the Anker 737. For phones and an iPad it's great."),
                 A("bea", 1, "Agree with Kristine. My son uses it for his phone and tablet "
                   "and it lasts him the whole school day."),
                 A("jomar", 1, "Yes kayang-kaya, super sulit!")),
        subscribers=("maria",)),
    QuestionSpec(
        "q_737_recharge", "aira", 120,
        "How long does the Anker 737 take to fully recharge itself?", product="anker_737",
        answers=(A("renz", 0, "About three hours with my laptop's charger."),
                 A("maria", 1, "A little over two hours with a 65W or stronger USB-C charger. "
                   "With a basic phone charger, it's an overnight job.")),
        best=1),
    QuestionSpec(
        "q_p20i_mic", "camille", 80,
        "Maayos ba ang mic ng P20i for Zoom calls in a noisy café?", product="soundcore_p20i",
        answers=(A("kristine", 1, "Indoors it's fine, but in a busy café people will hear the "
                   "background. For calls in noisy places, the Liberty 4 NC is much better."),
                 A("joshua", 2, "Okay lang indoors. Outside, medyo malayo ang boses mo.")),
        best=0),
    QuestionSpec(
        "q_ugreen_dual", "jaymie", 70,
        "Can the Nexode 65W charge a MacBook Air and a phone at the same time at full speed?",
        product="ugreen_nexode_65w",
        answers=(A("kristine", 0, "Almost. With both plugged in, the laptop gets about 45W and "
                   "the phone 20W, so the laptop charges a bit slower but it's still fast."),
                 A("vince", 3, "Same experience with my ultrabook. It's close enough to full "
                   "speed.")),
        best=0),
    QuestionSpec(
        "q_l4nc_hiss", "hazel", 90,
        "Does the noise cancelling on the Liberty 4 NC make a hissing sound in quiet rooms?",
        product="soundcore_liberty4nc",
        answers=(A("kristine", 1, "A very faint hiss in a silent room, which disappears once "
                   "anything is playing. On a commute you won't notice it."),
                 A("miguel", 2, "I don't hear any on mine.")),
        best=0),
    QuestionSpec(
        "q_deck_upgrade", "ivan", 25,
        "Is the OLED model worth it if I already own the LCD Steam Deck?",
        product="steam_deck_oled",
        answers=(A("kristine", 1, "If you play a lot on battery, yes: the OLED lasts noticeably "
                   "longer and looks much better. Otherwise, keep your LCD."),
                 A("amiel", 2, "Only if you can sell the LCD for a good price.")),
        subscribers=("ivan",)),
    QuestionSpec(
        "q_powerhub_or", "trisha", 50,
        "Do you issue official receipts for company reimbursement?",
        store="powerhub", directed_to="seller",
        answers=(A("rico", 0, "Yes po. Message us your company name and TIN after ordering and "
                   "we'll email the official receipt within two business days."),)),
    QuestionSpec(
        "q_galaxy_warranty", "steph", 5,
        "Is the stock you ship the Philippine version with local warranty?",
        store="galaxy", directed_to="seller"),
    QuestionSpec(
        "q_iphone_120hz", "joan", 1,
        "Mas mabilis ba mag-drain ang battery kapag naka-120Hz ang screen?",
        product="iphone_17"),
    QuestionSpec(
        "q_cerave_sensitive", "ella", 45,
        "Is the foaming cleanser okay for sensitive skin with mild acne?",
        product="cerave_foaming",
        answers=(A("nico", 1, "It worked for my mild acne without stinging."),
                 A("maria", 2, "If your skin is also dry, try the hydrating cleanser first. "
                   "The foaming one was too much for my dry cheeks.")),
        best=1),
    QuestionSpec(
        "q_life9_battery", "paolo", 1,
        "Gaano katagal ang battery ng Life9 on speed 3?", product="jisulife_life9",
        answers=(A("maria", 0, "Around three and a half hours on speed 3 for me, and about "
                   "seven on speed 2."),),
        subscribers=("paolo",)),
)

# ---------------------------------------------------------------- store reviews


@dataclass(frozen=True)
class StoreReviewSpec:
    key: str
    store: str
    author: str
    days_ago: int
    accuracy: bool
    complete: bool
    service: int
    packaging: int
    overall: float
    recommend: bool
    title: str
    comment: str
    product: str | None = None
    order_id: str | None = None
    #: The claimed owner's public reply.
    response: str | None = None
    #: The owner flags it as a suspected fake; a moderator asks for substantiation.
    appeal: str | None = None


STORE_REVIEWS: tuple[StoreReviewSpec, ...] = (
    StoreReviewSpec(
        "s_maria_powerhub", "powerhub", "maria", 148, True, True, 5, 5, 5, True,
        "Fast, well-packed, legit item",
        "Ordered the Anker 737 during a payday sale. It arrived in two days, bubble-wrapped "
        "twice, and the serial number checked out on Anker's site. The seller replied to my "
        "chat within minutes.", product="anker_737", order_id="2604PH18830571",
        response="Salamat po, Maria! We're glad the 737 arrived safely. Enjoy the "
                 "brownout-proof nights."),
    StoreReviewSpec(
        "s_kristine_powerhub", "powerhub", "kristine", 44, True, True, 4, 5, 4.5, True,
        "Genuine stock, excellent packaging",
        "Genuine Anker stock. Packaging was excellent; delivery to Pasig took four days.",
        product="anker_nano_10k", order_id="2608PH20417732"),
    StoreReviewSpec(
        "s_renz_powerhub", "powerhub", "renz", 188, True, True, 4, 3, 4, True,
        "Good item, dented box",
        "The power bank was fine, but the box arrived a bit dented. The seller offered a small "
        "voucher when I messaged them.", product="anker_737", order_id="2603PH16603318",
        response="Sorry about the dented box, Renz. We've switched to thicker cartons since."),
    StoreReviewSpec(
        "s_trisha_powerhub", "powerhub", "trisha", 36, True, True, 2, 3, 2, False,
        "Slow shipping, slow replies",
        "The power bank was genuine, but shipping took nine days and nobody answered my chat "
        "until I left a review.", product="anker_nano_10k", order_id="2609PH21100457",
        response="Hi Trisha, you're right that we were slow during the 9.9 rush. We've added "
                 "another person to answer chats. Sorry for the wait."),
    StoreReviewSpec(
        "s_gio_powerhub", "powerhub", "gio", 21, True, True, 5, 5, 5, True,
        "Mabilis at maayos",
        "Fast and careful packing. Will order again.", product="ugreen_nexode_65w",
        order_id="2609PH21398810"),
    StoreReviewSpec(
        "s_patrice_powerhub", "powerhub", "patrice", 16, False, False, 1, 1, 1, False,
        "Received an empty box",
        "The parcel arrived with nothing inside and the seller refused a refund.",
        product="ugreen_nexode_65w", order_id="2609PH21766120",
        appeal="We have no order under this order number, and no refund request on our "
               "records. We believe this review is not from a real order."),
    StoreReviewSpec(
        "s_ivan_galaxy", "galaxy", "ivan", 99, True, True, 4, 4, 4, True,
        "Genuine unit, slow courier",
        "Genuine DJI unit with the PH warranty card. Delivery took a week.",
        product="dji_osmo_action6", order_id="LZ-5541908823"),
    StoreReviewSpec(
        "s_amiel_galaxy", "galaxy", "amiel", 89, True, True, 5, 5, 5, True,
        "Well-packed Steam Deck",
        "Arrived in three days in a double box with foam corners.",
        product="steam_deck_oled", order_id="LZ-5602117364"),
    StoreReviewSpec(
        "s_carla_galaxy", "galaxy", "carla", 104, True, True, 5, 4, 4.5, True,
        "Sealed with receipt",
        "Sealed PS5 with an official receipt. The seller answered my questions quickly.",
        product="ps5_digital", order_id="LZ-5523306619"),
    StoreReviewSpec(
        "s_kathleen_galaxy", "galaxy", "kathleen", 84, True, True, 3, 3, 3, True,
        "Okay, but the courier left it outside",
        "The item was fine, but the courier left the box outside our gate without calling.",
        product="ps5_digital", order_id="LZ-5611450092"),
    StoreReviewSpec(
        "s_camille_cebuhub", "cebuhub", "camille", 118, True, True, 5, 4, 4, True,
        "Local shop, next-day shipping",
        "A local shop in Cebu. They shipped the next day and it arrived within the week.",
        product="jisulife_life9", order_id="2605PH17281554"),
    StoreReviewSpec(
        "s_joshua_cebuhub", "cebuhub", "joshua", 149, True, True, 4, 5, 4.5, True,
        "Sealed and authentic",
        "The earbuds were sealed and authentic, with a receipt in the box.",
        product="soundcore_p20i", order_id="2604PH18300217"),
    StoreReviewSpec(
        "s_dennis_tahanan", "tahanan", "dennis", 139, True, True, 4, 5, 4, True,
        "Mattress arrived well sealed",
        "The mattress arrived roll-packed and well sealed, with no dents or stains.",
        product="uratex_classic", order_id="LZ-5418830025"),
    StoreReviewSpec(
        "s_hazel_tahanan", "tahanan", "hazel", 72, True, True, 3, 4, 3.5, True,
        "Good item, slow delivery",
        "The item matched the listing, but delivery took ten days.",
        order_id="LZ-5650031187"),
    StoreReviewSpec(
        "s_nico_glowup", "glowup", "nico", 114, True, True, 5, 5, 5, True,
        "Authentic and fresh stock",
        "Authentic and sealed, with an expiry date two years away.",
        product="cerave_foaming", order_id="2605PH17444901"),
    StoreReviewSpec(
        "s_bea_glowup", "glowup", "bea", 58, True, True, 4, 4, 4, True,
        "Legit products",
        "Legit products. Delivery took five days to Laguna.", product="cerave_foaming",
        order_id="2607PH19623305"),
)

# ---------------------------------------------------------------- prices


@dataclass(frozen=True)
class PriceSpec:
    """A community price report, beyond the ones reviews carry with them."""
    product: str
    platform: str
    price: str
    days_ago: int
    submitter: str
    #: approve (charted), pending (waiting for a moderator), or none - an
    #: outlier the system holds for a moderator's glance on its own.
    decision: str = "approve"
    variant: str | None = None


#: Chosen so the four chart shapes the defense needs all exist: Shopee only
#: (Anker 737), Lazada only (Steam Deck), both marketplaces (Life9, iPhone 17),
#: and an outlier held for review (iPhone 17 at a price too good to be true).
PRICES: tuple[PriceSpec, ...] = (
    # Business rule: a price report comes from the reporter's own review of the
    # product (price_needs_review), so every reporter here reviewed it. §16: a
    # product/platform needs three approved prices before new ones publish on
    # their own; after that, anything under half or over double the median is
    # held as an outlier for a moderator's glance.
    PriceSpec("anker_737", "shopee", "4299", 64, "aira", variant="9.9 sale"),
    PriceSpec("anker_737", "shopee", "4499", 18, "renz"),
    PriceSpec("steam_deck_oled", "lazada", "31990", 40, "amiel", variant="512GB"),
    PriceSpec("jisulife_life9", "lazada", "949", 70, "camille"),
    PriceSpec("jisulife_life9", "shopee", "779", 25, "ken"),
    PriceSpec("iphone_17", "shopee", "57990", 15, "maria", variant="256GB"),
    PriceSpec("iphone_17", "lazada", "59490", 6, "mark", variant="256GB"),
    # "Too good to be true": under half the median, so the system holds it.
    PriceSpec("iphone_17", "shopee", "24999", 4, "steph", decision="none", variant="256GB"),
    # The first Lazada price for this mattress: no baseline yet, so it waits.
    PriceSpec("uratex_classic", "lazada", "4150", 5, "dennis", decision="pending"),
)

# ---------------------------------------------------------------- money


@dataclass(frozen=True)
class OrderSpec:
    """One marketplace order through a review's affiliate link.

    `days_ago` is when the reader clicked. The seed writes each order into a
    real-format Shopee or Lazada export and imports it the way a moderator
    would (admin/affiliate/import), so `status` is the marketplace's word:
    completed (Shopee) / delivered (Lazada) is money, pending is not yet, and
    cancelled never is.

    Money clears when the marketplace pays Bluntly for the month (§15). The seed
    records that payout for every month that ended 30+ days ago, so an order
    clicked 65+ days ago is withdrawable and one clicked within 20 days is not,
    whatever day the seed runs.
    """
    review: str
    days_ago: int
    #: The affiliate commission the marketplace reports for the order.
    gross: str
    status: str = "completed"


ORDERS: tuple[OrderSpec, ...] = (
    # Maria - Uratex, Shopee: eight cleared orders, one completed but not yet paid out.
    *(OrderSpec("m_uratex", d, g) for d, g in (
        (150, "308.00"), (145, "308.00"), (138, "296.00"), (131, "320.00"),
        (100, "308.00"), (95, "312.00"), (88, "308.00"), (84, "300.00"))),
    OrderSpec("m_uratex", 12, "308.00"),
    # Maria - iPhone 17, Shopee: one completed this month, one still with the courier.
    OrderSpec("m_iphone17", 18, "1180.00"),
    OrderSpec("m_iphone17", 9, "1150.00", status="pending"),
    # Kristine - Steam Deck, Lazada: one cleared (below the ₱300 threshold on its
    # own share), one delivered this month, one still with the courier.
    OrderSpec("k_steamdeck", 90, "620.00"),
    OrderSpec("k_steamdeck", 15, "990.00"),
    OrderSpec("k_steamdeck", 8, "960.00", status="pending"),
    # Steph - iPhone 17, Shopee: cleared, and she asks for a cashout.
    OrderSpec("c_steph_iphone", 76, "1180.00"),
    OrderSpec("c_steph_iphone", 71, "1120.00"),
    # Rina, Ivan: small cleared balances. Carla: delivered, not paid out yet.
    OrderSpec("c_rina_ipad", 95, "580.00"),
    OrderSpec("c_ivan_osmo", 88, "840.00"),
    OrderSpec("c_carla_ps5", 14, "520.00"),
    # A cancelled order: recorded in the ledger, never paid.
    OrderSpec("m_iphone17", 6, "0.00", status="cancelled"),
    # QA coverage (owner 2026-10-05): every window the reports compare has
    # orders - this week, last week, and the 30-60 days "30d" is compared
    # against - each on a review already published by then. None changes a
    # persona's story: Kristine stays under the cashout threshold, Carla's one
    # order stays unpaid, Ivan's balance stays small.
    OrderSpec("m_uratex", 2, "308.00"),
    OrderSpec("k_steamdeck", 4, "975.00"),
    OrderSpec("c_ivan_osmo", 1, "860.00", status="pending"),
    OrderSpec("c_rina_ipad", 10, "590.00"),
    OrderSpec("m_iphone17", 33, "1160.00"),
    OrderSpec("m_uratex", 35, "304.00"),
    OrderSpec("c_steph_iphone", 44, "1150.00"),
    OrderSpec("k_steamdeck", 47, "0.00", status="cancelled"),
    OrderSpec("m_uratex", 52, "300.00"),
)

#: The report windows the app compares (analytics 7d/30d/90d/12m against the
#: equal window before; Overview 1M/6M/1Y), as (label, newest day, oldest day)
#: in days ago - for checking the dataset covers each one.
REPORT_WINDOWS: tuple[tuple[str, int, int], ...] = (
    ("this week", 0, 6), ("last week", 7, 13),
    ("30d", 0, 29), ("previous 30d", 30, 59),
    ("90d", 0, 89), ("previous 90d", 90, 179),
)


def money_in(lo: int, hi: int, *, paid_only: bool = False) -> Decimal:
    """Commission the dataset's orders report for clicks `lo`..`hi` days ago,
    cancelled ones excluded (and pending ones with `paid_only`): the
    deterministic total a window should hold."""
    skip = ("cancelled", "pending") if paid_only else ("cancelled",)
    return sum((Decimal(o.gross) for o in ORDERS
                if lo <= o.days_ago <= hi and o.status not in skip), Decimal("0"))

#: What each monetized product sells for on its listing, for the export's
#: order value; the commission rate in the export is derived from it.
ORDER_VALUE: dict[str, int] = {
    "uratex_classic": 4399, "iphone_17": 57990, "steam_deck_oled": 31990,
    "ipad_11_a16": 22990, "dji_osmo_action6": 24990, "ps5_digital": 27990,
}

#: The (fictional) shop each export names as the seller.
ORDER_SHOP: dict[str, str] = {
    "uratex_classic": "Tahanan Home Finds", "iphone_17": "PowerHub PH",
    "steam_deck_oled": "Gadget Galaxy Manila", "ipad_11_a16": "PowerHub PH",
    "dji_osmo_action6": "Cebu Gadget Hub", "ps5_digital": "Gadget Galaxy Manila",
}


@dataclass(frozen=True)
class CashoutSpec:
    person: str
    amount: str
    #: paid - processed on the manual rail; requested - waiting in the batch.
    outcome: str
    days_ago: int


CASHOUTS: tuple[CashoutSpec, ...] = (
    CashoutSpec("maria", "369.60", "paid", 70),
    CashoutSpec("steph", "690.00", "requested", 3),
)

#: Where payouts go. PayPal sandbox addresses on the defense domain: no real
#: money can move, and no real person's address is stored.
PAYOUT_ACCOUNTS: dict[str, str] = {
    "maria": "maria.reyes.payouts@demo.bluntly.ph",
    "kristine": "kristine.v.payouts@demo.bluntly.ph",
    "steph": "steph.rivera.payouts@demo.bluntly.ph",
}

# ---------------------------------------------------------------- moderation


@dataclass(frozen=True)
class ReportSpec:
    review: str
    reporter: str
    reason: str
    notes: str
    #: None stays open in the queue; otherwise the moderator's resolution.
    resolution: str | None = None
    resolution_notes: str | None = None
    #: How long ago it was filed; a resolved one was decided 18 hours later.
    hours_ago: int = 24


REPORTS: tuple[ReportSpec, ...] = (
    # Urgent: personal information escalates near-immediately (§12).
    ReportSpec("c_hazel_p20i", "lara", "personal_information",
               "Contains a phone number and an offer to sell a unit outside the platform.",
               hours_ago=7),
    # Normal priority: a possible copied review.
    ReportSpec("j_p20i", "kristine", "plagiarized",
               "Possible copied review: it reads almost word for word like the listing's "
               "product description.", hours_ago=52),
    # Escalated: an administrator wanted a second opinion, so it left the open
    # queue for the Overview (the behaviour confirmed on 2026-09-29).
    ReportSpec("j_ugreen", "vince", "fake_proof",
               "The photo looks like the store's own listing image, not a unit in hand.",
               resolution="escalated",
               resolution_notes="Second opinion needed: the photo matches the Shopee listing.",
               hours_ago=30),
    # Already handled: an "incorrect product listing" report the moderator dismissed.
    ReportSpec("c_camille_life9", "ken", "other",
               "Incorrect product listing? I think this is the Life9 Pro, not the Life9.",
               resolution="dismissed",
               resolution_notes="Checked the photo against both models: it is the Life9.",
               hours_ago=470),
)

#: The moderator's investigation of the voting ring (halves the account's
#: vote weight and withholds its evidence while it lasts).
INVESTIGATIONS: dict[str, str] = {
    "jomar": "Suspected coordinated voting: the same five accounts up-voted every one of "
             "this member's reviews within hours of posting.",
}

# ---------------------------------------------------------------- review requests


@dataclass(frozen=True)
class RequestSpec:
    requester: str
    #: The product it is about: every request names one (dev/QA sync 2026-09-29).
    product: str
    days_ago: int
    title: str
    details: str
    upvoters: tuple[str, ...] = ()
    #: The review the asker picked as the Best Answer, if they have. Every
    #: review of the product written after the request is an answer.
    best_answer: str | None = None


#: The three states the Bounty Board shows (dev/QA sync 2026-09-29): answered
#: with a Best Answer (off the board, on its own page); answered twice and
#: waiting for the asker to pick; not answered yet.
REQUESTS: tuple[RequestSpec, ...] = (
    RequestSpec("hazel", "anker_nano_10k", 50,
                "Anker Nano 10,000mAh - enough for a full day of commuting?",
                "I ride the MRT and a jeep both ways. Will it keep an iPhone going from 7am to "
                "9pm, and does the built-in cable survive being yanked daily?",
                upvoters=("raf", "ivan", "camille", "renz"), best_answer="k_ankernano"),
    RequestSpec("joshua", "iphone_17", 45,
                "Is the base iPhone 17 enough for a year of heavy use?",
                "Coming from an iPhone 12. I shoot a lot of video for work and game at night. "
                "Is the base model enough, or should I save for the Pro?",
                upvoters=("lara", "miguel")),
    RequestSpec("aira", "akko_5075b", 6,
                "Akko 5075B Plus - quiet enough for a shared room?",
                "My roommate sleeps early. How loud are the stock switches after a few weeks, "
                "and is the wireless lag noticeable?",
                upvoters=("bea", "steph", "hazel")),
)
