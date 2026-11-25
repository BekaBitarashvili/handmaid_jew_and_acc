# Product & Technical Specification — Handmade Jewelry Store

Version 1.0 · Brand name: TBD (use placeholder `{{BRAND}}`, configurable via `SiteSettings`)

---

## 1. Goals

1. Customers browse, fall in love with a piece, and buy it in as few steps as possible — no registration.
2. The owner runs the shop entirely from a phone: products, stock, discounts, orders.
3. The site feels like a small, elegant atelier with a story — not a template store.

### Non-goals (MVP)
Required customer accounts (optional accounts with order history and a saved wishlist are Phase 3 — guest checkout always stays), marketplace features, multi-currency, automated courier integration,
social-feed integrations (owner handles social media separately), reviews.

---

## 2. Domain specifics that drive the design

| Fact | Consequence |
|---|---|
| Most pieces are **one-of-a-kind** (stock = 1) | Stock reservation at checkout; race-safe payment confirmation; sold items move to an **Archive** instead of disappearing |
| Some items have real variants (headscarf color, bracelet size) | Optional `ProductVariant`; product without variants uses a single default variant |
| Pieces are made from natural stones | `Stone` is a first-class entity with its own page ("Stone Glossary") |
| Jewelry is often a gift | Gift wrapping + gift note at checkout; option to hide prices on the packing slip |
| Owner may take custom requests | "Commission a similar piece" request form linked from archived items |

---

## 3. Languages (i18n)

- Languages: `ka` (default), `en`. URL prefix: `/ka/...`, `/en/...` (`i18n_patterns`, default language prefixed too for clean SEO).
- Language switcher in header; remembers choice via cookie.
- Language resolution: URL prefix → language cookie → `ka`. The browser's `Accept-Language` is
  deliberately ignored, so every first visit lands on `/ka/` (`apps.core.middleware.LocaleMiddleware`).
- UI strings → `gettext`. Content fields (name, description, story, care, SEO fields, category/stone names, page bodies, FAQ) → `django-modeltranslation` with `_ka` / `_en` columns. Fallback to `ka` when `en` is empty.
- Slugs: translated per language (`slug_ka`, `slug_en`); latin transliteration for `ka` slugs (custom transliteration helper, e.g. "ქარვა" → `karva`).
- `hreflang` alternates on every page; sitemap per language.
- Emails/SMS sent in the language the order was placed in (`Order.language`).

---

## 4. Architecture

```
Browser ── HTMX/Alpine ──► Django (Gunicorn) ──► PostgreSQL
                               │   │
                               │   └──► Redis ◄── huey worker (emails, SMS, reservation expiry)
                               ├──► S3 storage + CDN (images)
                               └──► BOG / TBC hosted payment pages ──callback──► /payments/<provider>/callback/
```

### Repository layout
```
.
├── CLAUDE.md
├── docs/SPEC.md
├── pyproject.toml / uv.lock / .python-version (3.12)
├── compose.yml, Dockerfile, .env.example
├── config/                 # settings/{base,dev,test,prod}.py, urls.py, wsgi.py
├── apps/
│   ├── core/               # SiteSettings, base templates context, utils (money, transliteration)
│   ├── catalog/            # models, services/ (writes: products, inventory, images), queries.py (storefront reads),
│   │                       # filters.py (shop query strings), lookup.py (translated slugs), seo.py, images.py (renditions)
│   ├── cart/               # session cart, HTMX endpoints
│   ├── orders/             # Order, OrderItem, checkout flow, status workflow, notifications
│   ├── payments/           # PaymentProvider base, bog.py, tbc.py, Payment model, callbacks
│   ├── promotions/         # Sale prices, PromoCode
│   ├── wishlist/           # cookie/session-based wishlist
│   └── pages/              # About, FAQ, Contact, legal pages, Stone glossary views, ContactMessage, CommissionRequest
├── templates/              # base.html, components/, per-app folders
├── assets/css/             # Tailwind source (main.css with @theme tokens, fonts.css) — outside static/
├── static/                 # brand/ (favicon.svg source + generated .ico/.png), fonts/, vendor/ (htmx, alpine), js/, dist/ (built css, gitignored)
├── scripts/                # tailwind.py (CLI install/watch/build), i18n.py (gettext via Docker), subset_fonts.py, build_favicons.py
├── bin/                    # downloaded Tailwind binary (gitignored)
├── locale/ka/LC_MESSAGES/
└── tests/
```

