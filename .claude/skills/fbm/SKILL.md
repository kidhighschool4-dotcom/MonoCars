---
name: fbm
description: FBM brand guidelines — the car marketplace for Cambodia. Use whenever designing, writing copy, building UI, or generating images/video for FBM (this repo's website), so everything uses the same colours, type, logo, voice and photo style. Trigger on "FBM brand", "on-brand", "brand colours", "make it look like FBM", new pages/components, marketing assets, or Higgsfield image prompts for FBM.
---

# FBM brand

FBM is Cambodia's car marketplace: buy, sell and compare cars, with an **AI price check** on every listing, trusted sellers, and a community of drivers.
Visual direction is inspired by new-wave.io: **black and white with one electric blue**, big confident type, lots of space.

The single source of truth for tokens is `app/globals.css`. If this file and the CSS disagree, the CSS wins — update this file.

## Name
- Always **FBM** (all caps). The wordmark is written `FBM.` with a blue full stop.
- "an FBM account", "FBM's listings" — FBM is said letter by letter.
- Don't invent an expansion of the letters in copy.

## Colour
Use the Tailwind token classes, never raw hex in components.

| Token | Hex | Use |
|---|---|---|
| `ink` | `#0a0a0b` | Text, dark sections, primary dark buttons |
| `ink-2` / `ink-3` | `#17181c` / `#26282e` | Raised surfaces and borders on dark |
| `paper` | `#f5f7fb` | Page background |
| `surface` | `#ffffff` | Cards |
| `line` | `#e3e7ef` | Hairlines and card borders on light |
| `muted` / `subtle` | `#5b6272` / `#8b92a1` | Secondary / tertiary text |
| `brand` | `#3a68ff` | **The one accent**: primary CTA, links, highlights |
| `brand-strong` | `#2a52e0` | Hover/pressed brand |
| `brand-deep` | `#14224f` | Deep navy for gradients |
| `brand-soft` / `brand-tint` | `#eef4ff` / `#cfdcf6` | Tinted fills and borders |

Rules:
- One accent. Blue is for the most important action on a screen and for highlights — not decoration everywhere.
- White text on `brand`; never black text on blue.
- Deal labels are semantic, not brand: Good Deal = emerald, Fair price = sky, Overpriced = rose (see `components/ui/Badge.tsx`).
- Dark sections (`bg-ink`) alternate with light ones to give the page rhythm; add `fbm-grid` and a soft `bg-brand/20 blur` glow for depth.

## Type
- **Parkinsans** for everything Latin (`--font-parkinsans`), **Kantumruy Pro** for Khmer (`--font-kantumruy`, applied automatically via `lang="km"`).
- Headlines: `font-semibold tracking-tight`, tight leading (`leading-[1.05]`). Avoid `font-black`.
- Body: 15–17px, `text-muted` for secondary copy, `leading-relaxed`.
- Numbers (prices, km, stats): add `tnum` so figures line up.
- Eyebrows are sentence case with a small blue dot, not uppercase tracking (see `components/ui/SectionHeading.tsx`).

## Logo
- Component: `components/brand/Logo.tsx` (`<Logo tone="dark|light" size="sm|md|lg" />`), mark only: `<LogoMark />`.
- Mark = blue rounded tile with three white speed lines stepping forward (motion, progress, a price bar going down).
- Keep clear space ≥ the tile's corner radius. Don't recolour the tile, stretch it, or put it on busy photos without a solid backing.

## Shape and components
- Radius: cards `rounded-2xl`/`rounded-3xl`, buttons and chips fully rounded (`rounded-full`).
- Cards: `bg-surface border border-line`, hover lifts via border `brand-tint` + soft navy shadow — no heavy default shadows.
- Buttons: primary `bg-brand text-white`, secondary `bg-ink text-white` (hover → brand), tertiary outlined `border-line`.
- Whole cards are links (bigger tap targets). Minimum tap target 44px.
- Reuse: `SectionHeading`, `PageHeader`, `CarCard`, `EventCard`, `Badge`.

## Voice
- Plain, direct, confident. Short sentences. Say what the user gets.
  - ✅ "Find the right car. Pay the right price."  ❌ "Revolutionising the automotive journey."
- Speak to Cambodian buyers and sellers: USD prices with ≈ Riel, provinces by name, Telegram/WhatsApp as contact.
- A short Khmer line under key headings is welcome (`lang="km"`); keep it accurate — ask a native speaker before shipping new Khmer copy.
- Sentence case for buttons and headings ("Sell your car", not "Sell Your Car").

## Photography and generated imagery
- Real cars in real Cambodian settings: Phnom Penh streets at dusk, riverside, provincial roads, rainy-season reflections, Angkor-area landscapes.
- Moody, high contrast, cool shadows, with blue hour or neon-blue accents that echo `brand`. Avoid warm sepia or gold grading (that was the old MonoCars look).
- Cars are clean, three-quarter front angle, a lot of negative space on one side for headline text.
- No visible licence plates, no brand logos as the subject, no people's faces without consent.

Higgsfield prompt starter (use with the `higgsfield-generate` skill):
> Cinematic photo of a [car] parked on a [Phnom Penh street / riverside / provincial road] at blue hour, cool moody lighting with subtle electric-blue (#3a68ff) accents, wet asphalt reflections, three-quarter front view, lots of empty dark space on the left for text, shallow depth of field, ultra realistic, no licence plate, no text.

## Checklist before shipping UI
- Uses token classes (`ink`, `brand`, `line`…) — no stray hex values.
- One blue primary action per view.
- Readable: body ≥ 15px, contrast AA, focus rings visible (global `:focus-visible` is set).
- Works at 390px wide with 16px gutters and no horizontal scroll.
