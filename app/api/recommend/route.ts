import { NextResponse, type NextRequest } from 'next/server'
import OpenAI from 'openai'
import { getOpenAI, openAINotConfigured } from '@/lib/openai'
import { getCars, getCarsByIds } from '@/lib/db'
import { supabaseAdmin } from '@/lib/supabase-server'
import type { Car } from '@/types'


// ─── Types ──────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface SearchPreferences {
  budget_min?: number
  budget_max?: number
  car_types?: string[]
  fuel_types?: string[]
  min_seats?: number
  locations?: string[]
  use_case?: string
  description?: string
}

// ─── System prompt ──────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are an expert car advisor for FBM — Cambodia's premier car marketplace.
Your job: ask the user 4–5 focused questions to understand exactly what car they need, then find their best matches.

Be conversational, friendly, and knowledgeable about the Cambodia car market.
Keep responses concise (2–3 sentences max per message).

Ask about (one topic at a time):
1. Budget range in USD
2. Primary use (daily city commute, family trips, off-road/province, business, cargo)
3. Preferred body type (SUV, Sedan, Pickup, etc.) — or let them skip
4. Fuel preference (Gasoline, Diesel, Hybrid, Electric)
5. Number of seats needed

Once you have enough information (at minimum: budget and use case), call the search_cars function.
Do NOT ask more than 5 questions. Make assumptions if needed.

Cambodia market context:
- Most popular: Toyota (Land Cruiser, Fortuner, Hilux, Camry), Honda (CR-V, Accord), Lexus
- Diesel great for province travel; Hybrid best for city fuel savings
- Budget under $20k: used pickups and older sedans
- $20k–$40k: mid-range SUVs (Tucson, Sportage, CX-5, Fortuner)
- $40k–$80k: premium (BMW, Mercedes, Lexus RX)
- $80k+: flagship (Land Cruiser 300, BMW X5)`

// ─── Tool definition ─────────────────────────────────────────────────────────

const SEARCH_TOOL: OpenAI.Chat.Completions.ChatCompletionTool = {
  type: 'function',
  function: {
    name: 'search_cars',
    description: 'Search the FBM database for cars matching user preferences. Call this once you have enough information.',
    parameters: {
      type: 'object',
      properties: {
        budget_min: {
          type: 'number',
          description: 'Minimum budget in USD',
        },
        budget_max: {
          type: 'number',
          description: 'Maximum budget in USD',
        },
        car_types: {
          type: 'array',
          items: { type: 'string' },
          description: 'Preferred car types: SUV, Sedan, Pickup, Hatchback, Van, Coupe, Crossover',
        },
        fuel_types: {
          type: 'array',
          items: { type: 'string' },
          description: 'Fuel types: Gasoline, Diesel, Hybrid, Plug-in Hybrid, Electric',
        },
        min_seats: {
          type: 'number',
          description: 'Minimum number of seats required',
        },
        use_case: {
          type: 'string',
          description: 'Primary use case description',
        },
        description: {
          type: 'string',
          description: 'Natural language description of ideal car for vector similarity search',
        },
      },
      required: ['budget_max', 'description'],
    },
  },
}

// ─── Car search logic ────────────────────────────────────────────────────────

async function searchCars(prefs: SearchPreferences): Promise<Car[]> {
  // Step 1: SQL filters — hard constraints
  const candidates = await getCars({
    priceMin: prefs.budget_min,
    priceMax: prefs.budget_max,
    seats:    prefs.min_seats,
    limit:    50,
  })

  // Filter by type/fuel if specified
  let filtered = candidates
  if (prefs.car_types?.length) {
    const types = prefs.car_types.map((t) => t.toLowerCase())
    filtered = filtered.filter((c) => types.includes(c.type.toLowerCase()))
  }
  if (prefs.fuel_types?.length) {
    const fuels = prefs.fuel_types.map((f) => f.toLowerCase())
    filtered = filtered.filter((c) => fuels.includes((c.fuel ?? '').toLowerCase()))
  }

  // If no results from strict filter, fall back to all SQL results
  const pool = filtered.length >= 3 ? filtered : candidates

  // Step 2: Vector similarity — rank by semantic match
  if (prefs.description && pool.length > 0) {
    try {
      const embeddingResponse = await getOpenAI().embeddings.create({
        model: 'text-embedding-3-small',
        input: prefs.description,
        dimensions: 1536,
      })
      const queryEmbedding = embeddingResponse.data[0].embedding

      const poolIds = pool.map((c) => c.id)

      const { data: matches } = await supabaseAdmin.rpc('match_cars', {
        query_embedding: queryEmbedding,
        match_threshold: 0.1,
        match_count: 5,
        filter_car_ids: poolIds,
      })

      if (matches?.length) {
        const rankedIds = (matches as { car_id: string; similarity: number }[])
          .sort((a, b) => b.similarity - a.similarity)
          .map((m) => m.car_id)

        const ranked = await getCarsByIds(rankedIds)
        if (ranked.length) return ranked
      }
    } catch (err) {
      console.error('[recommend] Vector search failed, using SQL results:', err)
    }
  }

  // Fallback: return top 5 from SQL pool sorted by price label
  const labelOrder = { 'Good Deal': 0, 'Fair': 1, 'Overpriced': 2 }
  return pool
    .sort((a, b) => (labelOrder[a.priceLabel] ?? 1) - (labelOrder[b.priceLabel] ?? 1))
    .slice(0, 5)
}

// ─── Stream helpers ──────────────────────────────────────────────────────────

function encode(obj: object): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(obj)}\n\n`)
}