---

## 5. Data model

Money fields are integers in **tetri**. All content text fields marked 🌐 are translated.

### core
- **SiteSettings** (singleton): intro_text 🌐 (home intro line), pinterest_url, brand_name, logo (optional, text fallback), contact phone/email/address, social links, free_shipping_threshold, `owner_notification_email`, `owner_notification_phone`, announcement_bar 🌐 (optional), maintenance_mode.

### catalog
- **Category**: show_on_home + home_order (home tiles, up to 4); slugs `new` / `sale` are reserved. name 🌐, slug 🌐, description 🌐, **code** (3 capital letters, unique — the SKU prefix, e.g. `NEC`; read-only once the category has products), image, parent (nullable, max depth 2: a parent must be top-level, a category with children stays top-level), sort_order, is_active.
  Seed: Necklaces, Earrings, Bracelets, Vintage, Knitted Headscarves.
- **Stone**: name 🌐, slug 🌐, short_description 🌐, story 🌐 (rich text: origin, meaning, properties), image, color_hex.
- **Material**: name 🌐 (silver 925, brass, glass beads, wool…).
- **Product**:
  - sku (unique, auto-generated `CAT-YYYY-NNNN` from `Category.code`, numbered per category per year via the row-locked `SkuSequence(prefix, year, last_number)` table; may be typed by hand only when creating). **A SKU never changes after creation** — not even when the category changes (read-only in admin; a `pre_save` guard refuses any change). name 🌐, slug 🌐
  - category (FK), stones (M2M Stone), materials (M2M Material)
  - short_description 🌐, description 🌐, story 🌐 ("how it was made"), care_instructions 🌐
  - dimensions 🌐 (free text, e.g. "Length 45 cm + 5 cm extender"), weight_g (optional), hours_to_make (optional)
  - price (tetri; edited in lari in forms via `MoneyField`). `compare_at_price` is **not stored**: the Phase 3 pricing service computes it from active sales, so it can never go stale.
  - status: `draft` | `active` | `hidden` | `sold` (archive) — sold is set automatically when total stock hits 0 and `is_unique=True`
  - is_unique (bool, default True — admin help text explains: unchecked = several identical pieces, stock may be > 1), is_featured, `new_badge` (auto / yes / no) → `is_new` property: auto = **published_at** < 30 days ago (a draft can wait weeks before going live)
  - allow_commission_request (bool, default True)
  - is_preowned (bool, default False — vintage pieces with a previous owner; JSON-LD `UsedCondition`, else `NewCondition`)
  - sold_at (set when status becomes `sold`, cleared when it leaves it; orders the archive)
  - seo_title 🌐, seo_description 🌐
  - created_at, updated_at, published_at
- **ProductVariant**: product (FK), name 🌐 (e.g. "Beige / M"; empty for default), sku_suffix, price_override (nullable), stock (int ≥ 0), reserved (int ≥ 0), sort_order, is_default.
  `available = stock - reserved`.
- **ProductImage**: product, image, alt 🌐 (`alt_ka` required), sort_order, variant (nullable FK — show this image when variant selected; must belong to the same product). **No `is_primary`: the first image by sort_order is the primary image.** On upload: EXIF rotation applied, then all metadata stripped (incl. GPS), RGB JPEG, long side ≤ 2400px, warning (not error) below 2000px. Renditions: square 1:1 crops at 400, 800, 1200, 1800 px in AVIF + WebP (easy-thumbnails), pre-generated by a huey task.
- Slugs: unique **per language** (`slug_ka`, `slug_en` constraints). The untranslated `slug` column follows the active language on save, so it is not unique.
- Rich text (Stone.story, Product.description / story): `RichTextField`, edited with unfold's WYSIWYG, sanitised with nh3 on every save to `p, br, strong, em, a, ul, ol, li, h3` (the editor toolbar offers only these).

### cart (no model — session based)
Session key `cart`: `{variant_id: qty}` + `gift_wrap`, `promo_code`. Cart service resolves prices fresh on every render.

