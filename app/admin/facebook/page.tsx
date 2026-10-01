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
  screenshot_path?: string | null
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
  screenshot_path?: string | null
  account_type?: 'individual' | 'business' | 'unknown'
  business_page_name?: string | null
  business_page_url?: string | null
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

function Shot({ src, alt, className }: { src?: string; alt: string; className?: string }) {
  if (!src) return null
  return (
    <a href={src} target="_blank" rel="noopener noreferrer" className={clsx('block rounded-xl overflow-hidden border border-line bg-paper', className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL from a private bucket */}
      <img src={src} alt={alt} className="w-full h-auto max-h-[420px] object-contain object-top" />
    </a>
  )
}

function CommentCard({ c, depth, shot }: { c: CommentRow; depth: number; shot?: string }) {
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
      <Shot src={shot} alt="Comment screenshot (name hidden)" className="mt-3 max-w-xl" />
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

function Thread({ comments, parentId, depth, shots }: { comments: CommentRow[]; parentId: string | null; depth: number; shots: Map<string, string | undefined> }) {
  const level = comments.filter((c) => c.parent_comment_id === parentId)
  return (
    <div className="space-y-3">
      {level.map((c) => (
        <div key={c.id} className="space-y-3">
          <CommentCard c={c} depth={depth} shot={shots.get(c.id)} />
          <Thread comments={comments} parentId={c.id} depth={depth + 1} shots={shots} />
        </div>
      ))}
    </div>
  )
}

function LeadCard({ c, p, parent, postShot, commentShot }: {
  c: CommentRow; p: PostRow | undefined; parent?: CommentRow; postShot?: string; commentShot?: string
}) {
  const link = c.canonical_comment_url ?? c.source_comment_url
  return (
    <article className="group flex flex-col rounded-3xl border border-line bg-surface overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      {/* Post screenshot (names hidden) — or a text preview until one is captured */}
      <a href={postShot ?? p?.canonical_post_url ?? '#'} target="_blank" rel="noopener noreferrer"
        className="relative block aspect-[16/10] bg-paper overflow-hidden border-b border-line">
        {postShot ? (
          // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL from a private bucket
          <img src={postShot} alt="Post screenshot (names hidden)" className="w-full h-full object-cover object-top group-hover:scale-[1.01] transition-transform" />
        ) : (
          <div className="absolute inset-0 p-6 flex flex-col justify-between bg-gradient-to-br from-brand-soft to-paper">
            <p className="text-ink text-lg leading-snug line-clamp-5 whitespace-pre-wrap">{p?.post_text ?? '(no post text)'}</p>
            <span className="text-xs text-muted">Screenshot not captured yet</span>
          </div>
        )}
        <span className="absolute top-3 left-3 inline-flex items-center gap-1 rounded-full bg-ink/80 text-white text-[11px] font-semibold px-2.5 py-1 backdrop-blur">
          Facebook post
        </span>
        {p?.published_at_observed && (
          <span className="absolute top-3 right-3 rounded-full bg-white/90 text-ink text-[11px] font-medium px-2.5 py-1">
            {new Date(p.published_at_observed).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        )}
      </a>

      <div className="flex-1 flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip className="bg-emerald-600 text-white"><Star className="w-3 h-3" /> Buyer</Chip>
          {c.buyer_intent_signals.map((s) => <Chip key={s} className="bg-emerald-50 text-emerald-800">{SIGNAL_LABEL[s] ?? s}</Chip>)}
          <span className="ml-auto text-[11px] text-subtle">
            {c.account_type === 'business'
              ? <FbLink href={c.business_page_url ?? null} label={`Business: ${c.business_page_name ?? 'page'}`} />
              : `${shortKey(c.commenter_key)} · identity hidden`}
          </span>
        </div>

        {parent && (
          <div className="flex gap-2 text-sm text-muted">
            <CornerDownRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <p className="line-clamp-2">Replying to: “{parent.comment_text}”</p>
          </div>
        )}

        {/* The buyer's words, big — this is what matters */}
        <blockquote className="relative rounded-2xl rounded-tl-sm bg-emerald-50 border border-emerald-100 px-4 py-3">
          <MessageSquare className="absolute -top-2 -left-2 w-5 h-5 text-emerald-600 bg-surface rounded-full p-0.5" />
          <p className="text-ink text-lg font-medium whitespace-pre-wrap break-words">{c.comment_text}</p>
          <p className="mt-1 text-[11px] text-emerald-800/80">
            {c.commented_at_observed ? `Commented ${fmt(c.commented_at_observed)}` : `Captured ${fmt(c.captured_at)}`}
          </p>
        </blockquote>

        {commentShot && (
          <a href={commentShot} target="_blank" rel="noopener noreferrer" className="block rounded-xl overflow-hidden border border-line bg-paper">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={commentShot} alt="Comment screenshot (name hidden)" className="w-full max-h-48 object-contain object-left-top" />
          </a>
        )}

        {p?.post_text && postShot && <p className="text-sm text-muted line-clamp-2">{p.post_text}</p>}

        <div className="mt-auto pt-2 flex flex-wrap items-center gap-2">
          {link && (
            <a href={link} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-ink text-white text-sm font-semibold px-4 py-2 hover:bg-brand transition-colors">
              Open comment <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          {p && (
            <a href={p.canonical_post_url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full border border-line text-ink text-sm font-medium px-4 py-2 hover:border-ink transition-colors">
              Open post <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          <details className="ml-auto text-xs text-muted">
            <summary className="cursor-pointer select-none">Details</summary>
            <dl className="mt-2 space-y-1">
              <div>Search: “{p?.search_query}”</div>
              <div>Matched: {c.matched_phrases.map((x) => `“${x}”`).join(', ') || '—'}</div>
              <div className="font-mono break-all">{c.comment_fingerprint.slice(0, 24)}…</div>
            </dl>
          </details>
        </div>
      </div>
    </article>
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
  // Lexus RX300 buyers on Facebook from the multi-platform worker (public_social_*, platform = facebook)
  const { data: rxCommentsData } = await supabaseAdmin.from('public_social_comments')
    .select('id,post_id,comment_text,source_comment_url,canonical_comment_url,commenter_key,matched_signals,matched_phrases,comment_fingerprint,' +
      'commented_at_observed,captured_at,screenshot_path,account_type,business_page_name,business_page_url,parent_comment_id')
    .eq('owner_id', user.id).eq('platform', 'facebook').eq('lead_type', 'confirmed_rx300_buyer')
    .order('captured_at', { ascending: false }).limit(200)
  type RxComment = { id: string; post_id: string; comment_text: string; source_comment_url: string | null; canonical_comment_url: string | null
    commenter_key: string | null; matched_signals: string[] | null; matched_phrases: string[] | null; comment_fingerprint: string
    commented_at_observed: string | null; captured_at: string; screenshot_path: string | null; account_type?: string
    business_page_name?: string | null; business_page_url?: string | null; parent_comment_id: string | null }
  const rxComments = (rxCommentsData ?? []) as unknown as RxComment[]
  const rxPostIds = Array.from(new Set(rxComments.map((c) => c.post_id)))
  const { data: rxPostsData } = rxPostIds.length
    ? await supabaseAdmin.from('public_social_posts').select('id,canonical_post_url,post_text,post_title,published_at_observed,search_query,screenshot_path').in('id', rxPostIds)
    : { data: [] }
  const rxPosts = new Map(((rxPostsData ?? []) as { id: string; canonical_post_url: string; post_text: string | null; post_title: string | null
    published_at_observed: string | null; search_query: string; screenshot_path: string | null }[]).map((p) => [p.id, p]))
  const posts = (postsData ?? []) as PostRow[]
  const comments = (commentsData ?? []) as CommentRow[]
  const skips = (skipsData ?? []) as SkipRow[]
  const listings = (listingsData ?? []) as ListingRow[]

  // Screenshots live in a private bucket → short-lived signed URLs (10 min), only for what this tab renders.
  const sign = async (path: string | null | undefined) => {
    if (!path) return undefined
    const { data } = await supabaseAdmin.storage.from('listing-evidence').createSignedUrl(path, 600)
    return data?.signedUrl
  }
  const shotPosts = posts.filter((p) => p.screenshot_path && (tab === 'posts' || tab === 'buyers'))
  const shotComments = comments.filter((c) => c.screenshot_path && (tab === 'posts' || (tab === 'buyers' && c.buyer_intent)))
  const [postShotList, commentShotList] = await Promise.all([
    Promise.all(shotPosts.map(async (p) => [p.id, await sign(p.screenshot_path)] as const)),
    Promise.all(shotComments.map(async (c) => [c.id, await sign(c.screenshot_path)] as const)),
  ])
  const [rxPostShotList, rxCommentShotList] = tab === 'buyers' ? await Promise.all([
    Promise.all(Array.from(rxPosts.values()).filter((p) => p.screenshot_path).map(async (p) => [p.id, await sign(p.screenshot_path)] as const)),
    Promise.all(rxComments.filter((c) => c.screenshot_path).map(async (c) => [c.id, await sign(c.screenshot_path)] as const)),
  ]) : [[], []]
  const rxPostShots = new Map<string, string | undefined>(rxPostShotList)
  const rxCommentShots = new Map<string, string | undefined>(rxCommentShotList)
  const postShots = new Map<string, string | undefined>(postShotList)
  const commentShots = new Map<string, string | undefined>(commentShotList)
  const commentById = new Map(comments.map((c) => [c.id, c]))

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

  const shownBuyers = buyers.filter((c) => textHit(c.comment_text) && (!query || postById.get(c.post_id)?.search_query === query))
  const withShots = posts.filter((p) => p.screenshot_path).length

  return (
    <div className="min-h-screen bg-paper/40">
      <header className="bg-surface border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="inline-flex items-center gap-2 text-xs font-medium text-muted"><span className="w-1.5 h-1.5 rounded-full bg-brand" />Private · {user.email}</p>
              <h1 className="mt-1 text-3xl md:text-4xl font-semibold tracking-tight text-ink">Facebook buyers</h1>
              <p className="mt-1 text-sm text-muted">Public car posts and the people asking to buy in the comments. Names are never stored.</p>
            </div>
            <dl className="flex flex-wrap gap-2">
              {([
                ['Buyers', buyers.length, 'bg-emerald-600 text-white border-emerald-600'],
                ['Unique', uniqueBuyers, ''],
                ['Posts', posts.length, ''],
                ['With screenshot', withShots, ''],
                ['Comments', comments.length, ''],
              ] as const).map(([l, v, cls]) => (
                <div key={l} className={clsx('rounded-2xl border px-4 py-2 min-w-[92px]', cls || 'border-line bg-surface text-ink')}>
                  <dt className={clsx('text-[11px] uppercase tracking-wide', cls ? 'text-white/80' : 'text-muted')}>{l}</dt>
                  <dd className="text-xl font-semibold tnum">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </header>

      {/* Sticky toolbar: sections + search in one row */}
      <div className="sticky top-0 z-20 bg-surface/90 backdrop-blur border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center gap-2">
          <nav className="flex flex-wrap gap-1 rounded-full bg-paper p-1" aria-label="Sections">
            {tabs.map((t) => (
              <Link key={t.id} href={href({ tab: t.id })}
                className={clsx('px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors',
                  tab === t.id ? 'bg-ink text-white' : 'text-ink hover:bg-surface')}>
                {t.label} <span className="tnum opacity-60">{t.count}</span>
              </Link>
            ))}
          </nav>
          <form className="flex flex-1 flex-wrap items-center gap-2 justify-end" action="/admin/facebook">
            <input type="hidden" name="tab" value={tab} />
            <label className="relative flex-1 min-w-[200px] max-w-sm">
              <span className="sr-only">Search text</span>
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <input name="q" defaultValue={q} placeholder="Search Khmer or English…"
                className="w-full rounded-full border border-line bg-surface pl-10 pr-4 py-2 text-sm focus:outline-none focus:border-brand" />
            </label>
            {(tab === 'posts' || tab === 'buyers') && (
              <select name="query" defaultValue={query} className="rounded-full border border-line bg-surface px-3 py-2 text-sm max-w-[200px]">
                <option value="">All searches</option>
                {queries.map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            )}
            {tab === 'posts' && (
              <label className="inline-flex items-center gap-2 text-sm text-ink px-1">
                <input type="checkbox" name="buyers" value="1" defaultChecked={buyersOnly} /> With buyers
              </label>
            )}
            <button className="px-4 py-2 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors">Apply</button>
            {(q || query || buyersOnly) && <Link href={`/admin/facebook?tab=${tab}`} className="text-sm text-brand px-1">Clear</Link>}
          </form>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ── Buyers: screenshot-first cards ── */}
        {tab === 'buyers' && rxComments.length > 0 && !q && !query && (
          <section className="mb-10">
            <div className="flex items-end justify-between gap-3 mb-4">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight text-ink">Lexus RX300 buyers <span className="text-muted tnum">{rxComments.length}</span></h2>
                <p className="text-sm text-muted">People asking to buy an RX300 on Facebook, from the RX300 searches.</p>
              </div>
              <Link href="/admin/social?platform=facebook" className="text-sm font-medium text-brand">All platforms →</Link>
            </div>
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {rxComments.map((c) => {
                const p = rxPosts.get(c.post_id)
                const asComment = { ...c, buyer_intent: true, buyer_intent_signals: c.matched_signals ?? [], matched_phrases: c.matched_phrases ?? [],
                  account_type: (c.account_type ?? 'unknown') as CommentRow['account_type'] } as unknown as CommentRow
                const asPost = p ? ({ ...p, post_text: [p.post_title, p.post_text].filter(Boolean).join('\n') || null } as unknown as PostRow) : undefined
                return <LeadCard key={c.id} c={asComment} p={asPost} postShot={rxPostShots.get(c.post_id)} commentShot={rxCommentShots.get(c.id)} />
              })}
            </div>
            <h2 className="mt-12 mb-4 text-lg font-semibold text-ink">Other car buyers (earlier general crawl)</h2>
          </section>
        )}
        {tab === 'buyers' && (
          <>
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {shownBuyers.map((c) => (
                <LeadCard key={c.id} c={c} p={postById.get(c.post_id)}
                  parent={c.parent_comment_id ? commentById.get(c.parent_comment_id) : undefined}
                  postShot={postShots.get(c.post_id)} commentShot={commentShots.get(c.id)} />
              ))}
            </div>
            {shownBuyers.length === 0 && <p className="text-muted">No buyer comments{q || query ? ' match these filters' : ' yet'}.</p>}
          </>
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
                      <div className={clsx('mt-4 grid gap-4', postShots.get(p.id) && 'md:grid-cols-[minmax(0,1fr)_320px]')}>
                        <p className="text-ink whitespace-pre-wrap">{p.post_text ?? <span className="text-subtle">(no text)</span>}</p>
                        <Shot src={postShots.get(p.id)} alt="Post screenshot (names hidden)" />
                      </div>
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
                      {mine.length ? <Thread comments={mine} parentId={null} depth={0} shots={commentShots} /> : <p className="text-sm text-muted">No public comments.</p>}
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
