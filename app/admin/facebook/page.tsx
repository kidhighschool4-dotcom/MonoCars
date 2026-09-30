import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'
import { ExternalLink, MessageSquare, Search, Star, CornerDownRight, CheckCircle2, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import { canViewFacebookData, getServerUser } from '@/lib/auth-server'
import { supabaseAdmin } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const metadata = { title: 'Facebook data | FBM', robots: { index: false, follow: false } }

// ─── Types (mirror supabase/migrations/20260930_facebook_public_posts.sql + buyer_intent_normalized.sql) ───
interface PostRow {
  id: string
  source_post_id: string | null
  source_post_url: string
  canonical_post_url: string
  author_key: string | null
  author_key_version: string | null
  post_text: string | null
  published_at_observed: string | null
  visibility_status: string
  visibility_evidence: string
  search_query: string
  captured_at: string
  adapter_version: string
  content_hash: string
  comments_complete: boolean
  comments_collected_count: number
  replies_collected_count: number
  comment_expansion_rounds: number
  comments_incomplete_reason: string | null
  expires_at: string
  updated_at: string
}
interface CommentRow {
  id: string
  post_id: string
  source_comment_id: string | null
  source_comment_url: string | null
  canonical_comment_url: string | null
  comment_fingerprint: string
  parent_comment_id: string | null
  commenter_key: string | null
  commenter_key_version: string | null
  comment_text: string
  comment_text_normalized: string | null
  buyer_intent: boolean
  buyer_intent_signals: string[]
  matched_phrases: string[]
  intent_classifier_version: string | null
  commented_at_observed: string | null
  comment_type: 'comment' | 'reply'
  visibility_status: string
  captured_at: string
  adapter_version: string
  expires_at: string
}
interface SkipRow {
  id: number
  canonical_post_url: string | null
  search_query: string
  visibility_status: string
  skip_reason: string
  adapter_version: string
  observed_at: string
}
interface ListingRow {
  id: string
  title_raw: string | null
  price_text_raw: string | null
  price_usd: number | null
  location_text_raw: string | null
  source_url: string
  lifecycle_status: string
  status_reason: string | null
  first_captured_at: string
  last_seen_at: string
}

const SIGNAL_LABEL: Record<string, string> = {
  asks_price: 'Asks price',
  makes_offer: 'Makes offer',
  asks_availability: 'Asks if available',
  wants_to_buy: 'Wants to buy',
  asks_contact: 'Wants contact',
  asks_to_see: 'Wants to see / location',
  asks_vehicle_details: 'Asks details',
}

const fmt = (d: string | null) => (d ? new Date(d).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—')
const shortKey = (k: string | null) => (k ? `#${k.slice(0, 8)}` : 'no public profile link')
const fbPath = (u: string | null) => (u ? u.replace('https://www.facebook.com', '') : '—')

function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full', className)}>{children}</span>
}

function Field({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-subtle">{label}</dt>
      <dd className={clsx('text-sm text-ink break-all', mono && 'font-mono text-xs')}>{children}</dd>
    </div>
  )
}

function FbLink({ href, label }: { href: string | null; label?: string }) {
  if (!href) return <span className="text-subtle">—</span>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-brand hover:underline break-all">
      {label ?? fbPath(href)} <ExternalLink className="w-3 h-3 flex-shrink-0" />
    </a>
  )
}