### wishlist
- No account → stored in a signed cookie (list of product IDs, max 50). Heart icon on cards & product page; `/wishlist/` page shows items with availability (sold items shown with "Commission similar" CTA).
- Optional "Share wishlist" link: `/wishlist/s/<signed-token>/` (read-only) — useful for gift hints.

### promotions
- **Sale** (implemented in Phase 1, redesign): name (internal), discount_type (`percent` 1–90 | `fixed` ₾), applies_to_all / products M2M / categories M2M (subcategories included), starts_at, ends_at (empty = open-ended), is_active; home banner fields: show_on_home, banner_title 🌐, banner_subtitle 🌐, banner_image. Best single sale wins per item (no stacking); percent rounds half-up to whole tetri, fixed never below 0. `promotions/services.py` holds the rule in Python (product page, cart, checkout) and as a SQL expression (listings sort and filter by the discounted price); tests keep both identical. Display: old price struck through + new price + "-30%" badge (fixed discounts shown as a percentage). JSON-LD: discounted price, priceValidUntil = ends_at.
- **PromoCode** stays in Phase 3.
- **PromoCode**: code (case-insensitive, unique), discount_type, value, min_order_total, starts_at, ends_at, max_uses, used_count, max_uses_per_email (default 1), applies_to_sale_items (bool), is_active. Validated in cart and re-validated at payment confirmation.

### orders
- **Order**:
  - number (human-friendly, unique: `A-260001` style, sequential per year), public_token (UUID, for status page link)
  - language, status (see §7), payment_status (`pending`|`paid`|`failed`|`refunded`)
  - customer: first_name, last_name, email, phone (Georgian format validation, `+995`),
  - shipping: city, address_line, notes; delivery_method (`courier_tbilisi` | `courier_regions` | `pickup`) — configurable list with prices in `DeliveryOption` model
  - gift: gift_wrap (bool), gift_note (≤ 300 chars), hide_prices_on_slip (bool)
  - subtotal, discount_total, promo_code (FK nullable, snapshot `promo_code_text`), gift_wrap_price, shipping_price, total
  - consent_terms (bool, required), consent_marketing (bool, optional), ip_address, user_agent
  - reservation_expires_at, created_at, paid_at, updated_at
- **OrderItem**: order, variant (FK, PROTECT), snapshots: product_name, variant_name, sku, unit_price, qty, line_total, image_url.
- **OrderStatusHistory**: order, from_status, to_status, changed_by, note, created_at.
- **DeliveryOption**: name 🌐, code, price, free_over_threshold (bool), estimated_days 🌐, is_active, sort_order.

### payments
- **Payment**: order, provider (`bog`|`tbc`), provider_order_id, amount, status, raw_request (JSON), raw_callbacks (JSON list), created_at, updated_at.

### pages
- **HeroSlide** (redesign): image, image_mobile (optional), title 🌐, subtitle 🌐, primary_text 🌐 / primary_link, secondary_text 🌐 / secondary_link (language-neutral paths such as `/shop/new/`, prefixed with the active language at render), sort_order, is_active.
- **Page** (About, Shipping & Returns, Privacy Policy, Terms, Cookie Policy): slug, title 🌐, body 🌐 (rich text), seo fields, `is_legal`.
- **FAQItem**: question 🌐, answer 🌐, group, sort_order.
- **ContactMessage**: name, email/phone, message, created_at, is_handled.
- **CommissionRequest**: reference_product (nullable), name, email, phone, description, budget (optional), reference_image (optional), status (`new`|`in_talks`|`accepted`|`declined`), created_at.

---

## 6. Customer flows

