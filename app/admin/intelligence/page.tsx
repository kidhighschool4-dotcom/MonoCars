import Link from 'next/link'
import { redirect } from 'next/navigation'
import { ExternalLink, ShieldAlert } from 'lucide-react'
import clsx from 'clsx'
import { getServerUser, isAdmin } from '@/lib/auth-server'
import { supabaseAdmin } from '@/lib/supabase-server'
import PageHeader from '@/components/ui/PageHeader'
import ReviewActions from '@/components/admin/ReviewActions'

export const dynamic = 'force-dynamic'

interface ListingRow {
  id: string
  title_raw: string | null
  price_text_raw: string | null
  location_normalized: string | null
  source_url: string
  source_platform: string
  lifecycle_status: string
}
interface MemberRow {
  listing_id: string
  rank_position: number
  composite_score: number
  qualified: boolean
  selected: boolean
  reason_codes: string[]
  component_scores: Record<string, unknown>
  listings: ListingRow
}
interface EvalRow {
  listing_id: string
  decision: string
  model_decision: string
  fit_score_percent: number
  evidence_quality_percent: number
  apparent_risk_level: number
  short_reason: string
  risk_flags: string[]
  missing_information: string[]
  model: string
  created_at: string
}

const decisionTone: Record<string, string> = {
  good: 'bg-emerald-50 text-emerald-700',
  review: 'bg-sky-50 text-sky-700',
  reject: 'bg-rose-50 text-rose-700',
  insufficient_evidence: 'bg-amber-50 text-amber-800',
}

function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={clsx('inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full', className)}>{children}</span>
}