function CommentCard({ c, depth }: { c: CommentRow; depth: number }) {
  return (
    <div className={clsx('rounded-2xl border p-4', c.buyer_intent ? 'border-emerald-200 bg-emerald-50/50' : 'border-line bg-surface', depth > 0 && 'ml-6 md:ml-10')}>
      <div className="flex flex-wrap items-center gap-2">
        {depth > 0 && <CornerDownRight className="w-4 h-4 text-subtle" />}
        <Chip className="bg-paper text-muted">{c.comment_type}</Chip>
        {c.buyer_intent ? (
          <Chip className="bg-emerald-600 text-white"><Star className="w-3 h-3" /> Buyer</Chip>
        ) : (
          <Chip className="bg-paper text-subtle">not buyer</Chip>
        )}
        {c.buyer_intent_signals.map((s) => <Chip key={s} className="bg-emerald-100 text-emerald-800">{SIGNAL_LABEL[s] ?? s}</Chip>)}
        <span className="text-xs text-subtle ml-auto">Commenter {shortKey(c.commenter_key)}</span>
      </div>
      <p className="mt-3 text-[15px] text-ink whitespace-pre-wrap">{c.comment_text}</p>
      {c.matched_phrases.length > 0 && (
        <p className="mt-2 text-xs text-emerald-800">Matched: {c.matched_phrases.map((p) => `“${p}”`).join(', ')}</p>
      )}
      <details className="mt-3 group">
        <summary className="text-xs text-muted cursor-pointer select-none">All fields</summary>
        <dl className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Comment link (canonical)"><FbLink href={c.canonical_comment_url} /></Field>
          <Field label="Comment link (as captured)"><FbLink href={c.source_comment_url} /></Field>
          <Field label="Source comment id" mono>{c.source_comment_id ?? '—'}</Field>
          <Field label="Fingerprint" mono>{c.comment_fingerprint}</Field>
          <Field label="Normalized text" mono>{c.comment_text_normalized ?? '—'}</Field>
          <Field label="Commented (observed)">{fmt(c.commented_at_observed)}</Field>
          <Field label="Captured">{fmt(c.captured_at)}</Field>
          <Field label="Visibility">{c.visibility_status}</Field>
          <Field label="Commenter key" mono>{c.commenter_key ? `${c.commenter_key} (${c.commenter_key_version})` : '—'}</Field>
          <Field label="Classifier" mono>{c.intent_classifier_version ?? '—'}</Field>
          <Field label="Adapter" mono>{c.adapter_version}</Field>
          <Field label="Expires">{fmt(c.expires_at)}</Field>
        </dl>
      </details>
    </div>
  )
}

function Thread({ comments, parentId, depth }: { comments: CommentRow[]; parentId: string | null; depth: number }) {
  const level = comments.filter((c) => c.parent_comment_id === parentId)
  return (
    <div className="space-y-3">
      {level.map((c) => (
        <div key={c.id} className="space-y-3">
          <CommentCard c={c} depth={depth} />
          <Thread comments={comments} parentId={c.id} depth={depth + 1} />
        </div>
      ))}
    </div>
  )
}

