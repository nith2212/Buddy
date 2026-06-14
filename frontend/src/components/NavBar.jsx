/**
 * NavBar.jsx
 * ----------
 * Top navigation bar. Shows the Buddy logo + 3 tab buttons.
 * Active tab is highlighted with a pink underline border.
 * The Agent Brain tab has a pulsing dot indicator.
 */

import robotImg from '../assets/image.png'

export default function NavBar({ screen, setScreen }) {
  const tabs = [
    { id: 'task',  label: 'Task' },
    { id: 'chat',  label: 'Chat' },
    { id: 'brain', label: 'Agent Brain' },
  ]

  return (
    <nav style={{
      background: 'var(--white)',
      borderBottom: '1px solid var(--rose-soft)',
      padding: '0 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      boxShadow: 'var(--card-shadow)',
    }}>
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 0' }}>
        <img src={robotImg} alt="Buddy" style={{ width: 32, height: 32, objectFit: 'contain' }} />
        <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--accent-pink)', letterSpacing: '-0.3px' }}>
          Buddy
        </span>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4 }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setScreen(t.id)}
            style={{
              padding: '14px 18px',
              fontSize: 13,
              fontWeight: screen === t.id ? 600 : 400,
              color: screen === t.id ? 'var(--accent-pink)' : 'var(--text-muted)',
              background: 'none',
              borderBottom: screen === t.id ? '2px solid var(--accent-pink)' : '2px solid transparent',
              borderRadius: 0,
              transition: 'all 0.15s ease',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {t.label}
            {/* Pulsing dot on Agent Brain tab */}
            {t.id === 'brain' && (
              <span style={{
                width: 6, height: 6, borderRadius: '50%',
                background: '#9B8EC4',
                display: 'inline-block',
                animation: 'pulse 2s infinite',
              }} />
            )}
          </button>
        ))}
      </div>
    </nav>
  )
}
