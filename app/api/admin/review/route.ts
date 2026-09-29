import { NextResponse, type NextRequest } from 'next/server'
import { getServerUser, isAdmin } from '@/lib/auth-server'
import { supabaseAdmin } from '@/lib/supabase-server'

// Human decisions on listing-intelligence candidates. Mirrors intelligence/fbm_intel/state.py:
//   approve: ranked | manual_review → approved
//   reject:  manual_review → rejected,  ranked → not_selected
const TRANSITIONS: Record<'approve' | 'reject', Record<string, string>> = {
  approve: { ranked: 'approved', manual_review: 'approved' },
  reject: { manual_review: 'rejected', ranked: 'not_selected' },
}

export async function POST(request: NextRequest) {
  const user = await getServerUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  if (!isAdmin(user)) return NextResponse.json({ error: 'Admins only' }, { status: 403 })

  const body = await request.json().catch(() => null)
  const listingId = typeof body?.listingId === 'string' ? body.listingId : ''
  const decision = body?.decision === 'approve' || body?.decision === 'reject' ? body.decision : null
  const notes = typeof body?.notes === 'string' ? body.notes.slice(0, 1000) : null
  if (!/^[0-9a-f-]{36}$/.test(listingId) || !decision) {
    return NextResponse.json({ error: 'listingId and decision (approve|reject) are required' }, { status: 400 })
  }

  const { data: listing } = await supabaseAdmin.from('listings').select('id, lifecycle_status').eq('id', listingId).single()
  if (!listing) return NextResponse.json({ error: 'Listing not found' }, { status: 404 })
  const next = TRANSITIONS[decision as 'approve' | 'reject'][listing.lifecycle_status]
  if (!next) {
    return NextResponse.json({ error: `Cannot ${decision} a listing in state "${listing.lifecycle_status}"` }, { status: 409 })
  }

  // Optimistic lock on the current state so two reviewers can't both win
  const { data: updated } = await supabaseAdmin
    .from('listings')
    .update({ lifecycle_status: next, status_reason: `reviewer_${decision}`, updated_at: new Date().toISOString() })
    .eq('id', listingId)
    .eq('lifecycle_status', listing.lifecycle_status)
    .select('id')
  if (!updated?.length) return NextResponse.json({ error: 'Listing changed, reload and try again' }, { status: 409 })

  await supabaseAdmin.from('pipeline_events').insert({
    entity_type: 'listing', entity_id: listingId, previous_state: listing.lifecycle_status, next_state: next,
    actor: `reviewer:${user.id}`, reason: notes ?? `reviewer_${decision}`,
  })
  await supabaseAdmin
    .from('review_tasks')
    .update({
      status: 'resolved', reviewer_decision: decision, reviewer_notes: notes, assigned_reviewer: user.id,
      resolved_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    })
    .eq('listing_id', listingId)
    .in('status', ['open', 'in_progress'])

  return NextResponse.json({ ok: true, state: next })
}
