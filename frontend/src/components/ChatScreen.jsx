/**
 * ChatScreen.jsx
 * --------------
 * Two-panel chat interface.
 *
 * Left panel  — conversation thread with Buddy (message bubbles + input)
 * Right panel — AgentBrainPanel (live reasoning sidebar)
 *
 * On mount, if `initiated` is false, calls /initiate so Buddy speaks first.
 * `initiated` is lifted to App.jsx to prevent duplicate initiate calls across
 * tab navigation or after simulate-next-day pre-loads a message.
 *
 * Enter (without Shift) submits the message. Shift+Enter adds a newline.
 */

import { useState, useEffect, useRef } from 'react'
import AgentBrainPanel from './AgentBrainPanel'

const API = 'http://localhost:8000'

export default function ChatScreen({ messages, setMessages, reasoning, setReasoning, initiated, setInitiated }) {
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef             = useRef(null)

  // Initiate agent on first load if no message has been pre-loaded
  useEffect(() => {
    if (!initiated) {
      initiate()
      setInitiated(true)
    }
  }, [])

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function initiate() {
    setLoading(true)
    try {
      const res  = await fetch(`${API}/initiate`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ user_id: 1, task_id: 1 }),
      })
      const data = await res.json()
      setMessages([{ role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
    } catch {
      setMessages([{ role: 'assistant', content: 'Could not reach the backend. Is it running?' }])
    } finally {
      setLoading(false)
    }
  }

  async function send() {
    const text = input.trim()
    if (!text || loading) return

    const next = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setInput('')
    setLoading(true)

    try {
      const res  = await fetch(`${API}/chat`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ user_id: 1, task_id: 1, message: text }),
      })
      const data = await res.json()
      setMessages([...next, { role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
    } catch {
      setMessages([...next, { role: 'assistant', content: 'Something went wrong.' }])
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div style={{
      display: 'flex',
      gap: 16,
      alignItems: 'flex-start',
      height: 'calc(100vh - 120px)',
    }}>

      {/* Left: conversation thread */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--white)',
        borderRadius: 16,
        boxShadow: 'var(--card-shadow)',
        overflow: 'hidden',
        height: '100%',
      }}>

        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--rose-soft)',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text-muted)',
          letterSpacing: 1,
          textTransform: 'uppercase',
        }}>
          Conversation
        </div>

        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '20px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}>
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} content={m.content} />
          ))}
          {loading && <Bubble role="assistant" content="thinking..." muted />}
          <div ref={bottomRef} />
        </div>

        <div style={{
          padding: '16px 20px',
          borderTop: '1px solid var(--rose-soft)',
          display: 'flex',
          gap: 10,
          alignItems: 'flex-end',
        }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Reply to your companion…"
            rows={2}
            style={{
              flex: 1,
              resize: 'none',
              border: '1.5px solid var(--lavender)',
              borderRadius: 12,
              padding: '10px 14px',
              fontSize: 14,
              fontFamily: 'var(--font-body)',
              color: 'var(--text-main)',
              background: 'var(--lavender)',
              outline: 'none',
              lineHeight: 1.5,
              transition: 'border-color 0.15s',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent-pink)'}
            onBlur={e  => e.target.style.borderColor = 'var(--lavender)'}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            style={{
              padding: '10px 20px',
              borderRadius: 12,
              background: loading || !input.trim() ? 'var(--rose-soft)' : 'var(--accent-pink)',
              color: loading || !input.trim() ? 'var(--text-muted)' : 'var(--white)',
              fontSize: 14,
              fontWeight: 600,
              transition: 'all 0.15s',
              height: 44,
            }}
          >
            Send
          </button>
        </div>
      </div>

      {/* Right: Agent Brain reasoning sidebar */}
      <AgentBrainPanel reasoning={reasoning} />
    </div>
  )
}

/**
 * Bubble
 * Chat message bubble. Agent messages align left, user messages align right.
 * `muted` renders the "thinking..." placeholder in italic.
 */
function Bubble({ role, content, muted }) {
  const isAgent = role === 'assistant'
  return (
    <div style={{ display: 'flex', justifyContent: isAgent ? 'flex-start' : 'flex-end' }}>
      <div style={{
        maxWidth: '80%',
        padding: '12px 16px',
        borderRadius: isAgent ? '4px 16px 16px 16px' : '16px 4px 16px 16px',
        background: isAgent ? 'var(--rose-soft)' : 'var(--blue-mist)',
        fontSize: 14,
        lineHeight: 1.6,
        color: muted ? 'var(--text-muted)' : 'var(--text-main)',
        fontStyle: muted ? 'italic' : 'normal',
        borderLeft: isAgent ? '3px solid var(--accent-pink)' : 'none',
        borderRight: !isAgent ? '3px solid #7AACE4' : 'none',
      }}>
        {content}
      </div>
    </div>
  )
}
