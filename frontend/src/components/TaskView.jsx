/**
 * TaskView.jsx
 * ------------
 * Main task dashboard screen (the 'Task' tab).
 *
 * Sections:
 *   - Floating notification bubble (top-right, fixed) — shows Buddy's latest message.
 *     Clicking it navigates to chat. If the user just celebrated, it skips resetChat()
 *     so the congrats message is preserved in the chat view.
 *   - Active task card — hardcoded demo task
 *   - History timeline — live from /task/1, updates after simulate
 *   - Action buttons — Mark Done + Simulate Next Day
 *
 * agentMessage is lifted to App.jsx so it persists across tab navigation.
 * celebrated flag prevents the notification click from wiping the celebration message.
 */

import { useState, useEffect } from 'react'
import Confetti from './Confetti'
import robotImg from '../assets/image.png'

const API = 'http://localhost:8000'

export default function TaskView({
  setScreen,
  setMessages,
  setReasoning,
  setInitiated,
  resetChat,
  agentMessage,
  setAgentMessage,
}) {
  const [simulating, setSimulating]     = useState(false)
  const [completing, setCompleting]     = useState(false)
  const [showConfetti, setShowConfetti] = useState(false)
  const [events, setEvents]             = useState([])
  const [celebrated, setCelebrated]     = useState(false)

  // Fetch live task history on mount
  useEffect(() => {
    fetchEvents()
  }, [])

  function fetchEvents() {
    fetch(`${API}/task/1`)
      .then(r => r.json())
      .then(data => setEvents(data.events || []))
      .catch(() => {})
  }

  // Simulate a day passing — logs missed_checkin, gets proactive message,
  // updates notification bubble (does NOT auto-navigate to chat)
  async function handleSimulate() {
    setSimulating(true)
    try {
      const res  = await fetch(`${API}/simulate-next-day`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const data = await res.json()
      setMessages([{ role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
      setInitiated(true)
      setAgentMessage(data.reply)
      fetchEvents()
    } catch (e) {
      console.error(e)
    } finally {
      setSimulating(false)
    }
  }

  // Mark task complete — clears notification, calls /celebrate, fires confetti after 1s
  async function handleComplete() {
    setCompleting(true)
    setAgentMessage(null)
    try {
      const res  = await fetch(`${API}/celebrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: 1 }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
      setInitiated(true)
      setCelebrated(true)
      setAgentMessage(data.reply)
      setTimeout(() => setShowConfetti(true), 1000)
      setTimeout(() => setShowConfetti(false), 3000)
    } catch (e) {
      console.error(e)
    } finally {
      setCompleting(false)
    }
  }

  // Notification click — skip resetChat if we just celebrated to preserve the congrats message
  function handleNotificationClick() {
    if (!celebrated) resetChat()
    setScreen('chat')
  }

  const dotColor = {
    postponed:      'var(--accent-pink)',
    'check-in':     '#9B8EC4',
    completed:      '#7BC47F',
    missed_checkin: '#E5A030',
  }

  return (
    <>
      <Confetti show={showConfetti} />

      {/* Floating notification bubble — fixed top-right, always visible on task screen */}
      <div
        onClick={handleNotificationClick}
        title="Click to open chat"
        style={{
          position: 'fixed',
          top: 72,
          right: 20,
          width: 280,
          background: 'var(--white)',
          borderRadius: 16,
          boxShadow: '0 4px 24px rgba(90,60,120,0.18)',
          padding: '14px 16px 14px 14px',
          display: 'flex',
          gap: 12,
          alignItems: 'flex-start',
          cursor: 'pointer',
          zIndex: 1000,
          animation: 'slideInRight 0.3s ease',
          border: '1px solid var(--rose-soft)',
        }}
      >
        <img
          src={robotImg}
          alt="Buddy"
          style={{
            width: 36, height: 36,
            borderRadius: '50%',
            objectFit: 'cover',
            flexShrink: 0,
            border: '2px solid var(--accent-pink)',
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-pink)', marginBottom: 4, letterSpacing: 0.5 }}>
            Buddy
          </div>
          <div style={{
            fontSize: 13,
            lineHeight: 1.5,
            color: agentMessage ? 'var(--text-main)' : 'var(--text-muted)',
            fontStyle: agentMessage ? 'normal' : 'italic',
          }}>
            {agentMessage || 'Buddy is thinking…'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
            Tap to reply →
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingTop: 8 }}>

        {/* Active task card */}
        <div style={{
          background: 'var(--white)',
          borderRadius: 16,
          padding: '24px 28px',
          boxShadow: 'var(--card-shadow)',
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>
            Active Task
          </div>
          <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--text-main)', marginBottom: 6 }}>
            Study for AWS CCP exam
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            Due in 3 days
          </div>
        </div>

        {/* History timeline — live from DB */}
        <div style={{
          background: 'var(--white)',
          borderRadius: 16,
          padding: '24px 28px',
          boxShadow: 'var(--card-shadow)',
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 }}>
            History
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {events.length === 0 && (
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>No events yet.</div>
            )}
            {events.map((e, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{
                  width: 8, height: 8,
                  borderRadius: '50%',
                  background: dotColor[e.event_type] || 'var(--text-muted)',
                  marginTop: 5,
                  flexShrink: 0,
                }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-main)', textTransform: 'capitalize' }}>
                    {e.event_type?.replace('_', ' ')}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    {e.note} · {e.created_at ? new Date(e.created_at).toLocaleString() : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Action buttons — equal size 2-column grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <button
            onClick={handleComplete}
            disabled={completing}
            style={{
              padding: '14px 0',
              borderRadius: 12,
              background: completing ? 'var(--lavender)' : '#D4F0D4',
              color: completing ? 'var(--text-muted)' : '#2D5A2D',
              fontSize: 14,
              fontWeight: 600,
              transition: 'all 0.15s',
            }}
          >
            {completing ? '✓ marking…' : '✓ Mark task as done'}
          </button>

          <button
            onClick={handleSimulate}
            disabled={simulating}
            style={{
              padding: '14px 0',
              borderRadius: 12,
              background: simulating ? 'var(--lavender)' : 'var(--brain-deep)',
              color: simulating ? 'var(--text-muted)' : '#E8C0D8',
              fontSize: 14,
              fontWeight: 500,
              fontFamily: 'var(--font-mono)',
              letterSpacing: 0.5,
              transition: 'all 0.2s',
            }}
          >
            {simulating ? 'thinking…' : '⏭ simulate next day'}
          </button>
        </div>

      </div>
    </>
  )
}
