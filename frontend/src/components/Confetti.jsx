import { useMemo } from 'react'

const COLORS = ['#E57399', '#9B8EC4', '#7AACE4', '#FFE4EE', '#E8E4FF']

const pieces = Array.from({ length: 60 }, (_, i) => ({
  left:     Math.random() * 100,
  delay:    Math.random() * 0.15,
  duration: 0.8 + Math.random() * 0.5,
  color:    COLORS[i % COLORS.length],
  size:     6 + Math.random() * 6,
  fromTop:  i % 2 === 0,
}))

export default function Confetti({ show }) {
  if (!show) return null

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0,
      width: '100%', height: '100vh',
      pointerEvents: 'none', zIndex: 9999,
    }}>
      {pieces.map((p, i) => (
        <div key={i} style={{
          position: 'fixed',
          width: p.size, height: p.size,
          background: p.color,
          borderRadius: '50%',
          left: p.left + '%',
          top: p.fromTop ? '2px' : '50%',
          animation: `confetti-fall ${p.duration}s ease-in ${p.delay}s forwards`,
        }} />
      ))}
    </div>
  )
}
