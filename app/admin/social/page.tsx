import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'
import { ExternalLink, CornerDownRight, Star, Search, Eye, Building2 } from 'lucide-react'
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

const ago = (d: string | null | undefined) => {
  if (!d) return '—'
  const m = Math.round((Date.now() - new Date(d).getTime()) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 36) return `${h} h ago`
  return `${Math.round(h / 24)} days ago`
}

function LeadTile({ c, p, parent, postShot, commentShot, bizShot }: {
  c: Comment; p?: Post; parent?: Comment; postShot?: string; commentShot?: string; bizShot?: string
}) {
  const lt = leadOf(c)
  const commentLink = c.comment_url_available ? c.source_comment_url : null
  return (
    <article className="group flex flex-col rounded-2xl border border-line bg-surface overflow-hidden hover:border-ink/30 transition-colors">
      <a href={postShot ?? p?.canonical_post_url ?? '#'} target="_blank" rel="noopener noreferrer"
        className="relative block aspect-[16/10] bg-paper overflow-hidden border-b border-line">
        {postShot ? (
          // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL from a private bucket
          <img src={postShot} alt="Post (names hidden)" className="w-full h-full object-cover object-top" />
        ) : (
          <div className="absolute inset-0 p-5 flex flex-col">
            <p className="text-[15px] leading-snug text-ink line-clamp-6 whitespace-pre-wrap">
              {[p?.post_title, p?.post_text].filter(Boolean).join('\n') || 'No post text'}
            </p>
            <span className="mt-auto text-[11px] text-subtle">No screenshot for this post</span>
          </div>
        )}
        <span className="absolute left-3 top-3 rounded-md bg-white/95 px-2 py-0.5 text-[11px] font-semibold text-ink shadow-sm">
          {PLATFORM_LABEL[c.platform] ?? c.platform}
        </span>
      </a>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-center gap-2 text-xs">
          <span className={clsx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-semibold', LEAD[lt].cls)}>{LEAD[lt].text}</span>
          {c.lead_use_case && <span className="text-muted">{c.lead_use_case === 'taxi' ? 'taxi use' : 'family car'}</span>}
          <span className="ml-auto text-subtle tnum">{c.displayed_timestamp ?? ago(c.captured_at)}</span>
        </div>

        {parent && <p className="text-xs text-muted line-clamp-2 border-l-2 border-line pl-2">↳ reply to “{parent.comment_text}”</p>}

        <p className="text-[17px] leading-snug font-medium text-ink whitespace-pre-wrap break-words">“{c.comment_text}”</p>

        {commentShot && (
          <a href={commentShot} target="_blank" rel="noopener noreferrer" className="block rounded-lg border border-line bg-paper overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={commentShot} alt="Comment in context (name hidden)" className="w-full max-h-36 object-contain object-left-top" />
          </a>
        )}

        {p && postShot && (p.post_title || p.post_text) && (
          <p className="text-xs text-muted line-clamp-2">{p.post_title ?? p.post_text}</p>
        )}

        <div className="mt-auto flex items-center gap-2 pt-1">
          {commentLink ? (
            <a href={commentLink} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg bg-ink px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand transition-colors">
              Open comment <ExternalLink className="w-3 h-3" />
            </a>
          ) : null}
          {p && (
            <a href={p.canonical_post_url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:border-ink transition-colors">
              Open post <ExternalLink className="w-3 h-3" />
            </a>
          )}
          <span className="ml-auto"><AccountChip c={c} bizShot={bizShot} /></span>
        </div>
      </div>
    </article>
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

  const active = ADAPTERS.filter((a) => (postsPerPlatform[a.platform] ?? 0) > 0 || ['ok', 'budget_exhausted', 'challenged', 'rate_limited'].includes(status.get(a.id)?.state ?? ''))
  const inactive = ADAPTERS.filter((a) => !active.includes(a))
  const buyerPosts = new Set(comments.filter((c) => leadOf(c) === 'confirmed_rx300_buyer').map((c) => c.post_id)).size
  const lastRun = Array.from(status.values()).map((s) => s.last_success_at).filter(Boolean).sort().pop() ?? null
  const NEEDS: Record<string, string> = { login_required: 'needs your login', misconfigured: 'needs an API key / setup' }

  return (
    <div className="min-h-screen bg-paper/50">
      <header className="bg-surface border-b border-line">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted">Private · {user.email}</p>
              <h1 className="mt-1 text-3xl md:text-4xl font-semibold tracking-tight text-ink">Lexus RX300 buyers</h1>
              <p className="mt-1.5 text-sm text-muted max-w-xl">People asking to buy an RX300 in public comments on sale posts. Names are never stored; open the comment to see it on the platform.</p>
            </div>
            <dl className="flex items-stretch divide-x divide-line rounded-xl border border-line bg-surface">
              <div className="px-5 py-3">
                <dt className="text-[11px] uppercase tracking-wider text-muted">RX300 buyers</dt>
                <dd className="text-3xl font-semibold tnum text-ink leading-tight">{counts.confirmed}</dd>
              </div>
              <div className="px-5 py-3">
                <dt className="text-[11px] uppercase tracking-wider text-muted">On sale posts</dt>
                <dd className="text-3xl font-semibold tnum text-ink leading-tight">{buyerPosts}</dd>
              </div>
              <div className="px-5 py-3 hidden sm:block">
                <dt className="text-[11px] uppercase tracking-wider text-muted">Last run</dt>
                <dd className="text-sm font-medium text-ink mt-2">{ago(lastRun)}</dd>
              </div>
            </dl>
          </div>

          {/* Sources: only what is actually collecting, the rest folded away */}
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted mr-1">Sources</span>
            <Link href={href({ platform: '' })}
              className={clsx('rounded-lg border px-3 py-1.5 text-sm transition-colors', !platform ? 'border-ink bg-ink text-white' : 'border-line bg-surface text-ink hover:border-ink')}>
              All
            </Link>
            {active.map((a) => {
              const st = status.get(a.id)
              const dot = !st ? 'bg-subtle' : st.state === 'ok' || st.state === 'budget_exhausted' ? 'bg-emerald-500' : st.state === 'challenged' ? 'bg-rose-500' : 'bg-amber-500'
              const on = platform === a.platform
              return (
                <Link key={a.id} href={href({ platform: on ? '' : a.platform })} title={st?.detail ?? undefined}
                  className={clsx('inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors',
                    on ? 'border-ink bg-ink text-white' : 'border-line bg-surface text-ink hover:border-ink')}>
                  <span className={clsx('w-1.5 h-1.5 rounded-full', dot)} />
                  {a.label}
                  <span className={clsx('tnum text-xs', on ? 'text-white/70' : 'text-muted')}>{postsPerPlatform[a.platform] ?? 0}</span>
                </Link>
              )
            })}
            {inactive.length > 0 && (
              <details className="relative">
                <summary className="list-none cursor-pointer select-none rounded-lg border border-dashed border-line px-3 py-1.5 text-sm text-muted hover:text-ink">
                  +{inactive.length} not set up
                </summary>
                <div className="absolute z-30 mt-2 w-[340px] rounded-xl border border-line bg-surface p-2 shadow-[0_18px_50px_-12px_rgba(0,0,0,0.25)]">
                  {inactive.map((a) => {
                    const st = status.get(a.id)
                    return (
                      <div key={a.id} className="flex items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-sm hover:bg-paper">
                        <span className="text-ink">{a.label}</span>
                        <span className="text-xs text-muted text-right">{st ? (NEEDS[st.state] ?? STATE[st.state]?.text ?? st.state) : 'off'}</span>
                      </div>
                    )
                  })}
                </div>
              </details>
            )}
          </div>
        </div>
      </header>

      {/* Sticky toolbar */}
      <div className="sticky top-16 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex flex-wrap items-center gap-2">
          <nav className="flex rounded-lg bg-paper p-0.5" aria-label="Views">
            {([['leads', 'Leads'], ['posts', 'Posts'], ['organizations', `Businesses ${orgs.length}`], ['skipped', `Skipped ${skips.length}`]] as const).map(([id, label]) => (
              <Link key={id} href={href({ view: id })}
                className={clsx('rounded-md px-3 py-1.5 text-sm font-medium transition-colors', view === id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink')}>
                {label}
              </Link>
            ))}
          </nav>
          {view === 'leads' && (
            <form className="flex flex-1 flex-wrap items-center justify-end gap-2" action="/admin/social">
              <input type="hidden" name="view" value="leads" />
              {platform && <input type="hidden" name="platform" value={platform} />}
              <label className="relative flex-1 min-w-[180px] max-w-xs">
                <span className="sr-only">Search comment text</span>
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                <input name="q" defaultValue={q} placeholder="Search comments…"
                  className="w-full rounded-lg border border-line bg-surface py-1.5 pl-9 pr-3 text-sm focus:outline-none focus:border-brand" />
              </label>
              <select name="lead" defaultValue={lead} className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm">
                <option value="confirmed_rx300_buyer">RX300 buyers</option>
                <option value="buyers">+ potential fits</option>
                <option value="seller_or_dealer">Sellers / dealers</option>
                <option value="all">Everything</option>
              </select>
              <button className="rounded-lg bg-ink px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-brand transition-colors">Apply</button>
            </form>
          )}
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {tablesMissing && <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">The social tables aren&apos;t created yet — apply <code>supabase/migrations/20261001_public_social_generalized.sql</code>.</p>}
        {!tablesMissing && leadsMissing && <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">Lead types need <code>supabase/migrations/20261002_multi_platform_discovery.sql</code>.</p>}

        {view === 'leads' && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {leads.map((c) => (
                <LeadTile key={c.id} c={c} p={postById.get(c.post_id)}
                  parent={c.parent_comment_id ? commentById.get(c.parent_comment_id) : undefined}
                  postShot={postShots.get(c.post_id)} commentShot={commentShots.get(c.id)} bizShot={bizShots.get(c.id)} />
              ))}
            </div>
            {!tablesMissing && leads.length === 0 && (
              <div className="rounded-2xl border border-dashed border-line bg-surface p-10 text-center">
                <p className="text-ink font-medium">No RX300 buyers{platform ? ` on ${PLATFORM_LABEL[platform]}` : ''} yet</p>
                <p className="mt-1 text-sm text-muted">New buyers appear here as the worker finds them.</p>
              </div>
            )}
          </>
        )}

        {view === 'posts' && shownPosts.map((p) => {
          const mine = comments.filter((c) => c.post_id === p.id)
          return (
            <article key={p.id} className="rounded-2xl bg-surface border border-line overflow-hidden">
              <div className="grid md:grid-cols-[320px_minmax(0,1fr)]">
                <div className="bg-paper border-b md:border-b-0 md:border-r border-line">
                  {postShots.get(p.id)
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <a href={postShots.get(p.id)} target="_blank" rel="noopener noreferrer"><img src={postShots.get(p.id)} alt="Post (names hidden)" className="w-full h-full max-h-[420px] object-cover object-top" /></a>
                    : <p className="p-5 text-sm text-muted">No screenshot</p>}
                </div>
                <div className="p-5 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span className="rounded-md bg-paper px-2 py-0.5 font-semibold text-ink">{PLATFORM_LABEL[p.platform] ?? p.platform}</span>
                    {p.lead_type && <span className={clsx('rounded-md px-2 py-0.5 font-semibold', LEAD[p.lead_type].cls)}>{LEAD[p.lead_type].text}</span>}
                    <span>“{p.search_query}”</span>
                    <span className="ml-auto">{p.published_text_displayed ?? fmt(p.published_at_observed ?? p.captured_at)}</span>
                  </div>
                  {(p.post_title || p.document_title) && <p className="mt-3 font-semibold text-ink">{p.post_title ?? p.document_title}</p>}
                  <p className="mt-2 text-sm text-ink whitespace-pre-wrap line-clamp-6">{p.post_text ?? '(no text)'}</p>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
                    <span>{p.comments_collected_count} comments · {p.replies_collected_count} replies{p.rejected_comment_count ? ` · ${p.rejected_comment_count} not stored` : ''}</span>
                    <span>{p.completeness_status === 'complete' ? 'all comments read' : p.completeness_status.replaceAll('_', ' ')}</span>
                    <Ext href={p.canonical_post_url} label="Open post" />
                  </div>
                  <div className="mt-4 space-y-3">{mine.length ? <Thread list={mine} parent={null} depth={0} /> : <p className="text-sm text-muted">No stored comments.</p>}</div>
                </div>
              </div>
            </article>
          )
        })}
        {view === 'posts' && !tablesMissing && shownPosts.length === 0 && <p className="text-muted">No posts yet.</p>}

        {view === 'organizations' && (
          <div className="rounded-2xl bg-surface border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-muted border-b border-line">
                <tr>{['Business', 'Platform', 'Category', 'Location', 'Contact', 'Last seen'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {orgs.filter((o) => !platform || o.platform === platform).map((o) => (
                  <tr key={o.id}>
                    <td className="px-4 py-3"><Building2 className="inline w-4 h-4 text-muted mr-1.5" />{o.url ? <Ext href={o.url} label={o.name} /> : o.name}</td>
                    <td className="px-4 py-3">{PLATFORM_LABEL[o.platform] ?? o.platform}</td>
                    <td className="px-4 py-3 text-muted">{(o as Org & { category?: string }).category ?? o.kind}</td>
                    <td className="px-4 py-3 text-muted">{(o as Org & { sales_location?: string }).sales_location ?? '—'}</td>
                    <td className="px-4 py-3 text-muted">{Object.values((o as Org & { contact_channels?: Record<string, string[]> }).contact_channels ?? {}).flat().slice(0, 2).join(', ') || '—'}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted">{ago(o.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {orgs.length === 0 && <p className="px-4 py-6 text-sm text-muted">No businesses recorded yet.</p>}
          </div>
        )}

        {view === 'skipped' && (
          <div className="rounded-2xl bg-surface border border-line overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-muted border-b border-line"><tr>{['When', 'Platform', 'Post', 'Search', 'Why skipped'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {skips.map((s) => (
                  <tr key={s.id}>
                    <td className="px-4 py-3 whitespace-nowrap text-muted">{ago(s.observed_at)}</td>
                    <td className="px-4 py-3">{PLATFORM_LABEL[s.platform] ?? s.platform}</td>
                    <td className="px-4 py-3"><Ext href={s.canonical_post_url} label="Open" /></td>
                    <td className="px-4 py-3">{s.search_query}</td>
                    <td className="px-4 py-3 text-muted">{s.skip_reason.replaceAll('_', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  )
}
