/**
 * OnboardingForm.jsx
 * ------------------
 * Multi-step onboarding form. One question per screen, progress dots at top.
 * Matches the calm/warm tone of BuddyIntro and BuddyStory.
 *
 * Questions map directly to the onboarding table:
 *   1. preferred_work_time     — morning / afternoon / evening / night
 *   2. work_session_style      — short_bursts / long_sessions
 *   3. procrastination_style   — overwhelmed / unclear / tired / bored / perfectionism / other
 *   4. notification_opted_in   — yes / not yet (soft opt-in, not a wall)
 *
 * On submit: POST /onboarding → backend writes onboarding row + seeds memory
 * at confidence 0.3, source 'onboarding'. Echo will refine these from day one.
 *
 * Phase flow in App.jsx: intro → story → onboarding → app
 */

import { useState } from 'react'

const API = 'http://localhost:8000'

const STEPS = [
  {
    key:      'preferred_work_time',
    question: "When do you usually do your best work?",
    subtext:  "Buddy will check in around that time — not against it.",
    options: [
      { value: 'morning',   label: 'Morning',   emoji: '🌅' },
      { value: 'afternoon', label: 'Afternoon', emoji: '☀️' },
      { value: 'evening',   label: 'Evening',   emoji: '🌆' },
      { value: 'night',     label: 'Night',     emoji: '🌙' },
    ],
  },
  {
    key:      'work_session_style',
    question: "How do you prefer to work?",
    subtext:  "There's no right answer — Buddy adapts to you, not the other way around.",
    options: [
      { value: 'short_bursts',   label: 'Short bursts',   emoji: '⚡', desc: '25–30 min, then a break' },
      { value: 'long_sessions',  label: 'Long sessions',  emoji: '🔵', desc: 'Get in the zone and stay there' },
    ],
  },
  {
    key:      'procrastination_style',
    question: "When you avoid something, it's usually because…",
    subtext:  "Buddy uses this to know where to start, not to judge.",
    options: [
      { value: 'overwhelmed',   label: 'It feels too big',         emoji: '🌊' },
      { value: 'unclear',       label: "I don't know where to start", emoji: '🌫️' },
      { value: 'tired',         label: "I'm just drained",         emoji: '😮‍💨' },
      { value: 'bored',         label: "It's honestly just boring", emoji: '😑' },
      { value: 'perfectionism', label: "I want it to be perfect",  emoji: '🔍' },
      { value: 'other',         label: "It varies",                emoji: '🤷' },
    ],
  },
  {
    key:      'notification_opted_in',
    question: "Can Buddy check in on you?",
    subtext:  "Not spam — one gentle nudge when you've gone quiet. You can always say LATER.",
    options: [
      { value: true,  label: 'Yes, check in on me', emoji: '🔔' },
      { value: false, label: 'Not yet',              emoji: '🔕', desc: "You can turn this on later" },
    ],
  },
]

