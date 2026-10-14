/**
 * TaskCreate.jsx
 * --------------
 * Task creation screen. Shown after onboarding, before the main app.
 * User gives their task a name and a due date — that's it.
 * Buddy and Echo start tracking it from this moment.
 *
 * Keeps it simple on purpose: no priority, no tags, no subtasks.
 * Complexity lives in conversation, not in metadata the user has to fill in.
 *
 * On submit: POST /task → returns {task_id, title, deadline}
 * onComplete(task) passes the task up to App.jsx state.
 */

import { useState } from 'react'

const API = 'http://localhost:8000'

export default function TaskCreate({ onComplete }) {
  const [title, setTitle]       = useState('')
  const [deadline, setDeadline] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]       = useState(null)

  // Minimum date = today
  const today = new Date().toISOString().split('T')[0]

  async function handleSubmit() {
    if (!title.trim()) {
      setError("Give the task a name first.")
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${API}/task`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          user_id:  1,
          title:    title.trim(),
          deadline: deadline || null,
        }),
      })
      if (!res.ok) throw new Error('Failed to create task.')
      const data = await res.json()
      onComplete(data)  // passes {id, title, deadline, status} up to App.jsx
    } catch (e) {
      setError("Couldn't reach Buddy's backend. Is it running?")
      setSubmitting(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter') handleSubmit()
  }

  return (
    <div style={{
      minHeight:      '100vh',
      display:        'flex',
      flexDirection:  'column',
      alignItems:     'center',
      justifyContent: 'center',
      padding:        '24px 16px',
      background:     'var(--bg)',
    }}>

      <div style={{
        width:        '100%',
        maxWidth:     460,
        background:   'var(--white)',
        borderRadius: 24,
        padding:      '40px 32px',
        boxShadow:    'var(--card-shadow)',
      }}>

        {/* Header */}
        <div style={{
          fontSize:     11,
          fontWeight:   600,
          color:        'var(--accent-pink)',
          letterSpacing: 1.5,
          textTransform: 'uppercase',
          marginBottom: 12,
        }}>
          Let's start somewhere
        </div>

        <div style={{
          fontSize:     24,
          fontWeight:   600,
          color:        'var(--text-main)',
          lineHeight:   1.3,
          marginBottom: 8,
        }}>
          What's the one thing you want Buddy to help you with?
        </div>

        <div style={{
          fontSize:     13,
          color:        'var(--text-muted)',
          lineHeight:   1.6,
          marginBottom: 32,
        }}>
          Just one thing for now. Buddy works best when it's focused.
        </div>

        {/* Task name */}
        <div style={{ marginBottom: 20 }}>
          <label style={{
            display:      'block',
            fontSize:     12,
            fontWeight:   600,
            color:        'var(--text-muted)',
            marginBottom: 8,
            letterSpacing: 0.5,
          }}>
            What is it?
          </label>
          <input
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            onKeyDown={handleKey}
            placeholder="e.g. Study for AWS exam, finish the report..."
            autoFocus
            style={{
              width:        '100%',
              padding:      '14px 16px',
              borderRadius: 12,
              border:       `1.5px solid ${title ? 'var(--accent-pink)' : 'var(--rose-soft)'}`,
              fontSize:     15,
              color:        'var(--text-main)',
              background:   'var(--lavender)',
              outline:      'none',
              transition:   'border-color 0.15s',
              boxSizing:    'border-box',
              fontFamily:   'var(--font-body)',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent-pink)'}
            onBlur={e  => e.target.style.borderColor = title ? 'var(--accent-pink)' : 'var(--rose-soft)'}
          />
        </div>

        {/* Due date — optional */}
        <div style={{ marginBottom: 32 }}>
          <label style={{
            display:      'block',
            fontSize:     12,
            fontWeight:   600,
            color:        'var(--text-muted)',
            marginBottom: 8,
            letterSpacing: 0.5,
          }}>
            When does it need to be done? <span style={{ fontWeight: 400 }}>(optional)</span>
          </label>
          <input
            type="date"
            value={deadline}
            min={today}
            onChange={e => setDeadline(e.target.value)}
            style={{
              width:        '100%',
              padding:      '14px 16px',
              borderRadius: 12,
              border:       '1.5px solid var(--rose-soft)',
              fontSize:     14,
              color:        deadline ? 'var(--text-main)' : 'var(--text-muted)',
              background:   'var(--lavender)',
              outline:      'none',
              transition:   'border-color 0.15s',
              boxSizing:    'border-box',
              fontFamily:   'var(--font-body)',
              cursor:       'pointer',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent-pink)'}
            onBlur={e  => e.target.style.borderColor = 'var(--rose-soft)'}
          />
          {!deadline && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
              No deadline? Buddy will still check in — just without the urgency signal.
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            fontSize:     13,
            color:        'var(--accent-pink)',
            marginBottom: 16,
          }}>
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={submitting || !title.trim()}
          style={{
            width:        '100%',
            padding:      '16px 0',
            borderRadius: 14,
            background:   submitting || !title.trim()
              ? 'var(--rose-soft)'
              : 'var(--accent-pink)',
            color:        submitting || !title.trim()
              ? 'var(--text-muted)'
              : 'var(--white)',
            fontSize:     15,
            fontWeight:   600,
            border:       'none',
            cursor:       submitting || !title.trim() ? 'default' : 'pointer',
            transition:   'all 0.15s',
          }}
        >
          {submitting ? 'Starting up…' : 'Let\'s go →'}
        </button>

      </div>

    </div>
  )
}