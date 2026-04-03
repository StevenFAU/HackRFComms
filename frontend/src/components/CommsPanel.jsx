import { useEffect, useRef, useState } from 'react'
import StatusIndicator from './StatusIndicator'
import { useWebSocket } from '../hooks/useWebSocket'

// Inline serial display stubs (backend holds the real values)
const CONFIG_TX = '625863dc...'
const CONFIG_RX = '15b062dc...'

const WS_URL = `ws://${window.location.host}/ws/comms`

function formatTimestamp(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

function MessageBubble({ entry }) {
  const isSent = entry.direction === 'sent'
  return (
    <div className={`flex flex-col ${isSent ? 'items-end' : 'items-start'} mb-2`}>
      <div
        className={`max-w-[75%] px-3 py-2 rounded-lg text-xs font-mono whitespace-pre-wrap break-words ${
          isSent
            ? 'bg-[#00d2ff]/15 border border-[#00d2ff]/40 text-[#00d2ff]'
            : 'bg-green-900/30 border border-green-500/40 text-green-300'
        }`}
      >
        {entry.text}
      </div>
      <span className="text-gray-600 text-xs font-mono mt-0.5 px-1">
        {isSent ? 'sent' : 'rcvd'} · {formatTimestamp(entry.timestamp)}
        {entry.error && (
          <span className="text-red-400 ml-2">· {entry.error}</span>
        )}
      </span>
    </div>
  )
}

export default function CommsPanel() {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [log, setLog] = useState([])
  const [listening, setListening] = useState(false)
  const logEndRef = useRef(null)

  const { messages: wsMessages, connected: wsConnected, connect, disconnect } = useWebSocket(WS_URL)

  // Append incoming WebSocket messages to the log
  const prevWsLengthRef = useRef(0)
  useEffect(() => {
    if (wsMessages.length > prevWsLengthRef.current) {
      const newMsgs = wsMessages.slice(prevWsLengthRef.current)
      prevWsLengthRef.current = wsMessages.length
      const entries = newMsgs.map((m) => ({
        id: m.id,
        direction: 'received',
        text: m.data || '(empty)',
        timestamp: m.timestamp,
        error: m.error,
      }))
      setLog((prev) => [...prev.slice(-(100 - entries.length)), ...entries])
    }
  }, [wsMessages])

  // Auto-scroll log to bottom on new messages
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log])

  function toggleListen() {
    if (listening) {
      disconnect()
      setListening(false)
    } else {
      connect()
      setListening(true)
    }
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    const timestamp = new Date().toISOString()
    try {
      const res = await fetch('/api/comms/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      const data = await res.json()
      setLog((prev) => [
        ...prev.slice(-99),
        {
          id: Date.now(),
          direction: 'sent',
          text,
          timestamp,
          error: data.success === false ? data.message : undefined,
        },
      ])
      if (data.success) setInput('')
    } catch (err) {
      setLog((prev) => [
        ...prev.slice(-99),
        {
          id: Date.now(),
          direction: 'sent',
          text,
          timestamp,
          error: 'Network error',
        },
      ])
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold font-mono text-gray-200">OOK Comms</h2>
        <div className="flex items-center gap-4">
          <StatusIndicator
            connected={wsConnected}
            label={wsConnected ? 'Listening' : listening ? 'Reconnecting...' : 'Not listening'}
          />
          <button
            onClick={toggleListen}
            className={`px-3 py-1.5 text-xs font-mono rounded border transition-colors ${
              listening
                ? 'border-red-500/60 text-red-400 hover:bg-red-900/20'
                : 'border-[#00d2ff]/50 text-[#00d2ff] hover:bg-[#00d2ff]/10'
            }`}
          >
            {listening ? 'Stop Listening' : 'Start Listening'}
          </button>
        </div>
      </div>

      {/* Message log */}
      <div
        className="flex-1 rounded-lg p-4 overflow-y-auto font-mono text-sm min-h-[320px] max-h-[480px] border border-white/10"
        style={{ backgroundColor: '#16213e' }}
      >
        {log.length === 0 ? (
          <p className="text-gray-600 text-xs font-mono text-center mt-8">
            No messages yet. Send a message or start listening.
          </p>
        ) : (
          log.map((entry) => <MessageBubble key={entry.id} entry={entry} />)
        )}
        <div ref={logEndRef} />
      </div>

      {/* Send input */}
      <div
        className="rounded-lg p-4 border border-white/10"
        style={{ backgroundColor: '#16213e' }}
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            className="flex-1 bg-[#0f3460] border border-white/10 rounded px-3 py-2 text-sm font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#00d2ff]/50 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="px-4 py-2 text-sm font-mono rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed border-[#00d2ff]/50 text-[#00d2ff] hover:bg-[#00d2ff]/10 disabled:hover:bg-transparent"
          >
            {sending ? 'Sending...' : 'Send'}
          </button>
        </div>
        <p className="text-xs font-mono text-gray-600 mt-2">
          Press Enter to send · 915 MHz OOK · TX: {CONFIG_TX} · RX: {CONFIG_RX}
        </p>
      </div>
    </div>
  )
}