export default async function IntelligencePage() {
  const user = await getServerUser()
  if (!user) redirect('/auth?next=/admin/intelligence')
  if (!isAdmin(user)) {
    return (
      <div className="max-w-md mx-auto px-4 py-24 text-center">
        <ShieldAlert className="w-10 h-10 text-muted mx-auto" />
        <h1 className="mt-4 text-2xl font-semibold text-ink">Admins only</h1>
        <p className="text-muted mt-2">Listing intelligence is an internal review tool.</p>
      </div>
    )
  }

  const [{ data: runs }, { data: crawls }, { data: openTasks }, { data: stateRows }] = await Promise.all([
    supabaseAdmin.from('ranking_runs').select('*').order('created_at', { ascending: false }).limit(1),
    supabaseAdmin.from('crawl_runs').select('*').order('planned_at', { ascending: false }).limit(5),
    supabaseAdmin.from('review_tasks').select('id, reason, priority, listing_id, created_at, listings(title_raw, lifecycle_status)')
      .eq('status', 'open').order('priority', { ascending: false }).limit(50),
    supabaseAdmin.from('listings').select('lifecycle_status'),
  ])
  const run = runs?.[0]
  const counts: Record<string, number> = {}
  for (const r of stateRows ?? []) counts[r.lifecycle_status] = (counts[r.lifecycle_status] ?? 0) + 1

  let members: MemberRow[] = []
  const evals = new Map<string, EvalRow>()
  const shots = new Map<string, string>()
  const photos = new Map<string, string>()
  const buyerComments = new Map<string, string[]>()
  if (run) {
    const { data } = await supabaseAdmin
      .from('ranking_members')
      .select('listing_id, rank_position, composite_score, qualified, selected, reason_codes, component_scores, listings(id, title_raw, price_text_raw, location_normalized, source_url, source_platform, lifecycle_status)')
      .eq('ranking_run_id', run.id)
      .order('rank_position')
    members = (data ?? []) as unknown as MemberRow[]
    const ids = members.map((m) => m.listing_id)
    if (ids.length) {
      const [{ data: ev }, { data: assets }] = await Promise.all([
        supabaseAdmin.from('vision_evaluations').select('listing_id, decision, model_decision, fit_score_percent, evidence_quality_percent, apparent_risk_level, short_reason, risk_flags, missing_information, model, created_at')
          .in('listing_id', ids).order('created_at', { ascending: false }),
        supabaseAdmin.from('listing_assets').select('listing_id, storage_path, captured_at, asset_kind').in('listing_id', ids).order('captured_at', { ascending: false }),
      ])
      const { data: comments } = await supabaseAdmin.from('listing_comments').select('listing_id, text_redacted').in('listing_id', ids)
      for (const c of comments ?? []) buyerComments.set(c.listing_id, [...(buyerComments.get(c.listing_id) ?? []), c.text_redacted])
      for (const e of (ev ?? []) as EvalRow[]) if (!evals.has(e.listing_id)) evals.set(e.listing_id, e)
      const latest = new Map<string, string>()
      const latestPhoto = new Map<string, string>()
      for (const a of assets ?? []) {
        const target = a.asset_kind === 'primary_image' ? latestPhoto : latest
        if (!target.has(a.listing_id)) target.set(a.listing_id, a.storage_path)
      }
      // Private bucket → short-lived signed URLs only (§9.5)
      const sign = async (entries: Map<string, string>, into: Map<string, string>) =>
        Promise.all([...entries].map(async ([id, path]) => {
          const { data: signed } = await supabaseAdmin.storage.from('listing-evidence').createSignedUrl(path, 600)
          if (signed?.signedUrl) into.set(id, signed.signedUrl)
        }))
      await Promise.all([sign(latest, shots), sign(latestPhoto, photos)])
    }
  }

  const statusText: Record<string, string> = {
    recommended: 'Recommended — awaiting your approval',
    manual_review: 'Top pick needs a human look (tie or near the threshold)',
    no_qualifying_candidate: 'No listing is good enough — nothing selected',
    empty: 'No candidates yet',
  }

  return (
    <div className="min-h-screen">
      <PageHeader eyebrow="Internal" title="Listing intelligence"
        description="Discovered public listings, AI screenshot checks, deterministic scores and the current recommendation. Every recommendation needs a human decision." />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
        {/* Pipeline summary */}
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            ['Captured', Object.values(counts).reduce((a, b) => a + b, 0)],
            ['Ranked', counts.ranked ?? 0],
            ['Manual review', counts.manual_review ?? 0],
            ['Rejected', (counts.rejected ?? 0) + (counts.prefilter_rejected ?? 0) + (counts.vision_rejected ?? 0)],
            ['Open tasks', openTasks?.length ?? 0],
          ].map(([label, value]) => (
            <div key={label as string} className="rounded-2xl bg-surface border border-line p-4">
              <p className="text-sm text-muted">{label}</p>
              <p className="text-2xl font-semibold text-ink tnum mt-1">{value as number}</p>
            </div>
          ))}
        </section>

        {/* Latest ranking */}
        <section className="rounded-3xl bg-surface border border-line overflow-hidden">
          <div className="p-6 border-b border-line flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold text-ink">Latest ranking</h2>
              <p className="text-sm text-muted mt-1">
                {run ? `${statusText[run.status] ?? run.status} · policy ${run.policy_version} · minimum ${run.minimum_acceptable_score}` : 'Run `fbm-intel run` to create one.'}
              </p>
            </div>
            {run && <p className="text-xs text-subtle tnum">{new Date(run.created_at).toLocaleString('en-GB')}</p>}
          </div>
          {members.length === 0 ? (
            <p className="p-6 text-muted">No candidates.</p>
          ) : (
            <ul className="divide-y divide-line">
              {members.map((m) => {
                const e = evals.get(m.listing_id)
                const l = m.listings
                return (
                  <li key={m.listing_id} className={clsx('p-5 grid grid-cols-1 md:grid-cols-[160px_1fr_auto] gap-5', m.selected && 'bg-brand-soft/60')}>
                    <div className="space-y-2">
                    <div className="aspect-[4/3] rounded-xl overflow-hidden bg-paper border border-line">
                      {shots.get(m.listing_id) ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={shots.get(m.listing_id)} alt="Captured listing evidence" className="w-full h-full object-cover object-top" />
                      ) : <div className="w-full h-full flex items-center justify-center text-xs text-muted">No screenshot</div>}
                    </div>
                    {photos.get(m.listing_id) && (
                      <a href={photos.get(m.listing_id)} target="_blank" rel="noopener noreferrer" className="block aspect-[4/3] rounded-xl overflow-hidden border border-line" title="Captured main photo">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={photos.get(m.listing_id)} alt="Captured main photo" className="w-full h-full object-cover" />
                      </a>
                    )}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-muted tnum">#{m.rank_position}</span>
                        {m.selected && <Chip className="bg-brand text-white">Selected</Chip>}
                        {e && <Chip className={decisionTone[e.decision]}>{e.decision.replaceAll('_', ' ')}</Chip>}
                        <Chip className={m.qualified ? 'bg-emerald-50 text-emerald-700' : 'bg-paper text-muted'}>
                          {m.qualified ? 'qualified' : 'not qualified'}
                        </Chip>
                      </div>
                      <p className="mt-2 font-semibold text-ink truncate">{l?.title_raw ?? 'Untitled listing'}</p>
                      <p className="text-sm text-muted">{[l?.price_text_raw, l?.location_normalized, l?.source_platform].filter(Boolean).join(' · ')}</p>
                      {e && <p className="mt-2 text-sm text-ink/80">{e.short_reason}</p>}
                      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted tnum">
                        <span>Composite <b className="text-ink">{Number(m.composite_score).toFixed(1)}</b></span>
                        {e && <span>Fit {e.fit_score_percent}%</span>}
                        {e && <span>Evidence {e.evidence_quality_percent}%</span>}
                        {e && <span>Risk {e.apparent_risk_level}/5</span>}
                        {e && <span>Model {e.model}</span>}
                      </div>
                      {(m.reason_codes?.length > 0 || (e?.risk_flags?.length ?? 0) > 0) && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {m.reason_codes.map((c) => <Chip key={c} className="bg-paper text-muted font-medium">{c}</Chip>)}
                          {e?.risk_flags?.map((f) => <Chip key={f} className="bg-amber-50 text-amber-800 font-medium">{f}</Chip>)}
                        </div>
                      )}
                      {(buyerComments.get(m.listing_id)?.length ?? 0) > 0 && (
                        <div className="mt-3 rounded-xl bg-emerald-50/60 border border-emerald-100 p-3">
                          <p className="text-xs font-semibold text-emerald-800">
                            {buyerComments.get(m.listing_id)!.length} buyer-interest comment{buyerComments.get(m.listing_id)!.length > 1 ? 's' : ''} (names and contacts removed)
                          </p>
                          <ul className="mt-1 space-y-0.5">
                            {buyerComments.get(m.listing_id)!.slice(0, 5).map((t) => <li key={t} className="text-xs text-ink/80">“{t}”</li>)}
                          </ul>
                        </div>
                      )}
                      {l?.source_url && (
                        <Link href={l.source_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-brand hover:underline">
                          Source <ExternalLink className="w-3 h-3" />
                        </Link>
                      )}
                    </div>
                    <div className="md:text-right">
                      <ReviewActions listingId={m.listing_id} state={l?.lifecycle_status ?? ''} />
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* Open review tasks */}
        <section className="rounded-3xl bg-surface border border-line p-6">
          <h2 className="text-xl font-semibold text-ink mb-4">Open review tasks</h2>
          {!openTasks?.length ? <p className="text-muted">Nothing waiting.</p> : (
            <ul className="divide-y divide-line">
              {openTasks.map((t) => {
                const l = t.listings as unknown as { title_raw: string | null; lifecycle_status: string } | null
                return (
                  <li key={t.id} className="py-3 flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-medium text-ink truncate">{l?.title_raw ?? t.listing_id}</p>
                      <p className="text-xs text-muted">{t.reason} · priority {t.priority}</p>
                    </div>
                    {t.listing_id && <ReviewActions listingId={t.listing_id} state={l?.lifecycle_status ?? ''} />}
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* Crawl runs */}
        <section className="rounded-3xl bg-surface border border-line p-6 overflow-x-auto">
          <h2 className="text-xl font-semibold text-ink mb-4">Recent crawl runs</h2>
          <table className="w-full text-sm tnum">
            <thead className="text-left text-muted">
              <tr>{['Started', 'Status', 'Queries', 'Found', 'Captured', 'Duplicates', 'Prefiltered', 'Blocks', 'Errors'].map((h) => <th key={h} className="py-2 pr-4 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(crawls ?? []).map((c) => (
                <tr key={c.id}>
                  <td className="py-2 pr-4">{new Date(c.planned_at).toLocaleString('en-GB')}</td>
                  <td className="py-2 pr-4">{c.status}</td>
                  <td className="py-2 pr-4">{c.queries_attempted}</td>
                  <td className="py-2 pr-4">{c.listings_found}</td>
                  <td className="py-2 pr-4">{c.listings_captured}</td>
                  <td className="py-2 pr-4">{c.duplicates}</td>
                  <td className="py-2 pr-4">{c.prefilter_rejected}</td>
                  <td className="py-2 pr-4">{c.blocks}</td>
                  <td className="py-2 pr-4">{c.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  )
}
