/**
 * ChatScreen.jsx
 * --------------
 * Two-panel chat interface.
 *
 * V2 changes:
 * - Receives activeTask prop, uses activeTask.id instead of hardcoded task_id: 1
 * - Filters [EmotionPick:] and [System:] messages from visible thread (already existed)
 * - If initiated=true (came from emotion picker hook), skips /initiate entirely
 */

import { useState, useEffect, useRef } from 'react'
import AgentBrainPanel from './AgentBrainPanel'

const API = 'http://localhost:8000'

export default function ChatScreen({
  activeTask,
  messages, setMessages,
  reasoning, setReasoning,
  initiated, setInitiated,
}) {
  const taskId = activeTask?.id

  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef             = useRef(null)
  const initiateCalledRef     = useRef(false)

  useEffect(() => {
    if (!initiated && !initiateCalledRef.current) {
      initiateCalledRef.current = true
      initiate()
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function initiate() {
    setLoading(true)
    try {
      const res  = await fetch(`${API}/initiate`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ user_id: 1, task_id: taskId }),
      })
      const data = await res.json()
      setMessages([{ role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
      setInitiated(true)
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
        body:    JSON.stringify({ user_id: 1, task_id: taskId, message: text }),
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

  const visibleMessages = messages.filter(m => {
    if (m.role !== 'user') return true
    return !m.content.startsWith('[EmotionPick:') && !m.content.startsWith('[System:')
  })

  return (
    <div style={{
      display:    'flex',
      gap:        16,
      alignItems: 'flex-start',
      height:     'calc(100vh - 120px)',
    }}>

      <div style={{
        flex:          1,
        display:       'flex',
        flexDirection: 'column',
        background:    'var(--white)',
        borderRadius:  16,
        boxShadow:     'var(--card-shadow)',
        overflow:      'hidden',
        height:        '100%',
      }}>

        {/* Header — shows task name */}
        <div style={{
          padding:       '16px 24px',
          borderBottom:  '1px solid var(--rose-soft)',
          display:       'flex',
          alignItems:    'center',
          gap:           10,
        }}>
          <div style={{
            fontSize:      13,
            fontWeight:    600,
            color:         'var(--text-muted)',
            letterSpacing: 1,
            textTransform: 'uppercase',
          }}>
            Buddy
          </div>
          {activeTask?.title && (
            <>
              <div style={{ color: 'var(--rose-soft)', fontSize: 13 }}>·</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                {activeTask.title}
              </div>
            </>
          )}
        </div>

        <div style={{
          flex:          1,
          overflowY:     'auto',
          padding:       '20px 24px',
          display:       'flex',
          flexDirection: 'column',
          gap:           14,
        }}>
          {visibleMessages.map((m, i) => (
            <Bubble key={i} role={m.role} content={m.content} />
          ))}
          {loading && <Bubble role="assistant" content="thinking…" muted />}
          <div ref={bottomRef} />
        </div>

        <div style={{
          padding:    '16px 20px',
          borderTop:  '1px solid var(--rose-soft)',
          display:    'flex',
          gap:        10,
          alignItems: 'flex-end',
        }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Reply to Buddy…"
            rows={2}
            style={{
              flex:        1,
              resize:      'none',
              border:      '1.5px solid var(--lavender)',
              borderRadius: 12,
              padding:     '10px 14px',
              fontSize:    14,
              fontFamily:  'var(--font-body)',
              color:       'var(--text-main)',
              background:  'var(--lavender)',
              outline:     'none',
              lineHeight:  1.5,
              transition:  'border-color 0.15s',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent-pink)'}
            onBlur={e  => e.target.style.borderColor = 'var(--lavender)'}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            style={{
              padding:      '10px 20px',
              borderRadius: 12,
              background:   loading || !input.trim() ? 'var(--rose-soft)' : 'var(--accent-pink)',
              color:        loading || !input.trim() ? 'var(--text-muted)' : 'var(--white)',
              fontSize:     14,
              fontWeight:   600,
              transition:   'all 0.15s',
              height:       44,
              border:       'none',
              cursor:       loading || !input.trim() ? 'default' : 'pointer',
            }}
          >
            Send
          </button>
        </div>
      </div>

      <AgentBrainPanel reasoning={reasoning} />
    </div>
  )
}

function Bubble({ role, content, muted }) {
  const isAgent = role === 'assistant'
  return (
    <div style={{ display: 'flex', justifyContent: isAgent ? 'flex-start' : 'flex-end' }}>
      <div style={{
        maxWidth:    '80%',
        padding:     '12px 16px',
        borderRadius: isAgent ? '4px 16px 16px 16px' : '16px 4px 16px 16px',
        background:  isAgent ? 'var(--rose-soft)' : 'var(--blue-mist)',
        fontSize:    14,
        lineHeight:  1.6,
        color:       muted ? 'var(--text-muted)' : 'var(--text-main)',
        fontStyle:   muted ? 'italic' : 'normal',
        borderLeft:  isAgent ? '3px solid var(--accent-pink)' : 'none',
        borderRight: !isAgent ? '3px solid #7AACE4' : 'none',
      }}>
        {content}
      </div>
    </div>
  )
}