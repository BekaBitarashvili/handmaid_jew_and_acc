# Product & Technical Specification — Handmade Jewelry Store

Version 1.0 · Brand name: TBD (use placeholder `{{BRAND}}`, configurable via `SiteSettings`)

---

## 1. Goals

1. Customers browse, fall in love with a piece, and buy it in as few steps as possible — no registration.
2. The owner runs the shop entirely from a phone: products, stock, discounts, orders.
3. The site feels like a small, elegant atelier with a story — not a template store.

### Non-goals (MVP)
Customer accounts/login, marketplace features, multi-currency, automated courier integration,
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
│   ├── catalog/            # Category, Stone, Material, Product, ProductVariant, ProductImage, inventory services
│   ├── cart/               # session cart, HTMX endpoints
│   ├── orders/             # Order, OrderItem, checkout flow, status workflow, notifications
│   ├── payments/           # PaymentProvider base, bog.py, tbc.py, Payment model, callbacks
│   ├── promotions/         # Sale prices, PromoCode
│   ├── wishlist/           # cookie/session-based wishlist
│   └── pages/              # About, FAQ, Contact, legal pages, Stone glossary views, ContactMessage, CommissionRequest
├── templates/              # base.html, components/, per-app folders
├── assets/css/             # Tailwind source (main.css with @theme tokens, fonts.css) — outside static/
├── static/                 # fonts/, vendor/ (htmx, alpine), js/ (alpine components), dist/ (built css, gitignored)
├── scripts/                # tailwind.py (CLI install/watch/build), i18n.py (gettext via Docker), subset_fonts.py
├── bin/                    # downloaded Tailwind binary (gitignored)
├── locale/ka/LC_MESSAGES/
└── tests/
```

---

## 5. Data model

Money fields are integers in **tetri**. All content text fields marked 🌐 are translated.

### core
- **SiteSettings** (singleton): brand_name, logo (optional, text fallback), contact phone/email/address, social links, free_shipping_threshold, `owner_notification_email`, `owner_notification_phone`, announcement_bar 🌐 (optional), maintenance_mode.

### catalog
- **Category**: name 🌐, slug 🌐, description 🌐, image, parent (nullable, max depth 2), sort_order, is_active.
  Seed: Necklaces, Earrings, Bracelets, Vintage, Knitted Headscarves.
- **Stone**: name 🌐, slug 🌐, short_description 🌐, story 🌐 (rich text: origin, meaning, properties), image, color_hex.
- **Material**: name 🌐 (silver 925, brass, glass beads, wool…).
- **Product**:
  - sku (unique, auto-generated `CAT-YYYY-NNNN`, editable), name 🌐, slug 🌐
  - category (FK), stones (M2M Stone), materials (M2M Material)
  - short_description 🌐, description 🌐, story 🌐 ("how it was made"), care_instructions 🌐
  - dimensions 🌐 (free text, e.g. "Length 45 cm + 5 cm extender"), weight_g (optional), hours_to_make (optional)
  - price (tetri), compare_at_price (auto from sale, see promotions)
  - status: `draft` | `active` | `hidden` | `sold` (archive) — sold is set automatically when total stock hits 0 and `is_unique=True`
  - is_unique (bool, default True), is_featured, is_new (auto: created < 30 days, overridable)
  - allow_commission_request (bool, default True)
  - seo_title 🌐, seo_description 🌐
  - created_at, updated_at, published_at
- **ProductVariant**: product (FK), name 🌐 (e.g. "Beige / M"; empty for default), sku_suffix, price_override (nullable), stock (int ≥ 0), reserved (int ≥ 0), sort_order, is_default.
  `available = stock - reserved`.
- **ProductImage**: product, image, alt 🌐, sort_order, is_primary, variant (nullable FK — show this image when variant selected). Generate sizes: 400, 800, 1200, 1800 px, WebP + AVIF.

### cart (no model — session based)
Session key `cart`: `{variant_id: qty}` + `gift_wrap`, `promo_code`. Cart service resolves prices fresh on every render.

### wishlist
- No account → stored in a signed cookie (list of product IDs, max 50). Heart icon on cards & product page; `/wishlist/` page shows items with availability (sold items shown with "Commission similar" CTA).
- Optional "Share wishlist" link: `/wishlist/s/<signed-token>/` (read-only) — useful for gift hints.

### promotions
- **Sale**: name, discount_type (`percent`|`fixed`), value, applies_to (products M2M, categories M2M, or all), starts_at, ends_at, is_active. Best single sale wins per item (no stacking). Product shows old price struck through + new price + optional "ends in" label.
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
- **Page** (About, Shipping & Returns, Privacy Policy, Terms, Cookie Policy): slug, title 🌐, body 🌐 (rich text), seo fields, `is_legal`.
- **FAQItem**: question 🌐, answer 🌐, group, sort_order.
- **ContactMessage**: name, email/phone, message, created_at, is_handled.
- **CommissionRequest**: reference_product (nullable), name, email, phone, description, budget (optional), reference_image (optional), status (`new`|`in_talks`|`accepted`|`declined`), created_at.

---

## 6. Customer flows

### 6.1 Browse
- **Home**: hero (one large photo + one line + CTA) → short brand statement → categories (editorial tiles) → "New pieces" → featured story/collection block → Stone of the month (from Stone glossary) → sale banner (only if active sale) → handmade promise (3 short points) → footer.
- **Shop / Category**: grid (2 cols mobile, 3 tablet, 4 desktop); filters: category, stone, material, price range, "available only" (default on); sort: newest, price ↑, price ↓. Filters update via HTMX with `hx-push-url` (shareable URLs). Pagination: "Load more" button (HTMX), no infinite scroll.
- **Archive** (`/archive/`): sold pieces, grayscale-to-color hover, "Commission a similar piece" CTA.
- **Stone glossary** (`/stones/`, `/stones/<slug>/`): stone story + products with that stone.
- **Search**: simple Postgres full-text (both languages) over name, description, stones, materials.

### 6.2 Product page
Gallery (swipe on mobile, thumbnails desktop, tap to fullscreen zoom) · name · price (sale: old struck + new + end date) · availability label ("One of a kind — only 1", "In stock", "Sold") · variant selector (only if >1 variant) · Add to cart · Wishlist heart · accordion: Description / Story / Stones & materials (linked to glossary) / Dimensions & size guide / Care / Delivery & returns · "You may also like" (same stone or category, available only).
Sold product: page stays live (SEO), shows "Sold" + Commission CTA, no add-to-cart.

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

### 9.2 Color tokens
Tokens follow Tailwind v4's `--color-*` convention (defined in `assets/css/main.css` `@theme`),
so each one is also a utility: `bg-ivory`, `text-espresso`, `border-sand`, …
Contrast ratios are measured against ivory / cream.

**Surfaces**
| Token | Hex | Use |
|---|---|---|
| `--color-ivory` | `#FAF6EF` | Page background |
| `--color-cream` | `#F2EBDF` | Section alternation, cards |
| `--color-sand` | `#E3D5C1` | Borders, dividers, input outlines |

