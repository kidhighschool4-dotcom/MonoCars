'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Send, Mic, Paperclip, FileText, Download, X } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'

interface Message {
  id: string
  sender_id: string
  message_type: 'text' | 'voice' | 'file'
  content: string | null
  file_url: string | null
  file_name: string | null
  file_size: number | null
  duration_secs: number | null
  is_read: boolean
  created_at: string
  profiles?: { full_name: string | null }
}

interface CarRef {
  id: string
  title: string
  price_usd: number
  car_images?: { url: string; is_primary: boolean }[]
}

interface ConvMeta {
  id: string
  buyer_id: string
  seller_id: string
  car_id: string
  cars: CarRef
  buyer: { id: string; full_name: string | null }
  seller: { id: string; full_name: string | null }
}

function formatDuration(secs: number) {
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const { user, loading } = useAuth()
  const router = useRouter()

  const [conv, setConv] = useState<ConvMeta | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [fetching, setFetching] = useState(true)
  const [uploading, setUploading] = useState(false)

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)

  const bottomRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchMessages = useCallback(async () => {
    const res = await fetch(`/api/conversations/${id}/messages`)
    if (!res.ok) return
    const { messages: msgs } = await res.json()
    setMessages(msgs ?? [])
  }, [id])

  useEffect(() => {
    if (!loading && !user) { router.replace('/auth?next=/messages'); return }
    if (!user) return

    fetch('/api/conversations')
      .then((r) => r.json())
      .then(({ conversations }) => {
        const found = conversations?.find((c: ConvMeta) => c.id === id)
        setConv(found ?? null)
      })

    fetchMessages().finally(() => setFetching(false))

    pollRef.current = setInterval(fetchMessages, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [user, loading, id, router, fetchMessages])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Clean up timer and recorder on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop()
      }
    }
  }, [])

  async function uploadAndSend(
    file: File | Blob,
    fileName: string,
    type: 'voice' | 'file',
    durationSecs?: number
  ) {
    setUploading(true)
    try {
      // 1. Get signed upload URL
      const urlRes = await fetch('/api/upload-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversationId: id, fileName }),
      })
      const { signedUrl, fileUrl } = await urlRes.json()

      // 2. Upload to storage
      await fetch(signedUrl, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file instanceof File ? file.type : 'audio/webm' },
      })

      // 3. Send message
      const res = await fetch(`/api/conversations/${id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_type: type,
          file_url: fileUrl,
          file_name: fileName,
          file_size: file.size,
          duration_secs: durationSecs,
        }),
      })
      if (res.ok) {
        const { message } = await res.json()
        setMessages((prev) => [...prev, message])
      }
    } finally {
      setUploading(false)
    }
  }

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || sending) return
    setSending(true)
    const content = input.trim()
    setInput('')
    try {
      const res = await fetch(`/api/conversations/${id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_type: 'text', content }),
      })
      if (res.ok) {
        const { message } = await res.json()
        setMessages((prev) => [...prev, message])
      }
    } finally {
      setSending(false)
    }
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const duration = recordingSeconds
        setRecordingSeconds(0)
        await uploadAndSend(blob, `voice-${Date.now()}.webm`, 'voice', duration)
      }

      recorder.start()
      setIsRecording(true)
      setRecordingSeconds(0)
      timerRef.current = setInterval(() => {
        setRecordingSeconds((s) => s + 1)
      }, 1000)
    } catch {
      alert('Microphone access is required to record voice messages.')
    }
  }

  const stopRecording = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    setIsRecording(false)
  }

  const cancelRecording = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.ondataavailable = null
      recorderRef.current.onstop = null
      recorderRef.current.stop()
    }
    setIsRecording(false)
    setRecordingSeconds(0)
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    // Reset input so same file can be re-selected
    e.target.value = ''
    await uploadAndSend(file, file.name, 'file')
  }

  if (loading || fetching) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const carImage = conv?.cars?.car_images?.find((i) => i.is_primary)?.url ?? conv?.cars?.car_images?.[0]?.url
  const otherPerson = user?.id === conv?.buyer_id ? conv?.seller : conv?.buyer

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      {/* Header */}
      <div className="bg-ink px-4 py-4 flex items-center gap-3 sticky top-0 z-10">
        <Link href="/messages" className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold text-sm truncate">{otherPerson?.full_name ?? 'Seller'}</p>
          <p className="text-gray-400 text-xs truncate">{conv?.cars?.title ?? 'Car Listing'}</p>
        </div>
        {conv?.cars?.id && (
          <Link href={`/cars/${conv.cars.id}`} className="text-xs text-brand hover:underline flex-shrink-0">
            View Car
          </Link>
        )}
      </div>

      {/* Car reference card */}
      {conv?.cars && (
        <div className="bg-white border-b border-line px-4 py-3">
          <div className="max-w-2xl mx-auto flex items-center gap-3">
            {carImage ? (
              <img src={carImage} alt={conv.cars.title} className="w-14 h-14 rounded-xl object-cover flex-shrink-0" />
            ) : (
              <div className="w-14 h-14 rounded-xl bg-gray-100 flex-shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-0.5">Enquiring about</p>
              <p className="text-sm font-bold text-ink truncate">{conv.cars.title}</p>
              <p className="text-sm font-semibold tracking-tight text-brand">${conv.cars.price_usd?.toLocaleString()}</p>
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-2xl mx-auto space-y-3">
          {messages.length === 0 && (
            <p className="text-center text-sm text-gray-400 py-8">
              No messages yet. Say hello!
            </p>
          )}
          {messages.map((msg) => {
            const isMe = msg.sender_id === user?.id
            const bubbleBase = `max-w-[75%] rounded-2xl px-4 py-2.5 ${
              isMe
                ? 'bg-brand text-white rounded-br-sm'
                : 'bg-white border border-line text-ink rounded-bl-sm shadow-sm'
            }`
            const timeText = new Date(msg.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
            const timeClass = `text-[10px] mt-1 ${isMe ? 'text-ink/60' : 'text-gray-400'}`

            return (
              <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                {msg.message_type === 'text' && (
                  <div className={bubbleBase}>
                    <p className="text-sm leading-relaxed">{msg.content}</p>
                    <p className={timeClass}>
                      {timeText}{isMe && msg.is_read ? ' · Read' : ''}
                    </p>
                  </div>
                )}

                {msg.message_type === 'voice' && (
                  <div className={bubbleBase}>
                    <div className="flex items-center gap-2">
                      <Mic className="w-4 h-4 flex-shrink-0 opacity-70" />
                      <audio
                        controls
                        src={msg.file_url ?? undefined}
                        className="h-8 max-w-[180px]"
                        style={{ colorScheme: isMe ? 'dark' : 'light' }}
                      />
                      {msg.duration_secs != null && (
                        <span className="text-xs opacity-70 flex-shrink-0">{formatDuration(msg.duration_secs)}</span>
                      )}
                    </div>
                    <p className={timeClass}>
                      {timeText}{isMe && msg.is_read ? ' · Read' : ''}
                    </p>
                  </div>
                )}

                {msg.message_type === 'file' && (
                  <div className={bubbleBase}>
                    <a
                      href={msg.file_url ?? undefined}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 group"
                    >
                      <FileText className="w-8 h-8 flex-shrink-0 opacity-70" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate max-w-[160px]">
                          {msg.file_name ?? 'File'}
                        </p>
                        {msg.file_size != null && (
                          <p className="text-xs opacity-60">{formatFileSize(msg.file_size)}</p>
                        )}
                      </div>
                      <Download className="w-4 h-4 flex-shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
                    </a>
                    <p className={timeClass}>
                      {timeText}{isMe && msg.is_read ? ' · Read' : ''}
                    </p>
                  </div>
                )}
              </div>
            )
          })}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="bg-white border-t border-line px-4 py-3 sticky bottom-0">
        <div className="max-w-2xl mx-auto">

          {/* Recording indicator */}
          {isRecording && (
            <div className="flex items-center gap-3 mb-2 px-1">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
              <span className="text-sm text-red-500 font-medium flex-1">
                Recording — {formatDuration(recordingSeconds)}
              </span>
              <button
                type="button"
                onClick={cancelRecording}
                className="text-gray-400 hover:text-muted transition-colors"
                aria-label="Cancel recording"
              >
                <X className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={stopRecording}
                className="px-3 py-1 rounded-lg bg-red-500 text-white text-xs font-semibold hover:bg-red-600 transition-colors"
              >
                Send
              </button>
            </div>
          )}

          {/* Uploading indicator */}
          {uploading && (
            <div className="flex items-center gap-2 mb-2 px-1">
              <div className="w-4 h-4 border-2 border-brand border-t-transparent rounded-full animate-spin flex-shrink-0" />
              <span className="text-sm text-muted">Uploading…</span>
            </div>
          )}

          {/* Main input row */}
          {!isRecording && (
            <form onSubmit={handleSend} className="flex items-center gap-2">
              {/* File attachment button */}
              <button
                type="button"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
                className="w-10 h-10 rounded-xl border border-line flex items-center justify-center text-gray-400 hover:text-brand hover:border-brand transition-colors flex-shrink-0 disabled:opacity-40"
                aria-label="Attach file"
              >
                <Paperclip className="w-4 h-4" />
              </button>

              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type a message…"
                className="flex-1 px-4 py-2.5 rounded-xl border border-line text-ink text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand placeholder:text-gray-400"
              />

              {/* Mic or Send button depending on input content */}
              {input.trim() ? (
                <button
                  type="submit"
                  disabled={sending || uploading}
                  className="w-10 h-10 rounded-xl bg-brand flex items-center justify-center disabled:opacity-40 hover:bg-brand-strong transition-colors flex-shrink-0"
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4 text-ink" />
                </button>
              ) : (
                <button
                  type="button"
                  disabled={uploading}
                  onClick={startRecording}
                  className="w-10 h-10 rounded-xl border border-line flex items-center justify-center text-gray-400 hover:text-brand hover:border-brand transition-colors flex-shrink-0 disabled:opacity-40"
                  aria-label="Record voice message"
                >
                  <Mic className="w-4 h-4" />
                </button>
              )}
            </form>
          )}

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept="image/*,audio/*,application/pdf,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={handleFileSelect}
          />
        </div>
      </div>
    </div>
  )
}
