# MonoCars — Design & Quality Feedback Log

> **Superseded (2026-09-30):** the site was rebranded to **FBM** with a black / white / electric-blue design system.
> The gold + deep-red + cream palette below no longer applies. Follow `.claude/skills/fbm/SKILL.md` and the tokens in `app/globals.css`.
> The rounds below are kept as history.

> This file is maintained by the review agent. Each iteration appends a new round of findings.
> Frontend agents must read this file before making UI changes and apply ALL open items.

---

## Round 1 — 2026-04-07 (Initial audit)

### 🐛 Bugs / Technical Issues

| # | File | Issue | Severity |
|---|------|--------|----------|
| B1 | `components/layout/Footer.tsx:95` | Copyright year hardcoded as `2024`. Use `new Date().getFullYear()` | Medium |
| B2 | `lib/priceEstimation.ts:15` | `2024 - year` hardcoded. Use `new Date().getFullYear() - year` | Low |
| B3 | `components/cars/PriceAnalysis.tsx:15` | `gaugePercent` variable defined but never used — dead code | Low |
| B4 | `app/community/page.tsx:11` | Trending topic "Import Taxes 2024" is stale. Change to "Import Taxes 2026" | Low |
| B5 | `components/cars/[id]/page.tsx` (gallery) | Thumbnail images don't update the main image on click — gallery is static markup only | High |

---

### 🇰🇭 Cambodia Identity / Cultural Vibe Issues

These are the most important items. The platform currently feels like a generic international car site.
It needs more soul — more Cambodia.

| # | Location | Issue | Fix |
|---|----------|--------|-----|
| C1 | `Hero.tsx` | No car imagery — pure dark background with a tiny crosshatch pattern. Feels empty for a car platform. | Add a stunning car image as hero background (use a high-quality Unsplash dark car photo overlaid with gradient). The hero must make you feel like Cambodia's premium car world. |
| C2 | All pages | No Khmer script anywhere. The brand "MonoCars" should have a subtle Khmer translation "ម៉ូណូការ" (in footer at minimum, and optionally in hero). Even one line in Khmer makes the product feel Cambodian. | Add `<span lang="km" className="font-normal text-xs text-gray-400">ម៉ូណូការ</span>` below the logo in Footer and Hero label. |
| C3 | `Footer.tsx` | No social media links. Facebook, Telegram, and Instagram are the primary social channels in Cambodia. | Add Facebook, Telegram, Instagram icon links in footer. |
| C4 | `cars/[id]/page.tsx` | Contact seller shows only a phone number (tel: link). In Cambodia, **WhatsApp and Telegram** are how people actually contact sellers. | Add WhatsApp button: `https://wa.me/[phone]` and Telegram button alongside the call button. |
| C5 | `CarCard.tsx`, `cars/[id]/page.tsx` | Prices shown in USD only. Cambodia uses both USD and KHR (Riel). | Below each price show `≈ ៛{(price * 4100).toLocaleString()}` in a muted smaller font. Use rate 1 USD ≈ 4,100 KHR (approximate). |
| C6 | `Hero.tsx` | The "Cambodia First" pill label is the only cultural marker on the entire hero. | Upgrade the hero background to use a premium car image (dark/moody). Add a subtle Angkor-inspired SVG geometric border element. Add the Cambodia flag emoji 🇰🇭 next to "Cambodia First" label. |
| C7 | `Footer.tsx` | Footer bottom text says only "Cambodia's Premier Car Intelligence Platform" which is fine, but no Khmer text. | Add a line: `<p className="text-xs text-gray-600 mt-1">ផ្ទាំងឆ្លាតវៃខ្មែរ</p>` ("Khmer Smart Platform" in Khmer) |
| C8 | Homepage — missing section | No "Why MonoCars?" / trust-building section. | Add a simple 3-column "Why trust us" section between FeaturedCars and FeaturedEvents: "Smart Pricing", "Verified Listings", "Cambodia Community" — each with a gold icon. |
| C9 | `events/page.tsx` | The event cards use car photo Unsplash IDs that look like racing/sports cars, not actual event photos. | Swap event images to use motor show / event / gathering themed photos from Unsplash. |
| C10 | Header | Header logo icon is a generic "M" in a gold circle — no Khmer or car symbolism. | Keep the circle but add a subtle angular car silhouette or Angkor motif inside the M, using SVG. |

---

### 🎨 Design Quality Issues

