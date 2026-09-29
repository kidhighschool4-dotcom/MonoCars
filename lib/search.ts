// Keyword search parsing for /cars?q=… — understands English, Khmer and mixed queries
// such as "sedan for sale Phnom Penh" or "ឡាន Camry លក់ ភ្នំពេញ".

const STOPWORDS = new Set([
  'for', 'sale', 'used', 'car', 'cars', 'the', 'in', 'a', 'an', 'and', 'with', 'buy', 'cheap', 'second', 'hand',
  'ឡាន', 'រថយន្ត', 'លក់', 'ទិញ', 'ថោក', 'មួយទឹក',
])

const LOCATIONS: Record<string, string> = {
  'phnom penh': 'Phnom Penh', 'ភ្នំពេញ': 'Phnom Penh',
  'kandal': 'Kandal', 'កណ្តាល': 'Kandal', 'កណ្ដាល': 'Kandal',
  'siem reap': 'Siem Reap', 'សៀមរាប': 'Siem Reap',
  'battambang': 'Battambang', 'បាត់ដំបង': 'Battambang',
  'sihanoukville': 'Sihanoukville', 'ព្រះសីហនុ': 'Sihanoukville',
  'kampot': 'Kampot', 'កំពត': 'Kampot',
}

const TYPES: Record<string, string> = {
  sedan: 'Sedan', suv: 'SUV', pickup: 'Pickup', hatchback: 'Hatchback',
  mpv: 'MPV (Minivan)', minivan: 'MPV (Minivan)', van: 'MPV (Minivan)',
}

export interface ParsedSearch {
  tokens: string[]
  location?: string
  type?: string
}

export function parseSearch(raw: string | null | undefined): ParsedSearch {
  let q = (raw ?? '').normalize('NFC').replace(/​/g, '').toLowerCase().trim().slice(0, 120)
  const out: ParsedSearch = { tokens: [] }
  if (!q) return out

  for (const [needle, place] of Object.entries(LOCATIONS)) {
    if (q.includes(needle)) {
      out.location ??= place
      q = q.replaceAll(needle, ' ')
    }
  }
  for (const word of q.split(/\s+/)) {
    // Letters, digits and hyphens only — keeps the PostgREST filter free of operators
    const clean = word.replace(/[^\p{L}\p{M}\p{N}-]/gu, '')
    if (!clean || STOPWORDS.has(clean)) continue
    if (TYPES[clean]) {
      out.type ??= TYPES[clean]
      continue
    }
    if (!out.tokens.includes(clean)) out.tokens.push(clean)
  }
  out.tokens = out.tokens.slice(0, 6)
  return out
}