// ─── Route handler ───────────────────────────────────────────────────────────

export async function POST(request: NextRequest) {
  const notConfigured = openAINotConfigured()
  if (notConfigured) return notConfigured

  const { messages }: { messages: ChatMessage[] } = await request.json()

  const stream = new ReadableStream({
    async start(controller) {
      try {
        const response = await getOpenAI().chat.completions.create({
          model: 'gpt-4o-mini',
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            ...messages,
          ],
          tools: [SEARCH_TOOL],
          tool_choice: 'auto',
          stream: true,
          temperature: 0.7,
          max_tokens: 500,
        })

        let fullText = ''
        let toolCallId = ''
        let toolName = ''
        let toolArgsRaw = ''

        for await (const chunk of response) {
          const delta = chunk.choices[0]?.delta

          // Text chunk
          if (delta?.content) {
            fullText += delta.content
            controller.enqueue(encode({ type: 'text', content: delta.content }))
          }

          // Tool call accumulation
          if (delta?.tool_calls?.[0]) {
            const tc = delta.tool_calls[0]
            if (tc.id)              toolCallId  = tc.id
            if (tc.function?.name)  toolName    = tc.function.name
            if (tc.function?.arguments) toolArgsRaw += tc.function.arguments
          }

          // Finish
          if (chunk.choices[0]?.finish_reason === 'tool_calls' && toolName === 'search_cars') {
            controller.enqueue(encode({ type: 'searching' }))

            const prefs: SearchPreferences = JSON.parse(toolArgsRaw)
            const cars = await searchCars(prefs)

            // Ask GPT to write the recommendation summary
            const summaryResp = await getOpenAI().chat.completions.create({
              model: 'gpt-4o-mini',
              messages: [
                { role: 'system', content: SYSTEM_PROMPT },
                ...messages,
                {
                  role: 'assistant',
                  content: null,
                  tool_calls: [{ id: toolCallId, type: 'function', function: { name: 'search_cars', arguments: toolArgsRaw } }],
                },
                {
                  role: 'tool',
                  tool_call_id: toolCallId,
                  content: JSON.stringify(
                    cars.slice(0, 5).map((c) => ({
                      id: c.id,
                      title: `${c.year} ${c.make} ${c.model}`,
                      price: c.price,
                      priceLabel: c.priceLabel,
                      type: c.type,
                      fuel: c.fuel,
                      mileage: c.mileage,
                      location: c.location,
                      seats: c.seats,
                    }))
                  ),
                },
              ],
              stream: true,
              temperature: 0.6,
              max_tokens: 400,
            })

            for await (const sumChunk of summaryResp) {
              const text = sumChunk.choices[0]?.delta?.content
              if (text) {
                controller.enqueue(encode({ type: 'text', content: text }))
              }
            }

            controller.enqueue(encode({ type: 'cars', cars }))
          }
        }

        controller.enqueue(encode({ type: 'done' }))
        controller.close()
      } catch (err) {
        console.error('[recommend] Error:', err)
        controller.enqueue(encode({ type: 'error', message: 'Something went wrong. Please try again.' }))
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  })
}