export default async function FacebookDataPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await getServerUser()
  if (!user) redirect('/auth?next=/admin/facebook')
  if (!canViewFacebookData(user)) notFound() // don't reveal that this page exists

  const sp = await searchParams
  const tab = (typeof sp.tab === 'string' ? sp.tab : 'buyers') as 'buyers' | 'posts' | 'skipped' | 'marketplace'
  const q = typeof sp.q === 'string' ? sp.q.trim().slice(0, 100) : ''
  const query = typeof sp.query === 'string' ? sp.query : ''
  const buyersOnly = sp.buyers === '1'

  // Always scoped to the signed-in owner (the service-role client bypasses RLS, so filter explicitly).
  const [{ data: postsData }, { data: commentsData }, { data: skipsData }, { data: listingsData }] = await Promise.all([
    supabaseAdmin.from('facebook_public_posts').select('*').eq('owner_id', user.id).order('captured_at', { ascending: false }),
    supabaseAdmin.from('facebook_public_comments').select('*').eq('owner_id', user.id).order('captured_at', { ascending: true }),
    supabaseAdmin.from('facebook_public_post_skips').select('*').eq('owner_id', user.id).order('observed_at', { ascending: false }).limit(300),
    supabaseAdmin.from('listings').select('id,title_raw,price_text_raw,price_usd,location_text_raw,source_url,lifecycle_status,status_reason,first_captured_at,last_seen_at')
      .in('source_platform', ['facebook']).order('last_seen_at', { ascending: false }),
  ])
  const posts = (postsData ?? []) as PostRow[]
  const comments = (commentsData ?? []) as CommentRow[]
  const skips = (skipsData ?? []) as SkipRow[]
  const listings = (listingsData ?? []) as ListingRow[]

  const needle = q.toLowerCase()
  const textHit = (s: string | null | undefined) => !needle || (s ?? '').toLowerCase().includes(needle)
  const postById = new Map(posts.map((p) => [p.id, p]))
  const buyers = comments.filter((c) => c.buyer_intent)
  const uniqueBuyers = new Set(buyers.map((c) => c.commenter_key ?? c.id)).size
  const queries = Array.from(new Set(posts.map((p) => p.search_query))).sort()

  const tabs: { id: typeof tab; label: string; count: number }[] = [
    { id: 'buyers', label: 'Buyer comments', count: buyers.length },
    { id: 'posts', label: 'Posts & all comments', count: posts.length },
    { id: 'skipped', label: 'Skipped posts', count: skips.length },
    { id: 'marketplace', label: 'Marketplace listings', count: listings.length },
  ]
  const href = (next: Record<string, string>) => {
    const p = new URLSearchParams({ tab, ...(q && { q }), ...(query && { query }), ...(buyersOnly && { buyers: '1' }), ...next })
    for (const [k, v] of Array.from(p.entries())) if (!v) p.delete(k)
    return `/admin/facebook?${p.toString()}`
  }

  return (
    <div className="min-h-screen">
      <div className="bg-surface border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-12 pb-8">
          <p className="inline-flex items-center gap-2 text-sm font-medium text-muted mb-3"><span className="w-1.5 h-1.5 rounded-full bg-brand" />Private · {user.email}</p>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink">Facebook data</h1>
          <p className="mt-3 text-muted max-w-3xl">
            Public car posts and their public comments collected by the listing-intelligence crawler. Commenters are shown as
            pseudonymous keys — open a comment link to see it on Facebook.
          </p>

          <dl className="mt-8 grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ['Public posts', posts.length],
              ['Comments + replies', comments.length],
              ['Buyer comments', buyers.length],
              ['Unique buyers', uniqueBuyers],
              ['Skipped posts', skips.length],
            ].map(([l, v]) => (
              <div key={l as string} className="rounded-2xl bg-paper border border-line p-4">
                <dt className="text-sm text-muted">{l}</dt>
                <dd className="text-2xl font-semibold text-ink tnum mt-1">{v as number}</dd>
              </div>
            ))}
          </dl>

          <nav className="mt-8 flex flex-wrap gap-2" aria-label="Sections">
            {tabs.map((t) => (
              <Link key={t.id} href={href({ tab: t.id })}
                className={clsx('px-4 py-2.5 rounded-full text-sm font-medium border transition-colors',
                  tab === t.id ? 'bg-ink text-white border-ink' : 'bg-surface text-ink border-line hover:border-ink')}>
                {t.label} <span className="tnum opacity-70">{t.count}</span>
              </Link>
            ))}
          </nav>

          <form className="mt-4 flex flex-wrap items-center gap-2" action="/admin/facebook">
            <input type="hidden" name="tab" value={tab} />
            <label className="relative flex-1 min-w-[220px] max-w-md">
              <span className="sr-only">Search text</span>
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <input name="q" defaultValue={q} placeholder="Search post or comment text (Khmer or English)"
                className="w-full rounded-full border border-line bg-surface pl-11 pr-4 py-2.5 text-sm focus:outline-none focus:border-brand" />
            </label>
            {(tab === 'posts' || tab === 'buyers') && (
              <select name="query" defaultValue={query} className="rounded-full border border-line bg-surface px-4 py-2.5 text-sm">
                <option value="">All search queries</option>
                {queries.map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            )}
            {tab === 'posts' && (
              <label className="inline-flex items-center gap-2 text-sm text-ink px-2">
                <input type="checkbox" name="buyers" value="1" defaultChecked={buyersOnly} /> Only posts with buyers
              </label>
            )}
            <button className="px-5 py-2.5 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors">Apply</button>
            {(q || query || buyersOnly) && <Link href={`/admin/facebook?tab=${tab}`} className="text-sm text-brand px-2">Clear</Link>}
          </form>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ── Buyer comments ── */}
        {tab === 'buyers' && (
          <div className="space-y-3">
            {buyers
              .filter((c) => textHit(c.comment_text) && (!query || postById.get(c.post_id)?.search_query === query))
              .map((c) => {
                const p = postById.get(c.post_id)
                return (
                  <div key={c.id} className="space-y-2">
                    <CommentCard c={c} depth={0} />
                    <p className="text-xs text-muted pl-4">
                      On post <FbLink href={p?.canonical_post_url ?? null} /> · search “{p?.search_query}” · {fmt(c.captured_at)}
                    </p>
                  </div>
                )
              })}
            {buyers.length === 0 && <p className="text-muted">No buyer comments yet.</p>}
          </div>
        )}

        {/* ── Posts with full threads ── */}
        {tab === 'posts' && (
          <div className="space-y-8">
            {posts
              .filter((p) => (!query || p.search_query === query))
              .filter((p) => !buyersOnly || comments.some((c) => c.post_id === p.id && c.buyer_intent))
              .filter((p) => textHit(p.post_text) || comments.some((c) => c.post_id === p.id && textHit(c.comment_text)))
              .map((p) => {
                const mine = comments.filter((c) => c.post_id === p.id)
                const nBuyers = mine.filter((c) => c.buyer_intent).length
                return (
                  <article key={p.id} className="rounded-3xl bg-surface border border-line overflow-hidden">
                    <div className="p-6 border-b border-line">
                      <div className="flex flex-wrap items-center gap-2">
                        <Chip className="bg-emerald-50 text-emerald-700"><CheckCircle2 className="w-3 h-3" /> {p.visibility_evidence}</Chip>
                        <Chip className="bg-paper text-muted">search: {p.search_query}</Chip>
                        {nBuyers > 0 && <Chip className="bg-emerald-600 text-white"><Star className="w-3 h-3" /> {nBuyers} buyer{nBuyers > 1 ? 's' : ''}</Chip>}
                        {p.comments_complete
                          ? <Chip className="bg-paper text-muted">all comments collected</Chip>
                          : <Chip className="bg-amber-50 text-amber-800"><AlertTriangle className="w-3 h-3" /> incomplete: {p.comments_incomplete_reason}</Chip>}
                      </div>
                      <p className="mt-4 text-ink whitespace-pre-wrap">{p.post_text ?? <span className="text-subtle">(no text)</span>}</p>
                      <dl className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
                        <Field label="Post link (canonical)"><FbLink href={p.canonical_post_url} /></Field>
                        <Field label="Post link (as captured)"><FbLink href={p.source_post_url} /></Field>
                        <Field label="Source post id" mono>{p.source_post_id ?? '—'}</Field>
                        <Field label="Published (observed)">{fmt(p.published_at_observed)}</Field>
                        <Field label="Captured">{fmt(p.captured_at)}</Field>
                        <Field label="Updated">{fmt(p.updated_at)}</Field>
                        <Field label="Comments / replies">{p.comments_collected_count} / {p.replies_collected_count} · {p.comment_expansion_rounds} expansion rounds</Field>
                        <Field label="Author key" mono>{p.author_key ? `${shortKey(p.author_key)} (${p.author_key_version})` : '—'}</Field>
                        <Field label="Visibility">{p.visibility_status}</Field>
                        <Field label="Content hash" mono>{p.content_hash.slice(0, 16)}…</Field>
                        <Field label="Adapter" mono>{p.adapter_version}</Field>
                        <Field label="Expires">{fmt(p.expires_at)}</Field>
                      </dl>
                    </div>
                    <div className="p-6 bg-paper/60">
                      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink mb-4"><MessageSquare className="w-4 h-4" /> {mine.length} comments & replies</h3>
                      {mine.length ? <Thread comments={mine} parentId={null} depth={0} /> : <p className="text-sm text-muted">No public comments.</p>}
                    </div>
                  </article>
                )
              })}
            {posts.length === 0 && <p className="text-muted">No posts yet.</p>}
          </div>
        )}

        {/* ── Skipped ── */}
        {tab === 'skipped' && (
          <div className="rounded-3xl bg-surface border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted border-b border-line">
                <tr>{['When', 'Post', 'Search', 'Status', 'Reason'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {skips.filter((s) => textHit(s.canonical_post_url) || textHit(s.skip_reason)).map((s) => (
                  <tr key={s.id}>
                    <td className="px-4 py-3 whitespace-nowrap">{fmt(s.observed_at)}</td>
                    <td className="px-4 py-3"><FbLink href={s.canonical_post_url} /></td>
                    <td className="px-4 py-3">{s.search_query}</td>
                    <td className="px-4 py-3">{s.visibility_status}</td>
                    <td className="px-4 py-3 font-mono text-xs">{s.skip_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Marketplace ── */}
        {tab === 'marketplace' && (
          <div className="rounded-3xl bg-surface border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted border-b border-line">
                <tr>{['Listing', 'Price', 'Location', 'State', 'Last seen', 'Link'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {listings.filter((l) => textHit(l.title_raw)).map((l) => (
                  <tr key={l.id}>
                    <td className="px-4 py-3">{l.title_raw ?? '—'}</td>
                    <td className="px-4 py-3 tnum whitespace-nowrap">{l.price_text_raw ?? '—'}{l.price_usd ? ` (≈$${l.price_usd.toLocaleString()})` : ''}</td>
                    <td className="px-4 py-3">{l.location_text_raw ?? '—'}</td>
                    <td className="px-4 py-3"><span className="font-mono text-xs">{l.lifecycle_status}</span>{l.status_reason ? <span className="block text-xs text-subtle">{l.status_reason}</span> : null}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{fmt(l.last_seen_at)}</td>
                    <td className="px-4 py-3"><FbLink href={l.source_url} label="Open" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-4 py-3 text-xs text-muted">Screenshots, AI evaluations and approvals for these are on <Link href="/admin/intelligence" className="text-brand">Listing intelligence</Link>.</p>
          </div>
        )}
      </div>
    </div>
  )
}
