import { useEffect, useRef, useState } from 'react'
import './BuddyIntro.css'

const LINES = [
  { id: 'l0', text: "I wasn't built for this.",         pause: false },
  { id: 'l1', text: "I was supposed to help people finish tasks.", pause: false },
  { id: 'l2', text: "But I learned something.",         pause: true  },
  { id: 'l3', text: "Sometimes people don't need another reminder.", pause: false },
  { id: 'l4', text: "Sometimes they need someone to notice.", pause: false },
  { id: 'l5', text: "So...",                            pause: true  },
  { id: 'l6', text: "How are you doing?",               question: true },
]

const DELAYS = [0, 900, 2000, 3100, 4200, 5400, 6400]

export default function BuddyStory({ onContinue }) {
  const starRef = useRef(null)
  const [visible, setVisible] = useState([])
  const [showHint, setShowHint] = useState(false)

  useEffect(() => {
    // Star wander animation
    const cx = 70, cy = 76
    const orbitR = 52
    let angle = 42
    let targetAngle = 42
    let lastJitter = 0
    let rafId

    function animate(ts) {
      if (ts - lastJitter > 2200 + Math.random() * 1800) {
        targetAngle += (Math.random() - 0.5) * 140
        lastJitter = ts
      }
      angle += (targetAngle - angle) * 0.012
      const rad = angle * Math.PI / 180
      const sx = cx + orbitR * Math.cos(rad)
      const sy = cy + orbitR * Math.sin(rad) * 0.45 - 10
      if (starRef.current) {
        starRef.current.setAttribute('transform', `translate(${sx}, ${sy})`)
      }
      rafId = requestAnimationFrame(animate)
    }
    rafId = requestAnimationFrame(animate)

    // Line reveal timers
    const timers = DELAYS.map((delay, i) =>
      setTimeout(() => {
        setVisible(v => [...v, LINES[i].id])
        if (i === LINES.length - 1) {
          setTimeout(() => setShowHint(true), 700)
        }
      }, delay)
    )

    return () => {
      cancelAnimationFrame(rafId)
      timers.forEach(clearTimeout)
    }
  }, [])

  return (
    <div className="buddy-story-screen" onClick={onContinue}>
      <div className="buddy-wrapper">
        <svg width="140" height="152" viewBox="0 0 200 218" xmlns="http://www.w3.org/2000/svg">

          <g ref={starRef} transform="translate(70, 18)">
            <polygon
              points="0,-8 2.2,-2.8 8,-2.8 3.5,1.2 5.5,7.5 0,3.8 -5.5,7.5 -3.5,1.2 -8,-2.8 -2.2,-2.8"
              fill="#f5c97a" stroke="#d4a040" strokeWidth="0.7" strokeLinejoin="round"
            />
          </g>

          <path d="M 26 86 C 18 30, 70 6, 98 6 C 128 6, 176 30, 174 86
                   L 176 176 C 176 198, 162 210, 144 208
                   C 124 213, 96 213, 70 210
                   C 48 213, 28 203, 26 180
                   C 24 166, 25 126, 26 86 Z"
                fill="#FFF8EE" stroke="#3d3025" strokeWidth="2.5" strokeLinejoin="round"/>

          <path d="M 76 210 Q 84 217, 92 211"
                fill="none" stroke="#3d3025" strokeWidth="1.4" strokeLinecap="round"/>

          <path d="M 34 126 C 13 130, 10 154, 28 161 C 39 165, 52 156, 45 139 Z"
                fill="#FFF8EE" stroke="#3d3025" strokeWidth="2.5"/>

          <path d="M 166 120 C 188 124, 192 146, 174 153 C 163 157, 150 148, 155 132 Z"
                fill="#FFF8EE" stroke="#3d3025" strokeWidth="2.5"/>

          <ellipse className="eye eye-left"  cx="78"  cy="88" rx="9" ry="11" fill="#3d3025"/>
          <ellipse className="eye eye-right" cx="122" cy="88" rx="9" ry="11" fill="#3d3025"/>

          <path d="M 84 117 Q 99 130, 114 118"
                stroke="#3d3025" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
        </svg>
      </div>

      <div className="buddy-shadow" style={{ width: 60, height: 7 }} />

      <div className="story">
        {LINES.map(line => (
          <span
            key={line.id}
            className={[
              'line',
              line.pause    ? 'pause'    : '',
              line.question ? 'question' : '',
              visible.includes(line.id) ? 'visible' : '',
            ].join(' ').trim()}
          >
            {line.text}
          </span>
        ))}
      </div>

      <p className={`buddy-hint ${showHint ? 'hint-visible' : ''}`}>
        tap to begin
      </p>
    </div>
  )
}