import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'
import { ExternalLink, CornerDownRight, Star, AlertTriangle, CheckCircle2, Search, Eye } from 'lucide-react'
import clsx from 'clsx'
import { canViewFacebookData, getServerUser } from '@/lib/auth-server'
import { supabaseAdmin } from '@/lib/supabase-server'

export const dynamic = 'force-dynamic'
export const metadata = { title: 'Social data | FBM', robots: { index: false, follow: false } }

const PLATFORMS = [
  { id: 'facebook', label: 'Facebook' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'reddit', label: 'Reddit' },
] as const
type Platform = (typeof PLATFORMS)[number]['id']

interface Post {
  id: string; platform: string; source_content_type: string; source_post_id: string | null; source_post_url: string
  canonical_post_url: string; document_title: string | null; post_title: string | null; post_text: string | null
  hashtags: string[]; subreddit: string | null; published_text_displayed: string | null; published_at_observed: string | null
  engagement: Record<string, string>; visibility_evidence: string; search_query: string; search_url: string | null
  captured_at: string; adapter_version: string; completeness_status: string; comments_collected_count: number
  replies_collected_count: number; comment_expansion_rounds: number; rejected_comment_count: number
  rejection_reasons: Record<string, number>; screenshot_path: string | null; expires_at: string
}
interface Comment {
  id: string; post_id: string; parent_comment_id: string | null; comment_type: 'comment' | 'reply'
  source_comment_url: string | null; comment_url_available: boolean; comment_fingerprint: string
  commenter_key: string | null; commenter_key_scope: string; comment_text: string; comment_text_normalized: string | null
  displayed_timestamp: string | null; captured_at: string; buyer_intent_score: number; buyer_intent_label: string
  intent_type: string | null; detected_language: string | null; matched_phrases: string[]; negative_signals: string[]
  spam_score: number; intent_reason: string | null; needs_human_review: boolean; scorer_version: string | null
  screenshot_path: string | null
}

const LABEL: Record<string, { text: string; cls: string }> = {
  strong_buyer_intent: { text: 'Strong buyer', cls: 'bg-emerald-600 text-white' },
  possible_buyer_intent: { text: 'Possible buyer', cls: 'bg-amber-100 text-amber-900' },
  not_buyer_intent: { text: 'Not buyer', cls: 'bg-paper text-subtle' },
}
const fmt = (d: string | null) => (d ? new Date(d).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '—')

