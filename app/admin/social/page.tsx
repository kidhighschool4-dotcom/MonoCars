import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'
import { ExternalLink, CornerDownRight, Star, AlertTriangle, CheckCircle2, Search, Eye, Building2, CircleDot, Clock } from 'lucide-react'
import clsx from 'clsx'
import { canViewFacebookData, getServerUser } from '@/lib/auth-server'
import { supabaseAdmin } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const metadata = { title: 'RX300 buyers | FBM', robots: { index: false, follow: false } }

// Worker adapter name → stored `platform` value + label (mirrors intelligence/config/platforms_v1.json)
const ADAPTERS = [
  { id: 'facebook_public_posts', platform: 'facebook', label: 'Facebook posts', tier: 1 },
  { id: 'facebook_marketplace', platform: 'facebook_marketplace', label: 'FB Marketplace', tier: 1 },
  { id: 'tiktok', platform: 'tiktok', label: 'TikTok', tier: 1 },
  { id: 'instagram', platform: 'instagram', label: 'Instagram', tier: 1 },
  { id: 'reddit', platform: 'reddit', label: 'Reddit', tier: 1 },
  { id: 'youtube', platform: 'youtube', label: 'YouTube', tier: 1 },
  { id: 'x', platform: 'x', label: 'X', tier: 1 },
  { id: 'threads', platform: 'threads', label: 'Threads', tier: 1 },
  { id: 'telegram', platform: 'telegram', label: 'Telegram', tier: 2 },
  { id: 'pinterest', platform: 'pinterest', label: 'Pinterest', tier: 2 },
  { id: 'bluesky', platform: 'bluesky', label: 'Bluesky', tier: 2 },
  { id: 'mastodon', platform: 'mastodon', label: 'Mastodon', tier: 2 },
  { id: 'forums', platform: 'forum', label: 'Forums', tier: 2 },
  { id: 'kh_classifieds', platform: 'classifieds', label: 'KH classifieds', tier: 2 },
  { id: 'search_engine', platform: 'web', label: 'Search engines', tier: 3 },
  { id: 'web_sites', platform: 'web', label: 'Dealer sites & blogs', tier: 3 },
] as const
const PLATFORM_LABEL: Record<string, string> = {
  facebook: 'Facebook', facebook_marketplace: 'FB Marketplace', tiktok: 'TikTok', instagram: 'Instagram', reddit: 'Reddit',
  youtube: 'YouTube', x: 'X', threads: 'Threads', telegram: 'Telegram', pinterest: 'Pinterest', bluesky: 'Bluesky',
  mastodon: 'Mastodon', forum: 'Forums', classifieds: 'Classifieds', web: 'Web',
}
const LEAD = {
  confirmed_rx300_buyer: { text: 'RX300 buyer', cls: 'bg-emerald-600 text-white' },
  potential_rx300_fit: { text: 'Potential RX300 fit', cls: 'bg-brand text-white' },
  seller_or_dealer: { text: 'Seller / dealer', cls: 'bg-paper text-ink' },
  irrelevant: { text: 'Irrelevant', cls: 'bg-paper text-subtle' },
} as const
type LeadType = keyof typeof LEAD
const STATE: Record<string, { text: string; cls: string }> = {
  ok: { text: 'Running', cls: 'bg-emerald-50 text-emerald-700' },
  budget_exhausted: { text: 'Budget reached', cls: 'bg-amber-50 text-amber-800' },
  misconfigured: { text: 'Not configured', cls: 'bg-paper text-muted' },
  login_required: { text: 'Needs login', cls: 'bg-amber-50 text-amber-800' },
  challenged: { text: 'CAPTCHA', cls: 'bg-rose-50 text-rose-700' },
  blocked: { text: 'Blocked', cls: 'bg-rose-50 text-rose-700' },
  rate_limited: { text: 'Rate limited', cls: 'bg-amber-50 text-amber-800' },
  error: { text: 'Failing', cls: 'bg-rose-50 text-rose-700' },
}