### 6.1 Browse
- **Home** (redesign, follows `docs/design/home-reference.jpeg`): hero slider (HeroSlide: photo, italic headline, subtitle, light "Shop Now" + outlined "Explore Collections", manual "01 / 03" ‹ ›, swipe, **no autoplay**) → intro line between hairlines and the star → 4 square category tiles (name + arrow) → "New Arrivals" (italic heading, hairline, View All, 4 cards) → "Special Offers" banner (only while a show_on_home sale runs; example old → new price is a real discounted piece) → light footer. Phones: hero text over the photo with a dark scrim, tiles 2×2, cards 2 columns, banner stacked.
- **Shop structure** (redesign): `/shop/` (all available pieces), `/shop/<category>/`, `/shop/new/` (is_new, newest first), `/shop/sale/` (running sale) — one view and template; category chips on top (clean category URLs on the shop, `?category=` on New / Sale); stone, material and price in a drawer (right side on desktop, full sheet on phones). **Sold pieces are never listed** (product page stays reachable with "Sold" + commission). Cards: square photo, upright serif name, price, small square cart button; only a sale gets a badge.
- **About** (placeholder until the owner writes it), **Contact** (details from Site settings; form in Phase 2), **Account** ("coming soon", guest checkout, Wishlist (n)).
- **URLs**: English path words in both languages, only slugs translated: `/ka/shop/`, `/ka/shop/<category>/` (subcategories have flat URLs), `/ka/product/<slug>/` (not under the category, so a category change keeps the URL), `/ka/shop/new/`, `/ka/shop/sale/`, `/ka/about/`, `/ka/contact/`, `/ka/account/`. A slug from the other language 301-redirects to the canonical URL (also what makes the language switch work on product pages).
- **Shop / Category**: grid (2 cols mobile, 3 tablet, 4 desktop); filters: category (subcategories on a category page), stone, material, price range in ₾, "available only" (default on; off adds sold / out-of-stock pieces after the buyable ones); sort: newest, price ↑, price ↓. One GET form (works without JS); HTMX swaps the results and the server sends a canonical `HX-Push-Url` (defaults dropped, current-language slugs; slugs from either language accepted). Phones: filters in a full-height sheet with a live "Show N pieces" button. Pagination: "Load more" (12 per page, HTMX, page not pushed to the URL; `?page=N` without JS renders N pages), no infinite scroll.
- **Archive and Stone glossary pages were removed in the redesign.** Stone and Material remain product attributes (shop filters, product accordion).

- **Search**: simple version now (header search → `/shop/?q=`): case-insensitive match on name, short / long description, stone and material names in both languages; noindex. Phase 3: Postgres full-text.

### 6.2 Product page
Gallery (swipe on mobile, thumbnails desktop, tap to fullscreen zoom) · name · price (sale: old struck + new + end date) · availability label ("One of a kind — only 1", "In stock", "Sold") · variant selector (only if >1 variant) · Add to cart · Wishlist heart · accordion: Description / Story / Stones & materials (linked to glossary) / Dimensions & size guide / Care / Delivery & returns · "You may also like" (same stone or category, available only).
Sold product: page stays live (SEO), shows the price **muted next to "Sold"** + Commission CTA, no add-to-cart. The price stays in JSON-LD (`SoldOut`). "Commission a similar piece" links to the request form once it exists (Phase 2), until then `mailto:` the contact e-mail with the SKU in the subject. Gallery: one CSS scroll-snap track (native swipe on phones, thumbnails + arrow keys on desktop), tap/click opens a fullscreen `<dialog>` (pinch-zoom on touch, click-to-zoom with a mouse). Variant pills update price / availability / photo without a request. Accordions are native `<details>`; empty sections are left out; delivery prices of 0 (not yet set) are not shown.

### 6.3 Cart (drawer + page)
- Add to cart opens a **side drawer** (HTMX swap) — no reload. `/cart/` full page also exists.
- Change qty (capped at `available`; unique items qty fixed to 1), remove, promo code apply/remove, gift wrap toggle.
- Totals: subtotal, sale savings, promo discount, gift wrap, shipping (estimate; "free over X ₾" progress hint), total.
- Header cart count updated via HTMX OOB swap / `HX-Trigger`.

### 6.4 Checkout (single page, guest)
Sections: Contact (name, email, phone) → Delivery (method radio + city + address; hidden for pickup) → Gift (wrap, note, hide prices) → Payment (BOG / TBC radio, card logos) → Summary → consent checkboxes (Terms + Privacy required; marketing optional, unchecked by default) → "Pay ₾X".

On submit (`orders.services.place_order`):
1. Re-validate cart, prices, promo code.
2. `transaction.atomic()` + `select_for_update()` on variants: check `available ≥ qty`, increment `reserved`.
3. Create `Order` (status `awaiting_payment`, `reservation_expires_at = now + 15 min`) + items.
4. Create `Payment`, call provider → redirect to hosted page.
If stock is gone: friendly message "Someone just took this piece" + suggest wishlist/similar.