**Text** — every token here passes WCAG AA (≥ 4.5:1) on **both** ivory and cream
| Token | Hex | Use | Ratio |
|---|---|---|---|
| `--color-espresso` | `#2E211A` | Headings, primary buttons, footer bg | 14.5 / 13.1 |
| `--color-cocoa` | `#5A4232` | Body text, secondary buttons | 8.6 / 7.8 |
| `--color-taupe-text` | `#7A6650` | Secondary text, meta, placeholders | 5.1 / 4.6 |
| `--color-gold-text` | `#80653C` | Sale price, focus ring, gold-coloured text | 5.1 / 4.6 |
| `--color-sold-text` | `#72675E` | "Sold" label, disabled text | 5.1 / 4.6 |
| `--color-error` | `#9E3B2E` | Form errors (muted brick, not alarm red) | 6.3 / 5.7 |

**Decorative only** — never for text on light backgrounds (they fail 4.5:1)
| Token | Hex | Use | Ratio |
|---|---|---|---|
| `--color-taupe` | `#A8927A` | Icons next to a text label, ornaments, hover borders | 2.8 / 2.5 |
| `--color-gold` | `#B08D57` | **Accent**: hover underlines, small ornaments | 2.9 / 2.6 |
| `--color-sold` | `#8C7F74` | Sold overlays, strike-through lines | 3.6 / 3.3 |

Rules: never pure white/black (Tailwind's default palette is removed, so only these
tokens exist). Gold covers < 5% of any screen. Text always uses a token from the
"Text" table; `--color-gold` is fine as text only on espresso (5.0:1, footer).
**Sale prices must not rely on color alone**: the old price is struck through and the
new price is set in a heavier weight (500) in `--color-gold-text`, with a visually
hidden "Sale price" / "Original price" label for screen readers.

