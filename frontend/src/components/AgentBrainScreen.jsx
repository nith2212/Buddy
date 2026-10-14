/**
 * AgentBrainScreen.jsx
 * --------------------
 * Full-page Agent Brain view (the 'Agent Brain' tab).
 *
 * V2 change: /memory/{user_id} now returns a list of objects
 * {key, value, confidence, source} instead of a flat dict.
 * MemoryRow updated to show confidence + source.
 * "Retrieved from Foundry IQ" label updated to "Retrieved from Knowledge Base".
 */

import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

function extractFrameworkTitles(text) {
  if (!text) return []
  const matches = text.match(/^#\s+(.+)$/gm) || []
  return matches.map(m => m.replace(/^#\s*(Intervention:\s*)?/, '').trim())
}

export default function AgentBrainScreen() {
  const [memory, setMemory]   = useState([])   // V2: list of {key, value, confidence, source}
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { fetchData() }, [])

  async function fetchData() {
    try {
      const [memRes, histRes] = await Promise.all([
        fetch(`${API}/memory/1`),
        fetch(`${API}/reasoning-history/1`),
      ])
      const memData  = await memRes.json()
      const histData = await histRes.json()
      // V2 memory is already a list — no Object.entries needed
      setMemory(Array.isArray(memData) ? memData : [])
      setHistory([...histData].reverse())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return (
    <BrainShell>
      <div style={{ color: '#6B5F8A', fontSize: 12, textAlign: 'center', paddingTop: 40 }}>
        loading…
      </div>
    </BrainShell>
  )

  return (
    <BrainShell>

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#E8C0D8', letterSpacing: '-0.3px' }}>
          Agent Brain
        </div>
        <div style={{ fontSize: 11, color: '#6B5F8A', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
          {history.length} reasoning step{history.length !== 1 ? 's' : ''} this session
        </div>
      </div>

      {/* Reasoning timeline */}
      {history.length === 0 ? (
        <div style={{ color: '#6B5F8A', fontSize: 12, lineHeight: 1.8 }}>
          No reasoning yet.<br />Start a conversation to see the agent think.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 28 }}>
          {history.map((step, i) => (
            <TimelineStep key={i} step={step} isLatest={i === 0} index={history.length - i} />
          ))}
        </div>
      )}

      <div style={{ borderTop: '1px solid #3D3460', margin: '24px 0' }} />

      {/* Full memory table — V2 format */}
      <BrainSection title="Everything I Know">
        {memory.length === 0 ? (
          <div style={{ color: '#6B5F8A', fontSize: 12 }}>No memory loaded.</div>
        ) : (
          memory.map((row, i) => (
            <MemoryRow
              key={i}
              label={row.key}
              value={row.value}
              confidence={row.confidence}
              source={row.source}
            />
          ))
        )}
      </BrainSection>

    </BrainShell>
  )
}

function TimelineStep({ step, isLatest, index }) {
  const topState = step.hypotheses?.[0]

  return (
    <div style={{
      background:   isLatest ? '#352B52' : '#1E1830',
      borderRadius: 12,
      padding:      '16px 18px',
      border:       isLatest ? '1px solid #4A3D6A' : '1px solid transparent',
    }}>

      <div style={{
        display:        'flex',
        justifyContent: 'space-between',
        alignItems:     'center',
        marginBottom:   12,
      }}>
        <div style={{ fontSize: 10, letterSpacing: 1.5, color: '#6B5F8A', textTransform: 'uppercase' }}>
          step {index}{isLatest && ' · latest'}
        </div>
        {topState && (
          <div style={{ fontSize: 11, color: isLatest ? '#E8C0D8' : '#9A8EC0', fontWeight: 600 }}>
            {topState.state} {Math.round(topState.confidence * 100)}%
          </div>
        )}
      </div>

      {step.observations?.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          {step.observations.map((o, i) => (
            <div key={i} style={{ color: '#9A8EC0', fontSize: 11, lineHeight: 1.6 }}>· {o}</div>
          ))}
        </div>
      )}

      {step.hypotheses?.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {step.hypotheses.map((h, i) => (
            <div key={i} style={{
              fontSize:   10,
              padding:    '3px 8px',
              borderRadius: 6,
              background: i === 0 ? '#4A3560' : '#2A2440',
              color:      i === 0 ? '#E8C0D8' : '#7A6E9A',
            }}>
              {h.state} {Math.round(h.confidence * 100)}%
            </div>
          ))}
        </div>
      )}

      {step.grounded_context && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 9, color: '#6B5F8A', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 6 }}>
            Retrieved from Knowledge Base
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {extractFrameworkTitles(step.grounded_context).map((title, i) => (
              <span key={i} style={{
                fontSize: 10, padding: '4px 10px', borderRadius: 6,
                background: '#2A2440', color: '#9A8EC0',
                border: '1px solid #3D3460',
              }}>
                📄 {title}
              </span>
            ))}
          </div>
        </div>
      )}

      <div style={{
        background:   '#1E1830',
        borderRadius: 8,
        padding:      '10px 12px',
        borderLeft:   '2px solid #E57399',
      }}>
        <div style={{ fontSize: 11, color: '#E8C0D8', fontWeight: 600, marginBottom: 4 }}>
          → {step.intervention_chosen}
        </div>
        {step.decision_reasoning && (
          <div style={{ fontSize: 11, color: '#9A8EC0', lineHeight: 1.5, fontStyle: 'italic' }}>
            "{step.decision_reasoning}"
          </div>
        )}
      </div>

    </div>
  )
}