| # | Location | Issue | Fix |
|---|----------|--------|-----|
| D1 | `FeaturedEvents` section | Has `bg-white` while other homepage sections have `bg-[#F8F5F0]`. The abrupt white block looks jarring on the cream background. | Change to `bg-[#F8F5F0]` or add a proper visual separator instead. |
| D2 | `Hero.tsx` | Stats row at bottom has items that look cramped on mobile. The separator pipe `w-px h-4` is positioned with `ml-6` but it's placed after the icon+text not between items. | Fix stats row layout: use a proper `divide-x` or correctly placed separators. |
| D3 | `CarCard.tsx` | "View Details" button uses `bg-[#1A1A1A]` which inverts to `hover:bg-[#CBA135]`. Good interaction but the button is full width inside a card — on wide cards this looks heavy. | Make the button slightly less aggressive visually. Try outlined style instead: `border-2 border-[#1A1A1A] text-[#1A1A1A] hover:bg-[#1A1A1A] hover:text-white`. |
| D4 | `Header.tsx` | Mobile nav uses a generic `<Car />` icon for ALL nav items. Very repetitive and confusing. | Use contextual icons: `Car` for Cars, `Calendar` for Events, `Users` for Community, `PlusCircle` for Submit Listing. |
| D5 | `app/cars/page.tsx` | Suspense fallback is a bare centered text "Loading listings..." — no spinner, no skeleton. | Use a proper loading skeleton: 6 gray placeholder cards in a grid. |
| D6 | `PriceAnalysis.tsx` | The gauge gradient goes `from-emerald-400 via-amber-400 to-red-500`. The marker position calculation `(askingPrice / estimatedValue) * 50` means at market value (ratio=1.0) the marker sits at 50% which appears mid-amber, not in the center of the gauge. | Fix: make the gradient center (50%) represent fair value. Use `((askingPrice / estimatedValue) - 0.5) * 100` clamped to 0-100 so that ratio=0.5 (50% below market) = 0%, ratio=1.0 = 50%, ratio=1.5 (50% above) = 100%. |
| D7 | All page headers | All inner pages (events, community) use the exact same dark header design (`bg-[#1A1A1A] py-12`). | Give each page a slightly different treatment — Events could use a photo background, Community could add member avatars, Cars listing page header could show the filter count prominently. |
| D8 | `app/submit/page.tsx` | Need to verify this page has proper form validation UX, success state, and real-time price preview working correctly. | Read and audit submit page separately. |
| D9 | `components/community/PostCard.tsx` | Not yet read. Need to verify it handles: no-image posts, long text truncation, comment display, avatar fallback. | Read and audit separately. |
| D10 | `app/auth/page.tsx` | Not yet read. Verify it has toggle between sign in/sign up, proper error states, and consistent styling. | Read and audit separately. |

---

### ✅ What's Working Well (Keep These)

- Gold (#CBA135) / Deep Red (#7A1E1E) / Cream (#F8F5F0) color scheme — correct and premium
- CarCard hover animations (shadow + lift + image scale) — keep exactly as-is
- Footer gradient border (red → gold → red) — beautiful Cambodian touch, keep it
- Mock data with real Cambodian names, cities, and cultural context — excellent
- Price Analysis gauge component — concept is great, just fix the math
- Community post topics (EV debate, import taxes, marketplace scams) — very authentic
- CTASection with dark + red gradient cards — premium look, keep it
- Header sticky backdrop-blur — keep it
- Khmer seller names in listings (Sophea Rin, Bopha Chan, etc.) — very authentic, keep all

---

## Iteration Checklist for Frontend Agent

When applying fixes from this file, implement in this priority order:

### Priority 1 — Cambodia Vibe (do these first)
- [x] C1: Add hero car background image with gradient overlay ✅ 2026-04-07
- [x] C2: Add Khmer text "ម៉ូណូការ" to footer and hero ✅ 2026-04-07
- [x] C3: Add Facebook, Telegram, Instagram to footer ✅ 2026-04-07
- [x] C4: Add WhatsApp + Telegram contact buttons on car detail page ✅ 2026-04-07
- [x] C5: Add KHR price display below USD prices ✅ 2026-04-07

### Priority 2 — Bugs (fix these second)
- [x] B1: Fix copyright year to be dynamic ✅ 2026-04-07
- [x] B2: Fix hardcoded 2024 in price estimation ✅ 2026-04-07
- [x] B3: Remove unused `gaugePercent` variable ✅ 2026-04-07
- [x] B4: Update "Import Taxes 2024" → "Import Taxes 2026" ✅ 2026-04-07
- [x] B5: Make car detail gallery thumbnails interactive (click to swap main image) ✅ 2026-04-07 — extracted to ImageGallery.tsx client component

### Priority 3 — Design Polish
- [x] D1: Fix FeaturedEvents background color inconsistency ✅ 2026-04-07 — changed to #F0EDE6
- [x] D4: Fix mobile nav icons to be contextual ✅ 2026-04-07
- [ ] D6: Fix gauge meter math — marker at market value should sit at center of green/red gradient
- [x] C8: Add "Why MonoCars?" trust section to homepage ✅ 2026-04-07 — WhyMonoCars.tsx created
- [ ] D5: Add loading skeleton for cars page — CarsClient fallback currently shows plain text

---

*Next review: After Priority 1 + 2 fixes are applied, run another audit to verify and identify new issues.*