export default function OnboardingForm({ onComplete }) {
  const [step, setStep]       = useState(0)
  const [answers, setAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]     = useState(null)

  const current = STEPS[step]
  const isLast  = step === STEPS.length - 1

  async function handleSelect(value) {
    const updated = { ...answers, [current.key]: value }
    setAnswers(updated)

    // Small delay so the selected state visually registers before advancing
    await new Promise(r => setTimeout(r, 220))

    if (!isLast) {
      setStep(s => s + 1)
      return
    }

    // Last step — submit
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${API}/onboarding`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ user_id: 1, ...updated }),
      })
      if (!res.ok) throw new Error('Failed to save onboarding.')
      onComplete()
    } catch (e) {
      setError("Couldn't save your answers — is the backend running?")
      setSubmitting(false)
    }
  }

  function handleBack() {
    if (step > 0) setStep(s => s - 1)
  }

  const selectedForStep = answers[current.key]

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

      {/* Progress dots */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 48 }}>
        {STEPS.map((_, i) => (
          <div
            key={i}
            style={{
              width:        i === step ? 24 : 8,
              height:       8,
              borderRadius: 4,
              background:   i <= step ? 'var(--accent-pink)' : 'var(--rose-soft)',
              transition:   'all 0.3s ease',
            }}
          />
        ))}
      </div>

      {/* Question card */}
      <div style={{
        width:        '100%',
        maxWidth:     460,
        background:   'var(--white)',
        borderRadius: 24,
        padding:      '36px 32px',
        boxShadow:    'var(--card-shadow)',
      }}>

        {/* Step label */}
        <div style={{
          fontSize:      11,
          fontWeight:    600,
          color:         'var(--accent-pink)',
          letterSpacing: 1.5,
          textTransform: 'uppercase',
          marginBottom:  12,
        }}>
          {step + 1} of {STEPS.length}
        </div>

        {/* Question */}
        <div style={{
          fontSize:     22,
          fontWeight:   600,
          color:        'var(--text-main)',
          lineHeight:   1.3,
          marginBottom: 8,
        }}>
          {current.question}
        </div>

        {/* Subtext */}
        <div style={{
          fontSize:     13,
          color:        'var(--text-muted)',
          lineHeight:   1.6,
          marginBottom: 28,
        }}>
          {current.subtext}
        </div>

        {/* Options */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {current.options.map(opt => {
            const isSelected = selectedForStep === opt.value
            return (
              <button
                key={String(opt.value)}
                onClick={() => !submitting && handleSelect(opt.value)}
                disabled={submitting}
                style={{
                  display:       'flex',
                  alignItems:    'center',
                  gap:           14,
                  padding:       '14px 18px',
                  borderRadius:  14,
                  border:        `1.5px solid ${isSelected ? 'var(--accent-pink)' : 'var(--rose-soft)'}`,
                  background:    isSelected ? 'var(--rose-soft)' : 'var(--white)',
                  cursor:        submitting ? 'default' : 'pointer',
                  textAlign:     'left',
                  transition:    'all 0.15s ease',
                  width:         '100%',
                }}
                onMouseEnter={e => {
                  if (!submitting && !isSelected)
                    e.currentTarget.style.borderColor = 'var(--accent-pink)'
                }}
                onMouseLeave={e => {
                  if (!isSelected)
                    e.currentTarget.style.borderColor = 'var(--rose-soft)'
                }}
              >
                <span style={{ fontSize: 22, flexShrink: 0 }}>{opt.emoji}</span>
                <div>
                  <div style={{
                    fontSize:   14,
                    fontWeight: isSelected ? 600 : 500,
                    color:      isSelected ? 'var(--accent-pink)' : 'var(--text-main)',
                    transition: 'color 0.15s',
                  }}>
                    {opt.label}
                  </div>
                  {opt.desc && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                      {opt.desc}
                    </div>
                  )}
                </div>
                {isSelected && (
                  <div style={{
                    marginLeft:  'auto',
                    color:       'var(--accent-pink)',
                    fontSize:    18,
                    flexShrink:  0,
                  }}>
                    ✓
                  </div>
                )}
              </button>
            )
          })}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            marginTop:    16,
            fontSize:     13,
            color:        'var(--accent-pink)',
            textAlign:    'center',
          }}>
            {error}
          </div>
        )}

        {/* Submitting state */}
        {submitting && (
          <div style={{
            marginTop:  20,
            fontSize:   13,
            color:      'var(--text-muted)',
            textAlign:  'center',
          }}>
            Setting up Buddy…
          </div>
        )}
      </div>

      {/* Back button — only shown after step 1 */}
      {step > 0 && !submitting && (
        <button
          onClick={handleBack}
          style={{
            marginTop:    24,
            fontSize:     13,
            color:        'var(--text-muted)',
            background:   'none',
            border:       'none',
            cursor:       'pointer',
            padding:      '8px 16px',
          }}
        >
          ← Back
        </button>
      )}

    </div>
  )
}