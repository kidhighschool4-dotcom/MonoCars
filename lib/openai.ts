import OpenAI from 'openai'
import { NextResponse } from 'next/server'

// Created on first use rather than at import time, so the app still builds
// and deploys when OPENAI_API_KEY isn't set yet.
let client: OpenAI | null = null

export function getOpenAI(): OpenAI {
  return (client ??= new OpenAI({ apiKey: process.env.OPENAI_API_KEY }))
}

/** Returns a 503 response when the AI features aren't configured, otherwise null. */
export function openAINotConfigured() {
  if (process.env.OPENAI_API_KEY) return null
  return NextResponse.json({ error: 'AI features are not configured yet.' }, { status: 503 })
}