interface Post {
  id: string; platform: string; source_content_type: string; source_post_id: string | null; canonical_post_url: string
  document_title: string | null; post_title: string | null; post_text: string | null; hashtags: string[]
  published_text_displayed: string | null; published_at_observed: string | null; engagement: Record<string, string>
  visibility_evidence: string; search_query: string; search_url: string | null; captured_at: string; adapter_version: string
  completeness_status: string; comments_collected_count: number; replies_collected_count: number; comment_expansion_rounds: number
  rejected_comment_count: number; screenshot_path: string | null; expires_at: string
  lead_type?: LeadType | null; organization_id?: string | null; source_adapter?: string | null
}
interface Comment {
  id: string; post_id: string; platform: string; parent_comment_id: string | null; comment_type: 'comment' | 'reply'
  source_comment_url: string | null; comment_url_available: boolean; comment_fingerprint: string; commenter_key: string | null
  commenter_key_scope: string; comment_text: string; displayed_timestamp: string | null; captured_at: string
  buyer_intent_score: number; buyer_intent_label: string; intent_type: string | null; detected_language: string | null
  matched_phrases: string[]; negative_signals: string[]; spam_score: number; intent_reason: string | null
  needs_human_review: boolean; screenshot_path: string | null
  lead_type?: LeadType | null; lead_use_case?: string | null; lead_confidence?: number | null; lead_reasons?: string[]
  lead_needs_review?: boolean; rx300_mentioned?: boolean; is_post_author?: boolean
  account_type?: 'individual' | 'business' | 'unknown'; business_page_name?: string | null; business_page_url?: string | null
  business_page_screenshot?: string | null
}
function AccountChip({ c, bizShot }: { c: Comment; bizShot?: string }) {
  if (c.account_type === 'business') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Chip className="bg-ink text-white"><Building2 className="w-3 h-3" /> Business</Chip>
        <Ext href={c.business_page_url} label={c.business_page_name ?? 'business page'} />
        {bizShot && <a href={bizShot} target="_blank" rel="noopener noreferrer" className="text-xs text-brand underline">page screenshot</a>}
      </span>
    )
  }
  return <Chip className="bg-paper text-muted">{c.account_type === 'individual' ? 'Individual' : 'Unknown'} · identity hidden</Chip>
}
interface Status {
  platform: string; enabled: boolean; state: string; detail: string | null; consecutive_failures: number
  circuit_open_until: string | null; last_success_at: string | null; last_run_at: string | null; next_run_at: string | null
}
interface Org { id: string; platform: string; name: string; url: string | null; kind: string; evidence: string; last_seen_at: string }