### 6.5 Payment return & confirmation
- Provider **callback** (server-to-server) is the source of truth. Verify signature/status by calling provider API; idempotent.
- On success: atomically `stock -= qty`, `reserved -= qty`, mark product `sold` if unique & 0 left, order → `new`, payment_status `paid`, increment promo `used_count`, enqueue notifications.
- On fail/cancel/expiry: release reservation, order → `cancelled` (payment_status `failed`).
- huey periodic task every minute: expire reservations past `reservation_expires_at` (after one final status check with the provider).
- Return URL → `/order/<public_token>/` showing status (polls via HTMX every 3s while pending, max ~60s).
- Edge case: payment succeeded after reservation expired and item already sold → flag order `needs_attention`, notify owner to refund. Covered by tests.

### 6.6 Order status page
`/order/<public_token>/` — no login; link sent in email/SMS. Shows items, totals, status timeline.

### 6.7 Notifications
| Event | Customer | Owner |
|---|---|---|
| Paid order | Email (+ SMS) with number & status link | Email + SMS |
| Status → shipped | Email + SMS | — |
| Status → delivered | Email (thank you + care tips) | — |
| Cancelled/refunded | Email | Email |
| Contact / Commission request | Auto-reply email | Email |

Emails: HTML (same visual identity, minimal) + plain text, in order language. SMS via a Georgian SMS gateway behind an `SmsBackend` interface (provider TBD; console backend in dev).

---

## 7. Order status workflow

```
awaiting_payment ──paid──► new ──► processing ──► shipped ──► delivered
        │                   │          │             │
        └─fail/expire──► cancelled ◄───┴─────────────┘ (manual, with refund note)
needs_attention (system flag, resolved manually)
```
Every transition logged in `OrderStatusHistory`; allowed transitions enforced in `orders.services.change_status`. Refunds performed manually in bank merchant portal (MVP); owner marks `refunded`.

---

## 8. Payments — BOG & TBC

```python
class PaymentProvider(Protocol):
    code: str
    def create_payment(self, order: Order, return_url: str, callback_url: str) -> CreatedPayment: ...  # returns redirect_url, provider_order_id
    def fetch_status(self, provider_order_id: str) -> PaymentStatus: ...
    def verify_callback(self, request: HttpRequest) -> CallbackData: ...
    def refund(self, payment: Payment, amount: int) -> None: ...  # Phase 3 (optional)
```
- `bog.py`: Bank of Georgia Online Payments API (OAuth2 client credentials → create order → redirect).
- `tbc.py`: TBC E-Commerce (TPay) API (API key + OAuth token → create payment → redirect).
- **Before implementing, read the current official API docs for both banks** (endpoints, signature verification, sandbox credentials). Do not guess endpoints.
- Credentials via env: `BOG_CLIENT_ID`, `BOG_CLIENT_SECRET`, `TBC_API_KEY`, `TBC_CLIENT_ID`, `TBC_CLIENT_SECRET`, sandbox flags.
- Amounts sent in GEL with 2 decimals (convert from tetri in one helper).
- All raw requests/callbacks stored on `Payment` (without secrets) for auditing.
- Fake provider (`payments.providers.fake`) for dev & tests: simulates success/failure/delay.

---

## 9. Design system — "Quiet Atelier"

### 9.1 Personality
Elegant · vintage-modern · warm · handmade · unhurried. Reference feeling: a small atelier with linen, old wood and daylight — an editorial magazine, not a marketplace. **The jewelry is the only loud thing on the page.**

### 9.2 Color tokens (redesign: warm linen palette)
Tokens follow Tailwind v4's `--color-*` convention (`assets/css/main.css` `@theme`).
Ratios are measured against linen / shell; tests enforce them.

