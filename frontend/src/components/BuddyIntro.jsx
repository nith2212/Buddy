import { useEffect, useRef } from 'react'
import './BuddyIntro.css'

export default function BuddyIntro({ onContinue }) {
  const starRef = useRef(null)

  useEffect(() => {
    const cx = 100, cy = 109
    const orbitR = 72
    let angle = 42
    let targetAngle = 42
    let lastJitter = 0
    let rafId

    function animate(ts) {
      if (ts - lastJitter > 2200 + Math.random() * 1800) {
        targetAngle += (Math.random() - 0.5) * 140
        lastJitter = ts
      }
      const diff = targetAngle - angle
      angle += diff * 0.012
      const rad = angle * Math.PI / 180
      const sx = cx + orbitR * Math.cos(rad)
      const sy = cy + orbitR * Math.sin(rad) * 0.45 - 10
      if (starRef.current) {
        starRef.current.setAttribute('transform', `translate(${sx}, ${sy})`)
      }
      rafId = requestAnimationFrame(animate)
    }

    rafId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafId)
  }, [])

  return (
    <div className="buddy-intro-screen" onClick={onContinue}>
      <div className="buddy-wrapper">
        <svg width="200" height="218" viewBox="0 0 200 218" xmlns="http://www.w3.org/2000/svg">

          <g ref={starRef} transform="translate(148, 18)">
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

      <div className="buddy-shadow" />
      <p className="buddy-label">Hi.<br />I'm Buddy.</p>
      <p className="buddy-hint">tap to continue</p>
    </div>
  )
}