function BrainShell({ children }) {
  return (
    <div style={{
      background:   'var(--brain-deep)',
      borderRadius: 20,
      padding:      '28px 24px',
      boxShadow:    'var(--card-shadow)',
      fontFamily:   'var(--font-mono)',
      color:        '#C8C0E8',
      minHeight:    'calc(100vh - 140px)',
    }}>
      {children}
    </div>
  )
}

function BrainSection({ title, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontSize:      9,
        letterSpacing: 2,
        color:         '#6B5F8A',
        textTransform: 'uppercase',
        marginBottom:  12,
        borderBottom:  '1px solid #3D3460',
        paddingBottom: 6,
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

/** V2: shows confidence bar + source badge alongside key/value */
function MemoryRow({ label, value, confidence, source }) {
  const sourceColor = {
    echo:        '#7BC47F',   // green — most trusted
    buddy:       '#9A8EC0',   // purple — recent observations
    onboarding:  '#6B5F8A',   // dim — cold-start prior
  }

  const pct = Math.round((confidence || 0) * 100)

  return (
    <div style={{
      display:       'flex',
      flexDirection: 'column',
      gap:           6,
      marginBottom:  12,
      padding:       '10px 12px',
      background:    '#1E1830',
      borderRadius:  8,
    }}>
      {/* Key + source badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 9, color: '#6B5F8A', letterSpacing: 1, textTransform: 'uppercase' }}>
          {label}
        </div>
        {source && (
          <div style={{
            fontSize:     9,
            padding:      '2px 7px',
            borderRadius: 5,
            background:   '#2A2440',
            color:        sourceColor[source] || '#6B5F8A',
            letterSpacing: 0.5,
          }}>
            {source}
          </div>
        )}
      </div>

      {/* Value */}
      <div style={{ fontSize: 12, color: '#C8C0E8', lineHeight: 1.5 }}>
        {value}
      </div>

      {/* Confidence bar */}
      {confidence !== undefined && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <div style={{ fontSize: 9, color: '#6B5F8A' }}>confidence</div>
            <div style={{ fontSize: 9, color: '#6B5F8A' }}>{pct}%</div>
          </div>
          <div style={{ height: 3, background: '#3D3460', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              height:     '100%',
              width:      `${pct}%`,
              background: sourceColor[source] || '#6B5F8A',
              borderRadius: 3,
              transition: 'width 0.4s ease',
            }} />
          </div>
        </div>
      )}
    </div>
  )
}