| Token | Hex | Use | Ratio |
|---|---|---|---|
| `--color-linen` | `#EFE5DB` | page, header, footer | — |
| `--color-shell` | `#E6D9CC` | photo placeholders, inputs, subtle panels | — |
| `--color-oat` | `#D2C0B2` | light filled buttons, small sale pill | espresso on it 9.5 |
| `--color-sand` | `#DCCFC2` | hairlines, borders | decorative |
| `--color-umber` | `#24140B` | dark sections (Special Offers, hero scrim) | linen on it 14.3 |
| `--color-espresso` | `#2A1A0F` | headings, primary text | 13.5 / 12.1 |
| `--color-cocoa` | `#4A3A2F` | body text | 8.7 / 7.8 |
| `--color-taupe-text` | `#6E5C48` | secondary text | 5.1 / 4.6 |
| `--color-clay-text` | `#6F5B4C` | focus ring, round "-30%" badge background | 5.2 / 4.6 |
| `--color-sold-text` | `#675D55` | "Sold" | 5.2 / 4.6 |
| `--color-error` | `#9E3B2E` | form errors | ≥ 4.5 |
| `--color-clay` | `#A48C7A` | **the accent** (replaces gold): star, hover lines — decorative only | 2.6 |
| `--color-sold` | `#8C7F74` | strike-through lines — decorative only | — |