### 9.3 Typography
Georgian-capable fonts are mandatory — test each with: `ხელნაკეთი სამკაულები ბუნებრივი ქვებით`.
- **Display / headings (serif)**: Latin: *Cormorant Garamond* (300–500). Georgian: *Noto Serif Georgian* (300–500). Set via `font-family: "Cormorant Garamond", "Noto Serif Georgian", serif;` — browser picks per-glyph. Tune sizes so both scripts feel balanced (Georgian often needs ~0.9× size) — implemented with `size-adjust: 90%` on the Noto Serif Georgian `@font-face`.
- **Body / UI (sans)**: *FiraGO* (covers Latin + Georgian in one family, 300/400/500).
- Self-host all fonts (woff2, subset), `font-display: swap`, preload the two most used.
  Built by `scripts/subset_fonts.py` from commit-pinned upstream sources into `static/fonts/`
  (committed, with OFL licences): separate Latin and Georgian subsets per family, selected
  by `unicode-range`; variable fonts limited to weights 300–500.
- Scale (fluid, `clamp`): display 48–88px, h1 36–56, h2 28–40, h3 20–26, body 16–17, small 13–14. Line-height body 1.65, headings 1.15. Headings light weight (300–400), never bold.
- Small uppercase labels (Latin only — Georgian has no case): letter-spacing 0.14em, 12px. For Georgian labels use letter-spacing 0.04em instead.
- Prices: sans, tabular figures, `₾` after number: `145 ₾`.

### 9.4 Layout & spacing
- 8px base; section vertical padding 96–160px desktop, 64–96px mobile.
- Max content width 1320px; text columns max 62ch.
- Editorial asymmetry on Home/About: alternating image/text blocks, occasional offset images, one full-bleed image per page max.
- Product images: consistent aspect ratio **4:5**, warm neutral backgrounds; no drop shadows on images.
- Corners: 0–2px radius (crisp, jewelry-box feel). Buttons rectangular.
- Hairline borders (1px `--sand`) instead of shadows.

### 9.5 Components
- **Header**: transparent over hero, solid `--ivory` on scroll; centered logo wordmark, left nav, right icons (search, wishlist, language, cart with count). Mobile: full-screen menu with large serif links.
- **Buttons**: Primary `--espresso` bg / `--ivory` text; Secondary outlined `--cocoa`; Text link with 1px gold underline that grows from left on hover.
- **Product card**: image (second image crossfades on hover desktop), name (serif), price (sans), small badges in text form ("New", "One of a kind", "−20%") — no colored pill stickers. Wishlist heart top-right, outline icon.
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
- **Products**: list with thumbnail, status, price, stock; filters (category, status, stone); quick actions: hide/show, mark sold, duplicate product. Inline variants & images (drag-sort, multi-upload, direct-from-phone camera). Translation fields shown as ka/en tabs. Required-field check before `active` (≥ 1 image, ka name, price).
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
- Footer: legal entity name / ID, contact, payment logos (BOG, TBC, Visa, Mastercard), language switch.

---

## 12. Non-functional

- **Performance**: LCP < 2.5s on 4G mobile, CLS < 0.1. Responsive `srcset`, lazy-load below fold, preload hero image, cache-control on static, template fragment caching for menus.
- **SEO**: translated slugs, `hreflang`, canonical, schema.org `Product` (with `availability` SoldOut for archive), `BreadcrumbList`, `Organization`; XML sitemaps; Open Graph images per product.
- **Security**: HTTPS, HSTS, CSRF everywhere (HTMX sends token via `hx-headers`), CSP, rate limiting on checkout/promo/contact forms, honeypot on public forms.
- **Reliability**: daily Postgres backups (off-site), Sentry, health-check endpoint, structured logs.
- **Accessibility**: WCAG 2.1 AA, focus states (gold ring), alt texts required in admin, semantic HTML.
- **Testing**: unit tests for services (pricing, promos, inventory, status transitions, payment callbacks incl. idempotency & race conditions); view tests for cart/checkout; Playwright smoke test for full purchase with fake provider.

---

## 13. Delivery phases

**Phase 0 — Foundation**: repo, Docker, settings split, i18n setup, Tailwind + fonts + design tokens, base layout (header/footer), CI (ruff + pytest), seed command with demo data.

**Phase 1 — Sellable MVP**: catalog (models, admin, list/filter/detail), cart drawer, guest checkout, reservations, fake provider → BOG → TBC, order emails, owner notifications, order status page, admin order management + packing slip, legal page placeholders, cookie banner.

**Phase 2 — Brand & polish**: full Home editorial layout, About, Stone glossary, Archive + commission requests, FAQ/Contact, wishlist (+ share link), gift wrapping, SEO & sitemaps, performance pass, accessibility audit.

**Phase 3 — Growth**: sales with end dates, promo codes, SMS notifications, admin dashboard metrics, search, analytics (consent-based), anonymization action, optional API refunds.

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