const fmt = (d: string | null | undefined) => (d ? new Date(d).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—')
const missingTable = (e: { message: string } | null) => !!e && /does not exist|schema cache|Could not find/i.test(e.message)

function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full', className)}>{children}</span>
}
function Ext({ href, label }: { href: string | null | undefined; label?: string }) {
  if (!href) return <span className="text-subtle">—</span>
  return <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-brand hover:underline break-all">{label ?? href} <ExternalLink className="w-3 h-3 flex-shrink-0" /></a>
}
function Field({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return <div className="min-w-0"><dt className="text-[11px] uppercase tracking-wide text-subtle">{label}</dt><dd className={clsx('text-sm text-ink break-all', mono && 'font-mono text-xs')}>{children}</dd></div>
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
function leadOf(c: Comment): LeadType {
  if (c.lead_type) return c.lead_type
  return c.buyer_intent_label === 'not_buyer_intent' ? 'irrelevant' : 'potential_rx300_fit' // before lead columns exist
}

function PostPreview({ p, shot }: { p: Post; shot?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Chip className="bg-brand-soft text-brand">{PLATFORM_LABEL[p.platform] ?? p.platform}</Chip>
        {p.lead_type && <Chip className={LEAD[p.lead_type].cls}>post: {LEAD[p.lead_type].text}</Chip>}
        <span>search “{p.search_query}”</span>
        <span>· {p.published_text_displayed ?? fmt(p.published_at_observed ?? p.captured_at)}</span>
        <span className="ml-auto"><Ext href={p.canonical_post_url} label="Open post" /></span>
      </div>
      <div className={clsx('mt-3 grid gap-4', shot && 'md:grid-cols-[minmax(0,1fr)_280px]')}>
        <div className="min-w-0">
          {(p.post_title || p.document_title) && <p className="font-semibold text-ink">{p.post_title ?? p.document_title}</p>}
          <p className="text-sm text-ink whitespace-pre-wrap line-clamp-[8]">{p.post_text ?? <span className="text-subtle">(no text)</span>}</p>
          {p.hashtags.length > 0 && <p className="mt-2 flex flex-wrap gap-1.5">{p.hashtags.slice(0, 8).map((h) => <Chip key={h} className="bg-paper text-muted">{h}</Chip>)}</p>}
        </div>
        <Shot src={shot} alt="Post screenshot (names hidden)" />
      </div>
    </div>
  )
}

function CommentCard({ c, shot, depth, bizShot }: { c: Comment; shot?: string; depth: number; bizShot?: string }) {
  const lt = leadOf(c)
  return (
    <div className={clsx('rounded-2xl border p-4', lt === 'confirmed_rx300_buyer' ? 'border-emerald-200 bg-emerald-50/50'
      : lt === 'potential_rx300_fit' ? 'border-brand/30 bg-brand-soft/60' : 'border-line bg-surface', depth > 0 && 'ml-6 md:ml-10')}>
      <div className="flex flex-wrap items-center gap-2">
        {depth > 0 && <CornerDownRight className="w-4 h-4 text-subtle" />}
        <Chip className="bg-paper text-muted">{c.comment_type}</Chip>
        <Chip className={LEAD[lt].cls}>{(lt === 'confirmed_rx300_buyer' || lt === 'potential_rx300_fit') && <Star className="w-3 h-3" />}{LEAD[lt].text}{c.lead_confidence != null ? ` · ${c.lead_confidence}` : ''}</Chip>
        {c.lead_use_case && <Chip className="bg-paper text-ink">{c.lead_use_case === 'taxi' ? 'Taxi use' : 'Family car'}</Chip>}
        <Chip className="bg-paper text-ink">intent {c.buyer_intent_score}{c.intent_type ? ` · ${c.intent_type.replaceAll('_', ' ')}` : ''}</Chip>
        {(c.lead_needs_review || c.needs_human_review) && <Chip className="bg-amber-50 text-amber-800"><Eye className="w-3 h-3" /> check</Chip>}
        <AccountChip c={c} bizShot={bizShot} />
        <span className="text-xs text-subtle ml-auto">{c.displayed_timestamp ?? ''} · {c.commenter_key ? `#${c.commenter_key.slice(0, 8)}` : 'comment-only id'}</span>
      </div>
      <p className="mt-3 text-[15px] text-ink whitespace-pre-wrap">{c.comment_text}</p>
      {!!c.lead_reasons?.length && <p className="mt-1 text-xs text-muted">Why: {c.lead_reasons.join(', ')}</p>}
      <Shot src={shot} alt="Comment screenshot (name hidden)" className="mt-3 max-w-xl" />
      <details className="mt-3">
        <summary className="text-xs text-muted cursor-pointer select-none">All fields</summary>
        <dl className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Comment link">{c.comment_url_available ? <Ext href={c.source_comment_url} /> : 'post link + platform comment id'}</Field>
          <Field label="Fingerprint" mono>{c.comment_fingerprint}</Field>
          <Field label="Language">{c.detected_language ?? '—'}</Field>
          <Field label="Matched phrases">{c.matched_phrases.length ? c.matched_phrases.map((p) => `“${p}”`).join(', ') : '—'}</Field>
          <Field label="Negations">{c.negative_signals.length ? c.negative_signals.join(', ') : '—'}</Field>
          <Field label="Spam score">{c.spam_score}</Field>
          <Field label="Key scope">{c.commenter_key_scope}</Field>
          <Field label="Captured">{fmt(c.captured_at)}</Field>
        </dl>
      </details>
    </div>
  )
}

export default async function SocialDataPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await getServerUser()
  if (!user) redirect('/auth?next=/admin/social')
  if (!canViewFacebookData(user)) notFound()

  const sp = await searchParams
  const str = (k: string) => (typeof sp[k] === 'string' ? (sp[k] as string) : '')
  const view = (['leads', 'posts', 'organizations', 'skipped'].includes(str('view')) ? str('view') : 'leads') as 'leads' | 'posts' | 'organizations' | 'skipped'
  const platform = str('platform') in PLATFORM_LABEL ? str('platform') : ''
  const lead = ['confirmed_rx300_buyer', 'potential_rx300_fit', 'seller_or_dealer', 'buyers', 'all'].includes(str('lead')) ? str('lead') : 'confirmed_rx300_buyer'
  const q = str('q').trim().slice(0, 100).toLowerCase()

  const postsQ = supabaseAdmin.from('public_social_posts').select('*').eq('owner_id', user.id).order('captured_at', { ascending: false }).limit(500)
  const commentsQ = supabaseAdmin.from('public_social_comments').select('*').eq('owner_id', user.id).order('captured_at', { ascending: false }).limit(3000)
  const skipsQ = supabaseAdmin.from('public_social_post_skips').select('*').eq('owner_id', user.id).order('observed_at', { ascending: false }).limit(200)
  const [{ data: postsData, error }, { data: commentsData }, { data: skipsData }, statusRes, orgRes] = await Promise.all([
    platform ? postsQ.eq('platform', platform) : postsQ,
    platform ? commentsQ.eq('platform', platform) : commentsQ,
    platform ? skipsQ.eq('platform', platform) : skipsQ,
    supabaseAdmin.from('social_platform_status').select('*').eq('owner_id', user.id),
    supabaseAdmin.from('public_social_organizations').select('*').eq('owner_id', user.id).order('last_seen_at', { ascending: false }).limit(300),
  ])
  const tablesMissing = missingTable(error)
  const leadsMissing = missingTable(statusRes.error)
  const posts = (postsData ?? []) as Post[]
  const comments = (commentsData ?? []) as Comment[]
  const skips = (skipsData ?? []) as { id: number; platform: string; canonical_post_url: string | null; search_query: string; skip_reason: string; observed_at: string }[]
  const status = new Map(((statusRes.data ?? []) as Status[]).map((s) => [s.platform, s]))
  const orgs = (orgRes.data ?? []) as Org[]
  const postById = new Map(posts.map((p) => [p.id, p]))
  const commentById = new Map(comments.map((c) => [c.id, c]))
  const postsPerPlatform: Record<string, number> = {}
  for (const p of posts) postsPerPlatform[p.platform] = (postsPerPlatform[p.platform] ?? 0) + 1

  const leadMatch = (c: Comment) => {
    const lt = leadOf(c)
    if (lead === 'all') return true
    if (lead === 'buyers') return lt === 'confirmed_rx300_buyer' || lt === 'potential_rx300_fit'
    return lt === lead
  }
  const leads = comments.filter((c) => leadMatch(c) && (!q || c.comment_text.toLowerCase().includes(q)))
    .sort((a, b) => (leadOf(a) === 'confirmed_rx300_buyer' ? 0 : 1) - (leadOf(b) === 'confirmed_rx300_buyer' ? 0 : 1)
      || (b.lead_confidence ?? b.buyer_intent_score) - (a.lead_confidence ?? a.buyer_intent_score))
    .slice(0, 200)
  const counts = {
    confirmed: comments.filter((c) => leadOf(c) === 'confirmed_rx300_buyer').length,
    potential: comments.filter((c) => leadOf(c) === 'potential_rx300_fit').length,
  }

  // Private bucket → short-lived signed URLs (10 min), only for what this view renders
  const sign = async (path: string | null | undefined) => {
    if (!path) return undefined
    const { data } = await supabaseAdmin.storage.from('listing-evidence').createSignedUrl(path, 600)
    return data?.signedUrl
  }
  const shownPosts = view === 'leads'
    ? (Array.from(new Set(leads.map((c) => c.post_id))).map((id) => postById.get(id)).filter(Boolean) as Post[])
    : view === 'posts' ? posts.slice(0, 60) : []
  const shownIds = new Set(shownPosts.map((p) => p.id))
  const shownComments = view === 'leads' ? leads : view === 'posts' ? comments.filter((c) => shownIds.has(c.post_id)) : []
  const [pShots, cShots] = await Promise.all([
    Promise.all(shownPosts.filter((p) => p.screenshot_path).map(async (p) => [p.id, await sign(p.screenshot_path)] as const)),
    Promise.all(shownComments.filter((c) => c.screenshot_path).map(async (c) => [c.id, await sign(c.screenshot_path)] as const)),
  ])
  const postShots = new Map<string, string | undefined>(pShots)
  const commentShots = new Map<string, string | undefined>(cShots)
  const bizShots = new Map<string, string | undefined>(await Promise.all(shownComments
    .filter((c) => c.account_type === 'business' && c.business_page_screenshot)
    .map(async (c) => [c.id, await sign(c.business_page_screenshot)] as const)))

  const href = (next: Record<string, string>) => {
    const p = new URLSearchParams({ view, ...(platform && { platform }), ...(lead !== 'confirmed_rx300_buyer' && { lead }), ...(q && { q }), ...next })
    for (const [k, v] of Array.from(p.entries())) if (!v) p.delete(k)
    return `/admin/social?${p.toString()}`
  }
  const Thread = ({ list, parent, depth }: { list: Comment[]; parent: string | null; depth: number }) => (
    <div className="space-y-3">
      {list.filter((c) => c.parent_comment_id === parent).map((c) => (
        <div key={c.id} className="space-y-3">
          <CommentCard c={c} shot={commentShots.get(c.id)} bizShot={bizShots.get(c.id)} depth={depth} />
          <Thread list={list} parent={c.id} depth={depth + 1} />
        </div>
      ))}
    </div>
  )

  return (
    <div className="min-h-screen">
      <div className="bg-surface border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-12 pb-8">
          <p className="inline-flex items-center gap-2 text-sm font-medium text-muted mb-3"><span className="w-1.5 h-1.5 rounded-full bg-brand" />Private · {user.email}</p>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink">Lexus RX300 buyers</h1>
          <p className="mt-3 text-muted max-w-3xl">
            Public posts and comments from every platform, typed as RX300 buyers, potential fits, sellers or irrelevant.
            Commenters are pseudonymous keys; screenshots hide names. Businesses are listed apart from buyer leads.
          </p>

          <section className="mt-8" aria-label="Platforms">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
              {ADAPTERS.map((a) => {
                const s = status.get(a.id)
                const st = s ? STATE[s.state] ?? STATE.error : null
                const active = platform === a.platform
                return (
                  <Link key={a.id} href={href({ platform: active ? '' : a.platform })} title={s?.detail ?? undefined}
                    className={clsx('rounded-2xl border p-3 transition-colors min-w-0', active ? 'border-ink bg-paper' : 'border-line bg-surface hover:border-ink')}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-ink truncate">{a.label}</span>
                      <span className="text-[10px] text-subtle">T{a.tier}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {st ? <Chip className={st.cls}>{st.text}</Chip> : <Chip className="bg-paper text-subtle"><CircleDot className="w-3 h-3" /> off</Chip>}
                      <span className="text-xs text-muted tnum">{postsPerPlatform[a.platform] ?? 0} posts</span>
                    </div>
                    {s && (
                      <p className="mt-1.5 text-[11px] text-subtle leading-snug">
                        {s.circuit_open_until && new Date(s.circuit_open_until) > new Date() ? <>paused until {fmt(s.circuit_open_until)}</>
                          : <><Clock className="inline w-3 h-3 -mt-0.5" /> next {fmt(s.next_run_at)}</>}
                        {s.consecutive_failures > 0 && <> · {s.consecutive_failures} fail</>}
                        {s.last_success_at && <><br />ok {fmt(s.last_success_at)}</>}
                      </p>
                    )}
                  </Link>
                )
              })}
            </div>
          </section>

          <nav className="mt-6 flex flex-wrap gap-2" aria-label="Views">
            {([['leads', 'Leads'], ['posts', 'Posts & threads'], ['organizations', `Businesses ${orgs.length}`], ['skipped', `Skipped ${skips.length}`]] as const).map(([id, label]) => (
              <Link key={id} href={href({ view: id })} className={clsx('px-4 py-2.5 rounded-full text-sm font-medium border transition-colors',
                view === id ? 'bg-ink text-white border-ink' : 'bg-surface text-ink border-line hover:border-ink')}>{label}</Link>
            ))}
          </nav>

          {view === 'leads' && (
            <form className="mt-4 flex flex-wrap items-center gap-2" action="/admin/social">
              <input type="hidden" name="view" value="leads" />
              {platform && <input type="hidden" name="platform" value={platform} />}
              <label className="relative flex-1 min-w-[220px] max-w-md">
                <span className="sr-only">Search comment text</span>
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                <input name="q" defaultValue={q} placeholder="Search comment text (Khmer or English)" className="w-full rounded-full border border-line bg-surface pl-11 pr-4 py-2.5 text-sm focus:outline-none focus:border-brand" />
              </label>
              <select name="lead" defaultValue={lead} className="rounded-full border border-line bg-surface px-4 py-2.5 text-sm">
                <option value="confirmed_rx300_buyer">Confirmed RX300 buyers</option>
                <option value="buyers">RX300 buyers + potential fits</option>
                <option value="potential_rx300_fit">Potential RX300 fits</option>
                <option value="seller_or_dealer">Sellers / dealers</option>
                <option value="all">Everything</option>
              </select>
              <button className="px-5 py-2.5 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors">Apply</button>
            </form>
          )}

          <dl className="mt-6 grid grid-cols-2 md:grid-cols-5 gap-3">
            {[['Posts', posts.length], ['Comments stored', comments.length], ['RX300 buyers', counts.confirmed], ['Potential fits', counts.potential], ['Businesses', orgs.length]].map(([l, v]) => (
              <div key={l as string} className="rounded-2xl bg-paper border border-line p-4"><dt className="text-sm text-muted">{l}</dt><dd className="text-2xl font-semibold text-ink tnum mt-1">{v as number}</dd></div>
            ))}
          </dl>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {tablesMissing && <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">The social tables aren&apos;t created yet — apply <code>supabase/migrations/20261001_public_social_generalized.sql</code>.</p>}
        {!tablesMissing && leadsMissing && <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">Lead types, businesses and platform status need <code>supabase/migrations/20261002_multi_platform_discovery.sql</code>. Until then buyers are shown by intent score only.</p>}

        {view === 'leads' && (
          <>
            {leads.map((c) => {
              const p = postById.get(c.post_id)
              const parent = c.parent_comment_id ? commentById.get(c.parent_comment_id) : undefined
              return (
                <article key={c.id} className="rounded-3xl border border-line bg-paper/60 p-3 md:p-4 space-y-3">
                  {p && <PostPreview p={p} shot={postShots.get(p.id)} />}
                  {parent && (
                    <div className="ml-4 md:ml-6 rounded-2xl border border-line bg-surface p-3 text-sm">
                      <span className="text-xs text-muted">Replying to {parent.commenter_key ? `#${parent.commenter_key.slice(0, 8)}` : 'a comment'}:</span>
                      <p className="mt-1 text-ink whitespace-pre-wrap line-clamp-3">{parent.comment_text}</p>
                    </div>
                  )}
                  <CommentCard c={c} shot={commentShots.get(c.id)} bizShot={bizShots.get(c.id)} depth={parent ? 1 : 0} />
                  <p className="text-xs text-muted pl-2">
                    {c.comment_url_available ? <Ext href={c.source_comment_url} label="Open comment" /> : <>Comment on <Ext href={p?.canonical_post_url} label="this post" /></>} · captured {fmt(c.captured_at)}
                  </p>
                </article>
              )
            })}
            {!tablesMissing && leads.length === 0 && <p className="text-muted">No leads{platform ? ` on ${PLATFORM_LABEL[platform]}` : ''} yet.</p>}
          </>
        )}

        {view === 'posts' && shownPosts.map((p) => {
          const mine = comments.filter((c) => c.post_id === p.id)
          return (
            <article key={p.id} className="rounded-3xl bg-surface border border-line overflow-hidden">
              <div className="p-6 border-b border-line">
                <PostPreview p={p} shot={postShots.get(p.id)} />
                <dl className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Field label="Found by search">“{p.search_query}” <Ext href={p.search_url} label="results" /></Field>
                  <Field label="Visibility"><CheckCircle2 className="inline w-3 h-3 text-emerald-600" /> {p.visibility_evidence}</Field>
                  <Field label="Comments">{p.completeness_status === 'complete' ? 'all collected' : <><AlertTriangle className="inline w-3 h-3 text-amber-600" /> {p.completeness_status}</>} · {p.comments_collected_count} / {p.replies_collected_count} replies{p.rejected_comment_count ? ` · ${p.rejected_comment_count} not stored` : ''}</Field>
                  <Field label="Engagement (shown)">{Object.entries(p.engagement).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'}</Field>
                  <Field label="Captured">{fmt(p.captured_at)}</Field>
                  <Field label="Adapter" mono>{p.source_adapter ?? p.adapter_version}</Field>
                </dl>
              </div>
              <div className="p-6 bg-paper/60">{mine.length ? <Thread list={mine} parent={null} depth={0} /> : <p className="text-sm text-muted">No stored comments.</p>}</div>
            </article>
          )
        })}
        {view === 'posts' && !tablesMissing && shownPosts.length === 0 && <p className="text-muted">No posts yet.</p>}

        {view === 'organizations' && (
          <div className="rounded-3xl bg-surface border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted border-b border-line"><tr>{['Business', 'Platform', 'Kind', 'Why organizational', 'Last seen'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {orgs.filter((o) => !platform || o.platform === platform).map((o) => (
                  <tr key={o.id}>
                    <td className="px-4 py-3"><Building2 className="inline w-4 h-4 text-muted mr-1" />{o.url ? <Ext href={o.url} label={o.name} /> : o.name}</td>
                    <td className="px-4 py-3">{PLATFORM_LABEL[o.platform] ?? o.platform}</td>
                    <td className="px-4 py-3">{o.kind}</td>
                    <td className="px-4 py-3 text-muted">{o.evidence}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{fmt(o.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {orgs.length === 0 && <p className="px-4 py-3 text-sm text-muted">No businesses recorded yet.</p>}
          </div>
        )}

        {view === 'skipped' && (
          <div className="rounded-3xl bg-surface border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted border-b border-line"><tr>{['When', 'Platform', 'Post', 'Search', 'Reason'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {skips.map((s) => (
                  <tr key={s.id}>
                    <td className="px-4 py-3 whitespace-nowrap">{fmt(s.observed_at)}</td>
                    <td className="px-4 py-3">{PLATFORM_LABEL[s.platform] ?? s.platform}</td>
                    <td className="px-4 py-3"><Ext href={s.canonical_post_url} /></td>
                    <td className="px-4 py-3">{s.search_query}</td>
                    <td className="px-4 py-3 font-mono text-xs">{s.skip_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
