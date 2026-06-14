/**
 * AgentBrainPanel.jsx
 * -------------------
 * Sidebar panel rendered inside ChatScreen (right column).
 * Shows the agent's latest reasoning snapshot in real time after each reply.
 *
 * Sections:
 *   Observations   — what the agent noticed (postpone count, last event, user message)
 *   Hypotheses     — ranked work-state guesses with confidence bars
 *   Foundry IQ     — which framework docs were retrieved from Azure AI Search
 *   Intervention   — chosen intervention key + LLM's one-line reason
 *   Memory Used    — subset of user memory that influenced this decision
 *
 * extractFrameworkTitles() parses H1 headings from the raw markdown returned
 * by Foundry IQ so we can show doc names as pills instead of raw markdown.
 */

function extractFrameworkTitles(text) {
  if (!text) return []
  const matches = text.match(/^#\s+(.+)$/gm) || []
  return matches.map(m => m.replace(/^#\s*(Intervention:\s*)?/, '').trim())
}

export default function AgentBrainPanel({ reasoning }) {
  // Empty state — shown before first agent response
  if (!reasoning) return (
    <div style={{
      width: 260,
      background: 'var(--brain-deep)',
      borderRadius: 16,
      padding: '24px 20px',
      boxShadow: 'var(--card-shadow)',
      fontFamily: 'var(--font-mono)',
      color: '#6B5F8A',
      fontSize: 12,
      height: 'calc(100vh - 120px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      lineHeight: 1.6,
    }}>
      waiting for<br />agent response…
    </div>
  )

  const { observations, hypotheses, intervention_chosen, memory_used } = reasoning

  return (
    <div style={{
      width: 260,
      background: 'var(--brain-deep)',
      borderRadius: 16,
      padding: '20px',
      boxShadow: 'var(--card-shadow)',
      fontFamily: 'var(--font-mono)',
      color: '#C8C0E8',
      fontSize: 12,
      height: 'calc(100vh - 120px)',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
    }}>

      <div style={{ fontSize: 10, letterSpacing: 1.5, color: '#7A6E9A', textTransform: 'uppercase' }}>
        Agent Brain
      </div>

      <Section title="Observations">
        {observations?.map((o, i) => (
          <div key={i} style={{ color: '#B0A8D0', lineHeight: 1.6, marginBottom: 4 }}>· {o}</div>
        ))}
      </Section>

      <Section title="Hypotheses">
        {hypotheses?.map((h, i) => (
          <HypothesisBar key={i} state={h.state} confidence={h.confidence} highlight={i === 0} />
        ))}
      </Section>

      {reasoning.grounded_context && (
        <Section title="Retrieved from Foundry IQ">
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {extractFrameworkTitles(reasoning.grounded_context).map((title, i) => (
              <span key={i} style={{
                fontSize: 10, padding: '4px 10px', borderRadius: 6,
                background: '#2A2440', color: '#9A8EC0',
                border: '1px solid #3D3460',
              }}>
                📄 {title}
              </span>
            ))}
          </div>
        </Section>
      )}

      <Section title="Intervention">
        <div style={{
          background: '#3D3460',
          borderRadius: 8,
          padding: '8px 12px',
          color: '#E8C0D8',
          fontSize: 11,
          letterSpacing: 0.3,
          marginBottom: 8,
        }}>
          {intervention_chosen}
        </div>
        {reasoning.decision_reasoning && (
          <div style={{ color: '#9A8EC0', fontSize: 11, lineHeight: 1.5, fontStyle: 'italic' }}>
            "{reasoning.decision_reasoning}"
          </div>
        )}
      </Section>

      {memory_used && Object.keys(memory_used).length > 0 && (
        <Section title="Memory Used">
          {Object.entries(memory_used).map(([k, v]) => (
            <div key={k} style={{ marginBottom: 6 }}>
              <div style={{ color: '#7A6E9A', fontSize: 10, marginBottom: 2 }}>{k}</div>
              <div style={{ color: '#C8C0E8', lineHeight: 1.5 }}>{v}</div>
            </div>
          ))}
        </Section>
      )}

    </div>
  )
}

/** Section wrapper with a labelled divider. */
function Section({ title, children }) {
  return (
    <div>
      <div style={{
        fontSize: 9,
        letterSpacing: 1.5,
        color: '#6B5F8A',
        textTransform: 'uppercase',
        marginBottom: 10,
        borderBottom: '1px solid #3D3460',
        paddingBottom: 6,
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

/** Confidence bar for a single hypothesis. Top hypothesis is highlighted pink. */
function HypothesisBar({ state, confidence, highlight }) {
  const pct = Math.round(confidence * 100)
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: 4,
        color: highlight ? '#E8C0D8' : '#9A8EC0',
        fontSize: 11,
      }}>
        <span>{state}</span>
        <span>{pct}%</span>
      </div>
      <div style={{ height: 4, background: '#3D3460', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: highlight ? 'var(--accent-pink)' : '#6B5F8A',
          borderRadius: 4,
          transition: 'width 0.6s ease',
        }} />
      </div>
    </div>
  )
}