function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full', className)}>{children}</span>
}
function Ext({ href, label }: { href: string | null; label?: string }) {
  if (!href) return <span className="text-subtle">—</span>
  return <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-brand hover:underline break-all">{label ?? href} <ExternalLink className="w-3 h-3 flex-shrink-0" /></a>
}
function Field({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return <div className="min-w-0"><dt className="text-[11px] uppercase tracking-wide text-subtle">{label}</dt><dd className={clsx('text-sm text-ink break-all', mono && 'font-mono text-xs')}>{children}</dd></div>
}

function CommentCard({ c, shot, depth }: { c: Comment; shot?: string; depth: number }) {
  const l = LABEL[c.buyer_intent_label] ?? LABEL.not_buyer_intent
  return (
    <div className={clsx('rounded-2xl border p-4', c.buyer_intent_label === 'strong_buyer_intent' ? 'border-emerald-200 bg-emerald-50/50'
      : c.buyer_intent_label === 'possible_buyer_intent' ? 'border-amber-200 bg-amber-50/40' : 'border-line bg-surface', depth > 0 && 'ml-6 md:ml-10')}>
      <div className="flex flex-wrap items-center gap-2">
        {depth > 0 && <CornerDownRight className="w-4 h-4 text-subtle" />}
        <Chip className="bg-paper text-muted">{c.comment_type}</Chip>
        <Chip className={l.cls}>{c.buyer_intent_label !== 'not_buyer_intent' && <Star className="w-3 h-3" />}{l.text} · {c.buyer_intent_score}</Chip>
        {c.intent_type && <Chip className="bg-paper text-ink">{c.intent_type.replaceAll('_', ' ')}</Chip>}
        {c.needs_human_review && <Chip className="bg-amber-50 text-amber-800"><Eye className="w-3 h-3" /> review</Chip>}
        {c.spam_score > 0 && <Chip className="bg-rose-50 text-rose-700">spam {c.spam_score}</Chip>}
        <span className="text-xs text-subtle ml-auto">{c.displayed_timestamp ?? ''} · {c.commenter_key ? `#${c.commenter_key.slice(0, 8)}` : 'comment-only id'}</span>
      </div>
      <p className="mt-3 text-[15px] text-ink whitespace-pre-wrap">{c.comment_text}</p>
      {c.intent_reason && <p className="mt-1 text-xs text-muted">{c.intent_reason}</p>}
      {shot && (
        <a href={shot} target="_blank" rel="noopener noreferrer" className="mt-3 block max-w-md rounded-xl overflow-hidden border border-line">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={shot} alt="Comment evidence (commenter name hidden)" className="w-full" />
        </a>
      )}
      <details className="mt-3">
        <summary className="text-xs text-muted cursor-pointer select-none">All fields</summary>
        <dl className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Comment link">{c.comment_url_available ? <Ext href={c.source_comment_url} /> : 'not provided by the platform'}</Field>
          <Field label="Fingerprint" mono>{c.comment_fingerprint}</Field>
          <Field label="Normalized text" mono>{c.comment_text_normalized ?? '—'}</Field>
          <Field label="Language">{c.detected_language ?? '—'}</Field>
          <Field label="Matched phrases">{c.matched_phrases.length ? c.matched_phrases.map((p) => `“${p}”`).join(', ') : '—'}</Field>
          <Field label="Negative signals">{c.negative_signals.length ? c.negative_signals.join(', ') : '—'}</Field>
          <Field label="Commenter key scope">{c.commenter_key_scope}</Field>
          <Field label="Captured">{fmt(c.captured_at)}</Field>
          <Field label="Scorer" mono>{c.scorer_version ?? '—'}</Field>
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
  const platform = (PLATFORMS.some((p) => p.id === sp.platform) ? sp.platform : 'tiktok') as Platform
  if (platform === 'facebook') redirect('/admin/facebook')
  const minScore = Math.max(0, Math.min(100, Number(sp.min ?? 0) || 0))
  const q = typeof sp.q === 'string' ? sp.q.trim().slice(0, 100).toLowerCase() : ''

  const [{ data: postsData, error }, { data: commentsData }, { data: skipsData }, { data: counts }] = await Promise.all([
    supabaseAdmin.from('public_social_posts').select('*').eq('owner_id', user.id).eq('platform', platform).order('captured_at', { ascending: false }),
    supabaseAdmin.from('public_social_comments').select('*').eq('owner_id', user.id).eq('platform', platform).order('captured_at', { ascending: true }),
    supabaseAdmin.from('public_social_post_skips').select('*').eq('owner_id', user.id).eq('platform', platform).order('observed_at', { ascending: false }).limit(100),
    supabaseAdmin.from('public_social_posts').select('platform').eq('owner_id', user.id),
  ])
  const tablesMissing = !!error && /does not exist|schema cache/i.test(error.message)
  const posts = (postsData ?? []) as Post[]
  const comments = (commentsData ?? []) as Comment[]
  const skips = (skipsData ?? []) as { id: number; canonical_post_url: string | null; search_query: string; skip_reason: string; observed_at: string }[]
  const perPlatform: Record<string, number> = {}
  for (const r of counts ?? []) perPlatform[r.platform] = (perPlatform[r.platform] ?? 0) + 1

  // Private bucket → short-lived signed URLs (10 min)
  const sign = async (path: string | null) => {
    if (!path) return undefined
    const { data } = await supabaseAdmin.storage.from('listing-evidence').createSignedUrl(path, 600)
    return data?.signedUrl
  }
  const postShots = new Map(await Promise.all(posts.map(async (p) => [p.id, await sign(p.screenshot_path)] as const)))
  const commentShots = new Map(await Promise.all(comments.filter((c) => c.screenshot_path).map(async (c) => [c.id, await sign(c.screenshot_path)] as const)))

  const buyers = comments.filter((c) => c.buyer_intent_label !== 'not_buyer_intent')
  const visible = (c: Comment) => c.buyer_intent_score >= minScore && (!q || c.comment_text.toLowerCase().includes(q))

  const Thread = ({ list, parent, depth }: { list: Comment[]; parent: string | null; depth: number }) => (
    <div className="space-y-3">
      {list.filter((c) => c.parent_comment_id === parent).map((c) => (
        <div key={c.id} className="space-y-3">
          {(visible(c) || list.some((r) => r.parent_comment_id === c.id && visible(r))) && <CommentCard c={c} shot={commentShots.get(c.id)} depth={depth} />}
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
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink">Social data</h1>
          <p className="mt-3 text-muted max-w-3xl">Public posts and public comments from each platform, scored for buyer intent. Commenters are pseudonymous keys; screenshots hide names.</p>
          <nav className="mt-8 flex flex-wrap gap-2" aria-label="Platforms">
            {PLATFORMS.map((p) => (
              <Link key={p.id} href={p.id === 'facebook' ? '/admin/facebook' : `/admin/social?platform=${p.id}`}
                className={clsx('px-4 py-2.5 rounded-full text-sm font-medium border transition-colors',
                  platform === p.id ? 'bg-ink text-white border-ink' : 'bg-surface text-ink border-line hover:border-ink')}>
                {p.label} {p.id !== 'facebook' && <span className="tnum opacity-70">{perPlatform[p.id] ?? 0}</span>}
              </Link>
            ))}
          </nav>
          <form className="mt-4 flex flex-wrap items-center gap-2" action="/admin/social">
            <input type="hidden" name="platform" value={platform} />
            <label className="relative flex-1 min-w-[220px] max-w-md">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <input name="q" defaultValue={q} placeholder="Search comment text" className="w-full rounded-full border border-line bg-surface pl-11 pr-4 py-2.5 text-sm focus:outline-none focus:border-brand" />
            </label>
            <select name="min" defaultValue={String(minScore)} className="rounded-full border border-line bg-surface px-4 py-2.5 text-sm">
              <option value="0">All comments</option><option value="40">Possible buyers and up (40+)</option><option value="70">Strong buyers (70+)</option>
            </select>
            <button className="px-5 py-2.5 rounded-full bg-ink text-white text-sm font-semibold hover:bg-brand transition-colors">Apply</button>
          </form>
          <dl className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3">
            {[['Public posts', posts.length], ['Comments + replies', comments.length], ['Buyer comments', buyers.length], ['Skipped', skips.length]].map(([l, v]) => (
              <div key={l as string} className="rounded-2xl bg-paper border border-line p-4"><dt className="text-sm text-muted">{l}</dt><dd className="text-2xl font-semibold text-ink tnum mt-1">{v as number}</dd></div>
            ))}
          </dl>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {tablesMissing && <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-900 text-sm">The multi-platform tables aren&apos;t created yet — apply <code>supabase/migrations/20261001_public_social_generalized.sql</code>.</p>}
        {!tablesMissing && posts.length === 0 && <p className="text-muted">No {platform} data yet.</p>}
        {posts.map((p) => {
          const mine = comments.filter((c) => c.post_id === p.id)
          const shot = postShots.get(p.id)
          return (
            <article key={p.id} className="rounded-3xl bg-surface border border-line overflow-hidden">
              <div className="p-6 border-b border-line grid md:grid-cols-[220px_1fr] gap-6">
                <div className="rounded-2xl overflow-hidden bg-paper border border-line aspect-[3/4]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {shot ? <img src={shot} alt="Post evidence" className="w-full h-full object-cover" /> : <div className="w-full h-full flex items-center justify-center text-xs text-muted">No screenshot</div>}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip className="bg-emerald-50 text-emerald-700"><CheckCircle2 className="w-3 h-3" /> {p.visibility_evidence}</Chip>
                    <Chip className="bg-paper text-muted">{p.source_content_type}</Chip>
                    {p.completeness_status === 'complete' ? <Chip className="bg-paper text-muted">all comments collected</Chip>
                      : <Chip className="bg-amber-50 text-amber-800"><AlertTriangle className="w-3 h-3" /> {p.completeness_status}</Chip>}
                  </div>
                  <p className="mt-3 text-ink whitespace-pre-wrap">{p.post_title ? <b>{p.post_title}<br /></b> : null}{p.post_text ?? '(no caption)'}</p>
                  {p.hashtags.length > 0 && <p className="mt-2 flex flex-wrap gap-1.5">{p.hashtags.map((h) => <Chip key={h} className="bg-brand-soft text-brand">{h}</Chip>)}</p>}
                  <dl className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <Field label="Post link"><Ext href={p.canonical_post_url} /></Field>
                    <Field label="Found by search">“{p.search_query}” <Ext href={p.search_url} label="results page" /></Field>
                    <Field label="Page title">{p.document_title ?? '—'}</Field>
                    <Field label="Published (shown)">{p.published_text_displayed ?? '—'}</Field>
                    <Field label="Engagement (shown)">{Object.entries(p.engagement).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'}</Field>
                    <Field label="Comments / replies">{p.comments_collected_count} / {p.replies_collected_count} · {p.comment_expansion_rounds} rounds{p.rejected_comment_count ? ` · ${p.rejected_comment_count} not stored` : ''}</Field>
                    <Field label="Source id" mono>{p.source_post_id ?? '—'}</Field>
                    <Field label="Captured">{fmt(p.captured_at)}</Field>
                    <Field label="Adapter / expires" mono>{p.adapter_version} · {fmt(p.expires_at)}</Field>
                  </dl>
                </div>
              </div>
              <div className="p-6 bg-paper/60">{mine.length ? <Thread list={mine} parent={null} depth={0} /> : <p className="text-sm text-muted">No stored comments.</p>}</div>
            </article>
          )
        })}
        {skips.length > 0 && (
          <section className="rounded-3xl bg-surface border border-line p-6">
            <h2 className="font-semibold text-ink mb-3">Skipped (not verified public / unavailable)</h2>
            <ul className="space-y-1 text-sm">{skips.map((s) => <li key={s.id}><Ext href={s.canonical_post_url} /> · “{s.search_query}” · <span className="font-mono text-xs">{s.skip_reason}</span></li>)}</ul>
          </section>
        )}
      </div>
    </div>
  )
}