Rules: never pure white/black (Tailwind's palette is removed). The reference's light-on-clay
badge (2.6:1) is darkened to `clay-text` (5.2:1). **Sale prices must not rely on colour alone**:
old price struck through, new price heavier, screen-reader labels.

### 9.3 Typography
- **Redesign**: h1, h2 and display text use **Cormorant Garamond Italic** (self-hosted, variable 300–500, Latin subset). Georgian has no italic: `:lang(ka)` sets those headings upright in Noto Serif Georgian, and `font-synthesis: none` stops browsers from faking an italic (or bold) — so Georgian words inside English italic headings stay upright too. Card names, nav links and buttons use the upright serif at small sizes.
Georgian-capable fonts are mandatory — test each with: `ხელნაკეთი სამკაულები ბუნებრივი ქვებით`.
- **Display / headings (serif)**: Latin: *Cormorant Garamond* (300–500). Georgian: *Noto Serif Georgian* (300–500). Set via `font-family: "Cormorant Garamond", "Noto Serif Georgian", serif;` — browser picks per-glyph. Tune sizes so both scripts feel balanced (Georgian often needs ~0.9× size) — implemented with `size-adjust: 94%` on the Noto Serif Georgian `@font-face` — at 94% Georgian ascenders align with Cormorant's (chosen in the Phase 0 design review; the styleguide shows 86–94% side by side).
- **Body / UI (sans)**: *FiraGO* (covers Latin + Georgian in one family, 300/400/500).
- Self-host all fonts (woff2, subset), `font-display: swap`, preload the two most used.
  Built by `scripts/subset_fonts.py` from commit-pinned upstream sources into `static/fonts/`
  (committed, with OFL licences): separate Latin and Georgian subsets per family, selected
  by `unicode-range`; variable fonts limited to weights 300–500.
- Scale (fluid, `clamp`): display 48–88px, h1 36–56, h2 28–40, h3 20–26, body 16–17, small 13–14. Line-height body 1.65, headings 1.15. Headings light weight (300–400), never bold. Display holds 48px up to 640px and reaches 88px at 1280px (≈56px at 768, ≈72px at 1024), with `text-wrap: balance`, so tablets never crowd the edges. Container side padding: 16px mobile, 40px from 768px, 48px from 1280px.
- Small uppercase labels (Latin only — Georgian has no case): letter-spacing 0.14em, 12px. For Georgian labels use letter-spacing 0.04em instead. Small Georgian text in FiraGO is set one step lighter: for `:lang(ka)`, labels and button text use weight 400 (not 500) at +1px, buttons keep letter-spacing 0.06em; form labels use 400.
- Prices: sans, tabular figures, `₾` after number: `145 ₾`.

### 9.4 Layout & spacing
- 8px base; section vertical padding 96–160px desktop, 64–96px mobile.
- Max content width 1320px; text columns max 62ch.
- Editorial asymmetry on Home/About: alternating image/text blocks, occasional offset images, one full-bleed image per page max.
- Product images: **square 1:1** everywhere (redesign): matches the reference's tiles, keeps two-column phone grids compact, suits jewelry laid flat; one shooting rule for the owner. Renditions 400–1800px AVIF + WebP. Warm neutral backgrounds; no drop shadows.
- Corners: 0–2px radius (crisp, jewelry-box feel). Buttons rectangular.
- Hairline borders (1px `--sand`) instead of shadows.

### 9.5 Components
- **Header** (redesign): solid linen. Desktop (≥ 1024px): Shop · New Arrivals · Sale · About · Contact (small serif) | ✦ star + brand | KA/EN · search · account · cart (0). Georgian labels set wider: the links show from 1280px there (Tailwind `desk:` variant + DESKTOP_NAV in site.js), and the header uses the shorter "სიახლეები" (msgctxt "main nav"). Phones and tablets: ☰ | brand | search · cart. The search icon opens a field under the bar. No backdrop blur (it would trap the fixed mobile menu inside the header).
- **Mobile menu**: full-screen linen overlay under the header bar, 400ms fade; the bar stays (burger → ✕ in place); the five links in large italic serif (upright in Georgian) fading in 60ms apart; divider; Account, Wishlist (n), KA/EN. Scroll lock, page behind `inert`, focus trap, close on Esc / ✕ / link click, focus returns to the burger; scrolls in phone landscape.
- **Buttons** (redesign): flat, 2px radius, quiet serif label — `btn-light` (oat fill), `btn-outline` (1px), `btn-outline-light` (on photos), `btn-dark` (main action on light pages). Text links: clay underline on hover.
- **Product card** (redesign): square photo (second photo cross-fades on hover, mouse only), upright serif name, price, small square cart button; **no text labels** — only a sale gets a "-30%" pill plus old / new price. "One of a kind — only 1" stays on the product page.
- **Ornament**: one small thin line-art motif (e.g. a stylized bead/stone outline SVG) used as section divider — sparingly.
- **Forms**: underline-style or hairline inputs, generous height (48px), labels above, inline validation.
- **Cart drawer**: slides from right, 420px desktop / full-width mobile.
- **Toasts**: bottom-center, small, auto-dismiss 3s.
- **Icons**: thin stroke (1.25px) — Lucide or Phosphor Light.

### 9.6 Motion
- Durations 300–600ms, easing `cubic-bezier(.2,.6,.2,1)`.
- Reveal on scroll: fade + 12px rise, once, staggered ≤ 80ms.
- Image hover: scale 1.03 over 800ms. No parallax, no bouncing, no auto carousels.
- All disabled under `prefers-reduced-motion`.

### 9.7 Imagery guidelines (for the owner)
Consistent backdrop (linen/cream paper/old wood/stone), daylight, 3 shots per piece minimum: detail, full, worn. Export ≥ 2000px long side. These guidelines go into the admin help text.

### 9.8 Don'ts
Pop-ups on load, countdown timers screaming urgency, stock-pressure tricks ("12 people viewing"), bright red sale banners, stock photos, more than 2 font families, centered long paragraphs.

---

## 10. Admin (owner, mobile-first)

Django Admin + `django-unfold`, tested on a phone.
- **Dashboard**: today's / this week's paid orders and revenue, orders `new` needing action, `needs_attention` alerts, low stock (variants with available ≤ 1, non-unique), new commission requests & messages.
- **Products**: list with thumbnail, status, price, stock; filters (category, status, stone); quick actions: hide/show, mark sold, duplicate product. Inline variants & images (drag-sort, multi-upload, direct-from-phone camera). Translation fields shown as ka/en tabs. Required-field check before `active` (≥ 1 image, ka name, price, category, Georgian alt text on every image); "Show" applies the same check.
- **Admin language**: Georgian by default (language cookie, else `ka`); the header switch flips to English. All project labels, help texts, actions and sections are translated in `locale/ka/`; unfold / Django admin UI strings in `locale_vendor/ka/` (kept separate because `makemessages --no-obsolete` would drop them). Django's `capfirst` is patched (`apps/core/georgian.py`) so Georgian labels never start with a Mtavruli capital.
- **Categories, Stones, Materials, DeliveryOptions, Pages, FAQ**: simple CRUD with sort order.
- **Sales & Promo codes**: CRUD, show usage counts, active/expired filter.
- **Orders**: list (number, date, customer, total, status, payment status) with big tap-friendly status-change action; detail with items + images, gift info, customer contact (tap-to-call / tap-to-email), status history, internal notes; print-friendly **packing slip** (respects hide-prices) — `/admin/orders/<id>/slip/`.
- **Commission requests & Contact messages**: inbox style.
- **SiteSettings**: brand name, logo, contacts, thresholds, announcement bar.
- Security: strong password, 2FA (`django-otp`), admin URL not `/admin/` (env var), login rate limiting (`django-axes`).

---

## 11. Legal, privacy & trust

- Pages (owner provides final text; ship with clearly marked placeholders, **do not invent legal text**): Terms & Conditions, Privacy Policy (in line with Georgia's Law on Personal Data Protection), Shipping & Returns (consumer-protection right of withdrawal — owner to confirm terms with a lawyer), Cookie Policy.
- Checkout consents stored on order with timestamp.
- Cookie banner: essential cookies only by default; analytics only after opt-in (Accept / Reject equal prominence).
- Data minimization: no customer accounts, no card data, order data retention per policy; admin action to anonymize an order's personal data on request.
- Footer (redesign): light linen — Contact · Shipping & returns · FAQ | ✦ | Instagram, Pinterest, Facebook icons (hidden when empty); bottom bar with © + legal entity, Terms · Privacy · Cookies, payment text badges (official marks come with the merchant agreements). Pages that don't exist yet show as plain text.

---

## 12. Non-functional

- **Performance**: LCP < 2.5s on 4G mobile, CLS < 0.1. Responsive `srcset`, lazy-load below fold, preload hero image, cache-control on static, template fragment caching for menus.
- **SEO**: translated slugs, `hreflang` (ka, en, x-default = ka; each language's own slug), canonical (never with filter params; filtered / sorted / paged listings are `noindex,follow`), schema.org `Product` (`Offer`, or `AggregateOffer` for variant price ranges; InStock / OutOfStock / SoldOut; New / UsedCondition), `BreadcrumbList`, `Organization`; XML sitemaps (Phase 2); Open Graph images per product (the processed JPEG original). Titles: `seo_title` or "Name — Category | Brand".
- **Images**: `<picture>` with AVIF + WebP srcsets (400–1800w), fixed width/height (no layout shift), first product photo `fetchpriority=high`, first 4 grid cards eager; picture data cached per file name (Redis in production).
- **Security**: HTTPS, HSTS, CSRF everywhere (HTMX sends token via `hx-headers`), CSP, rate limiting on checkout/promo/contact forms, honeypot on public forms.
- **Reliability**: daily Postgres backups (off-site), Sentry, health-check endpoint, structured logs.
- **Accessibility**: WCAG 2.1 AA, focus states (clay-text ring), alt texts required in admin, semantic HTML.
- **Testing**: unit tests for services (pricing, promos, inventory, status transitions, payment callbacks incl. idempotency & race conditions); view tests for cart/checkout; Playwright smoke test for full purchase with fake provider.

---

## 13. Delivery phases

**Phase 0 — Foundation**: repo, Docker, settings split, i18n setup, Tailwind + fonts + design tokens, base layout (header/footer), CI (ruff + pytest), seed command with demo data.

**Phase 1 — Sellable MVP**: catalog (models, admin, list/filter/detail), **redesign (reference look, home page, New Arrivals, Sale pricing pulled forward from Phase 3, simple search)**, cart drawer, guest checkout, reservations, fake provider → BOG → TBC, order emails, owner notifications, order status page, admin order management + packing slip, legal page placeholders, cookie banner.

**Phase 2 — Brand & polish**: About text, commission request form, FAQ / Contact form, wishlist share link, gift wrapping, SEO & sitemaps, performance pass, accessibility audit. (Stone glossary and Archive were dropped in the redesign.)

**Phase 3 — Growth**: promo codes, optional customer accounts (order history, saved wishlist — guest checkout always stays), SMS notifications, admin dashboard metrics, full-text search (Postgres), analytics (consent-based), anonymization action, optional API refunds.

Each phase ends with: tests green, mobile check at 375/768/1280, Lighthouse ≥ 90 (perf/a11y/SEO), SPEC.md updated.

---

## 14. Open questions (owner to decide)
1. Brand name & logo.
2. Delivery prices per option and free-shipping threshold.
3. Gift wrap price (or free).
4. SMS gateway provider.
5. Return policy terms & legal texts (with a lawyer).
6. Hosting choice (VPS in EU vs local) and domain.
7. BOG and TBC merchant contracts & sandbox credentials.
