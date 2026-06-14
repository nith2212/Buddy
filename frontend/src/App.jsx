/**
 * App.jsx
 * -------
 * Root component. Owns all shared state and renders the nav + active screen.
 *
 * State lifted here (not in child screens) so it persists across tab navigation:
 *   screen       — active tab: 'task' | 'chat' | 'brain'
 *   messages     — conversation turn array for ChatScreen
 *   reasoning    — latest agent reasoning snapshot for AgentBrainPanel
 *   initiated    — whether ChatScreen has already called /initiate this session
 *   agentMessage — latest Buddy message shown in the TaskView notification bubble
 *
 * resetChat() clears messages + reasoning + initiated so ChatScreen re-initiates
 * from a clean DB state (used after python seed.py).
 */

import { useState } from 'react'
import TaskView from './components/TaskView'
import ChatScreen from './components/ChatScreen'
import AgentBrainScreen from './components/AgentBrainScreen'
import NavBar from './components/NavBar'

export default function App() {
  const [screen, setScreen]           = useState('task')
  const [messages, setMessages]       = useState([])
  const [reasoning, setReasoning]     = useState(null)
  const [initiated, setInitiated]     = useState(false)
  const [agentMessage, setAgentMessage] = useState(
    "You've pushed this back twice now. I know you work better in the evenings — it's that time. What's getting in the way?"
  )

  function resetChat() {
    setMessages([])
    setReasoning(null)
    setInitiated(false)
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <NavBar screen={screen} setScreen={setScreen} />
      <main style={{ flex: 1, padding: '24px 16px', maxWidth: 760, margin: '0 auto', width: '100%' }}>
        {screen === 'task' && (
          <TaskView
            setScreen={setScreen}
            setMessages={setMessages}
            setReasoning={setReasoning}
            setInitiated={setInitiated}
            resetChat={resetChat}
            agentMessage={agentMessage}
            setAgentMessage={setAgentMessage}
          />
        )}
        {screen === 'chat' && (
          <ChatScreen
            messages={messages}     setMessages={setMessages}
            reasoning={reasoning}   setReasoning={setReasoning}
            initiated={initiated}   setInitiated={setInitiated}
          />
        )}
        {screen === 'brain' && <AgentBrainScreen reasoning={reasoning} />}
      </main>
    </div>
  )
}
