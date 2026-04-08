import { NextResponse, type NextRequest } from 'next/server'
import OpenAI from 'openai'
import { getCars, buildCarEmbeddingContent } from '@/lib/db'
import { supabaseAdmin } from '@/lib/supabase-server'

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })

// POST /api/embed — generate and store embeddings for all cars
// Protect with a secret header in production
export async function POST(request: NextRequest) {
  const secret = request.headers.get('x-embed-secret')
  if (secret !== process.env.EMBED_SECRET && process.env.NODE_ENV === 'production') {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const cars = await getCars({ limit: 200 })
  if (!cars.length) {
    return NextResponse.json({ error: 'No cars found' }, { status: 404 })
  }

  const results: { id: string; status: string }[] = []

  for (const car of cars) {
    try {
      const content = buildCarEmbeddingContent(car as Parameters<typeof buildCarEmbeddingContent>[0])

      const embeddingResponse = await openai.embeddings.create({
        model: 'text-embedding-3-small',
        input: content,
        dimensions: 1536,
      })

      const embedding = embeddingResponse.data[0].embedding

      const { error } = await supabaseAdmin
        .from('car_embeddings')
        .upsert({ car_id: car.id, embedding, content }, { onConflict: 'car_id' })

      if (error) throw error
      results.push({ id: car.id, status: 'ok' })
    } catch (err) {
      console.error(`[embed] Failed for car ${car.id}:`, err)
      results.push({ id: car.id, status: 'error' })
    }
  }

  const ok = results.filter((r) => r.status === 'ok').length
  return NextResponse.json({ embedded: ok, total: cars.length, results })
}
