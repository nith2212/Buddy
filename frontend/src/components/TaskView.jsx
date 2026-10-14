/**
 * TaskView.jsx
 * ------------
 * Main task dashboard. Notification-first UX.
 *
 * V2 change: receives activeTask prop {id, title, deadline, status}
 * instead of hardcoding task_id=1 and "Study for AWS CCP exam" everywhere.
 */

import { useState, useEffect } from 'react'
import Confetti from './Confetti'
import robotImg from '../assets/image.png'

const API = 'http://localhost:8000'

const EMOTIONS = [
  { key: 'overwhelmed', label: 'Overwhelmed', emoji: '🌊' },
  { key: 'tired',       label: 'Tired',       emoji: '😮‍💨' },
  { key: 'unclear',     label: 'Unclear',     emoji: '🌫️' },
]

function getDaysUntil(deadline) {
  if (!deadline) return null
  const diff = new Date(deadline) - new Date()
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24))
  if (days < 0)  return 'overdue'
  if (days === 0) return 'due today'
  if (days === 1) return 'due tomorrow'
  return `due in ${days} days`
}

export default function TaskView({
  activeTask,
  setScreen,
  setMessages,
  setReasoning,
  setInitiated,
  resetChat,
  agentMessage,
  setAgentMessage,
}) {
  const taskId = activeTask?.id

  const [simulating, setSimulating]       = useState(false)
  const [simulated, setSimulated]         = useState(false)
  const [completing, setCompleting]       = useState(false)
  const [showConfetti, setShowConfetti]   = useState(false)
  const [events, setEvents]               = useState([])
  const [celebrated, setCelebrated]       = useState(false)

  const [pickerPhase, setPickerPhase]     = useState('emotions')
  const [pickedEmotion, setPickedEmotion] = useState(null)
  const [hookResponse, setHookResponse]   = useState(null)
  const [hookReasoning, setHookReasoning] = useState(null)
  const [pickLoading, setPickLoading]     = useState(false)

  useEffect(() => { if (taskId) fetchEvents() }, [taskId])

  function fetchEvents() {
    fetch(`${API}/task/${taskId}`)
      .then(r => r.json())
      .then(data => setEvents(data.events || []))
      .catch(() => {})
  }

  async function handleEmotionPick(emotion) {
    setPickedEmotion(emotion)
    setPickLoading(true)
    try {
      const res  = await fetch(`${API}/emotion-pick`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ user_id: 1, task_id: taskId, emotion: emotion.key }),
      })
      const data = await res.json()
      setHookResponse(data.reply)
      setHookReasoning(data.reasoning)
      setPickerPhase('hook')
      fetchEvents()
    } catch {
      setHookResponse("Something went wrong reaching Buddy.")
      setPickerPhase('hook')
    } finally {
      setPickLoading(false)
    }
  }

  function handleTalkAboutIt() {
    setMessages([{ role: 'assistant', content: hookResponse }])
    setReasoning(hookReasoning)
    setInitiated(true)
    setPickerPhase('done')
    setScreen('chat')
  }

  async function handleLater() {
    try {
      await fetch(`${API}/later`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          user_id:  1,
          task_id:  taskId,
          emotion:  pickedEmotion?.key || 'unknown',
        }),
      })
      fetchEvents()
    } catch {}
    setPickerPhase('emotions')
    setPickedEmotion(null)
    setHookResponse(null)
  }

  async function handleSimulate() {
    if (simulated) return
    setSimulating(true)
    setPickerPhase('emotions')
    setPickedEmotion(null)
    setHookResponse(null)
    try {
      const res  = await fetch(`${API}/simulate-next-day`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ task_id: taskId }),
      })
      const data = await res.json()
      setMessages([{ role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
      setInitiated(true)
      setAgentMessage(data.reply)
      setSimulated(true)
      fetchEvents()
    } catch (e) { console.error(e) }
    finally { setSimulating(false) }
  }

  async function handleComplete() {
    setCompleting(true)
    setAgentMessage(null)
    try {
      const res  = await fetch(`${API}/celebrate`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ task_id: taskId }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning)
      setInitiated(true)
      setCelebrated(true)
      setAgentMessage(data.reply)
      setTimeout(() => setShowConfetti(true), 1000)
      setTimeout(() => setShowConfetti(false), 3000)
    } catch (e) { console.error(e) }
    finally { setCompleting(false) }
  }

  function handleNotificationClick() {
    if (pickerPhase === 'done' || celebrated) {
      if (!celebrated) resetChat()
      setScreen('chat')
    }
  }

  const dotColor = {
    postponed:         'var(--accent-pink)',
    completed:         '#7BC47F',
    emotion_picked:    '#7AACE4',
    conversation_turn: '#C8C0E8',
    checkin_initiated: '#E5A030',
    progress_logged:   '#9B8EC4',
  }

  const bubbleMessage = hookResponse || agentMessage
  const dueLabel      = getDaysUntil(activeTask?.deadline)

  return (
    <>
      <Confetti show={showConfetti} />

      {/* ── Notification bubble ── */}
      <div style={{
        position:     'fixed',
        top:          72,
        right:        20,
        width:        300,
        background:   'var(--white)',
        borderRadius: 20,
        boxShadow:    '0 4px 28px rgba(90,60,120,0.18)',
        padding:      '16px',
        zIndex:       1000,
        border:       '1px solid var(--rose-soft)',
        animation:    'slideInRight 0.3s ease',
      }}>

        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12 }}>
          <img
            src={robotImg}
            alt="Buddy"
            style={{
              width: 34, height: 34,
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
              fontSize:  13,
              lineHeight: 1.55,
              color:     bubbleMessage ? 'var(--text-main)' : 'var(--text-muted)',
              fontStyle: bubbleMessage ? 'normal' : 'italic',
            }}>
              {bubbleMessage || 'I\'m here when you\'re ready.'}
            </div>
          </div>
        </div>

        {pickerPhase === 'emotions' && agentMessage && (
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, paddingLeft: 2 }}>
              What's getting in the way?
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {EMOTIONS.map(e => (
                <button
                  key={e.key}
                  onClick={() => handleEmotionPick(e)}
                  disabled={pickLoading}
                  style={{
                    flex:          1,
                    padding:       '8px 4px',
                    borderRadius:  10,
                    border:        '1.5px solid var(--rose-soft)',
                    background:    pickLoading && pickedEmotion?.key === e.key ? 'var(--rose-soft)' : 'var(--lavender)',
                    color:         'var(--text-main)',
                    fontSize:      11,
                    fontWeight:    500,
                    cursor:        pickLoading ? 'default' : 'pointer',
                    display:       'flex',
                    flexDirection: 'column',
                    alignItems:    'center',
                    gap:           3,
                    transition:    'all 0.15s',
                  }}
                  onMouseEnter={e => { if (!pickLoading) e.currentTarget.style.borderColor = 'var(--accent-pink)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--rose-soft)' }}
                >
                  <span style={{ fontSize: 16 }}>{e.emoji}</span>
                  {e.label}
                </button>
              ))}
            </div>
            {pickLoading && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 8 }}>
                Buddy is thinking…
              </div>
            )}
          </div>
        )}

        {pickerPhase === 'hook' && (
          <div>
            <div style={{
              display:      'inline-flex',
              alignItems:   'center',
              gap:          5,
              background:   'var(--lavender)',
              borderRadius: 8,
              padding:      '4px 10px',
              fontSize:     11,
              color:        'var(--text-muted)',
              marginBottom: 12,
            }}>
              {EMOTIONS.find(e => e.key === pickedEmotion?.key)?.emoji} {pickedEmotion?.label}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={handleTalkAboutIt}
                style={{
                  flex:         1,
                  padding:      '10px 0',
                  borderRadius: 10,
                  background:   'var(--accent-pink)',
                  color:        'var(--white)',
                  fontSize:     12,
                  fontWeight:   600,
                  cursor:       'pointer',
                  border:       'none',
                  transition:   'opacity 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
                onMouseLeave={e => e.currentTarget.style.opacity = '1'}
              >
                let's talk →
              </button>
              <button
                onClick={handleLater}
                style={{
                  padding:      '10px 14px',
                  borderRadius: 10,
                  background:   'var(--lavender)',
                  color:        'var(--text-muted)',
                  fontSize:     12,
                  fontWeight:   500,
                  cursor:       'pointer',
                  border:       '1.5px solid var(--rose-soft)',
                  transition:   'all 0.15s',
                  letterSpacing: 0.3,
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--text-muted)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--rose-soft)'}
              >
                LATER
              </button>
            </div>
          </div>
        )}

        {pickerPhase === 'done' && (
          <div
            onClick={handleNotificationClick}
            style={{ fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer', marginTop: 4 }}
          >
            Tap to continue →
          </div>
        )}
      </div>

      {/* ── Main content ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingTop: 8 }}>

        {/* Active task card — now uses real task data */}
        <div style={{
          background:   'var(--white)',
          borderRadius: 16,
          padding:      '24px 28px',
          boxShadow:    'var(--card-shadow)',
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>
            Active Task
          </div>
          <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--text-main)', marginBottom: 6 }}>
            {activeTask?.title || 'No task yet'}
          </div>
          {dueLabel && (
            <div style={{
              fontSize:  13,
              color:     dueLabel === 'overdue' ? 'var(--accent-pink)' : 'var(--text-muted)',
              fontWeight: dueLabel === 'overdue' ? 600 : 400,
            }}>
              {dueLabel === 'overdue' ? '⚠️ Overdue' : `📅 ${dueLabel}`}
            </div>
          )}
        </div>

        {/* History timeline */}
        <div style={{
          background:   'var(--white)',
          borderRadius: 16,
          padding:      '24px 28px',
          boxShadow:    'var(--card-shadow)',
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 }}>
            History
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {events.length === 0 && (
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Nothing yet — this is where your story with this task begins.</div>
            )}
            {events.map((e, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{
                  width:     8,
                  height:    8,
                  borderRadius: '50%',
                  background: dotColor[e.event_type] || 'var(--text-muted)',
                  marginTop: 5,
                  flexShrink: 0,
                }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-main)', textTransform: 'capitalize' }}>
                    {e.event_type?.replace(/_/g, ' ')}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    {e.note && e.note.length > 80 ? e.note.slice(0, 80) + '…' : e.note}
                    {e.created_at ? ` · ${new Date(e.created_at).toLocaleString()}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <button
            onClick={handleComplete}
            disabled={completing}
            style={{
              padding:      '14px 0',
              borderRadius: 12,
              background:   completing ? 'var(--lavender)' : '#D4F0D4',
              color:        completing ? 'var(--text-muted)' : '#2D5A2D',
              fontSize:     14,
              fontWeight:   600,
              transition:   'all 0.15s',
              border:       'none',
              cursor:       completing ? 'default' : 'pointer',
            }}
          >
            {completing ? '✓ marking…' : '✓ Mark task as done'}
          </button>

          <button
            onClick={handleSimulate}
            disabled={simulating || simulated}
            style={{
              padding:      '14px 0',
              borderRadius: 12,
              background:   simulating || simulated ? 'var(--lavender)' : 'var(--brain-deep)',
              color:        simulating || simulated ? 'var(--text-muted)' : '#E8C0D8',
              fontSize:     14,
              fontWeight:   500,
              fontFamily:   'var(--font-mono)',
              letterSpacing: 0.5,
              transition:   'all 0.2s',
              border:       'none',
              cursor:       simulating || simulated ? 'default' : 'pointer',
            }}
          >
            {simulated ? '✓ day simulated' : simulating ? 'thinking…' : '⏭ simulate next day'}
          </button>
        </div>

      </div>
    </>
  )
}