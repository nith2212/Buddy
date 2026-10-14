/**
 * App.jsx
 * -------
 * Top-level state and phase routing.
 *
 * Phase flow: intro → story → onboarding → create-task → app
 *
 * V2 changes:
 * - Added 'create-task' phase between onboarding and app
 * - activeTask lifted to App state — contains {id, title, deadline, status}
 * - task_id no longer hardcoded anywhere — flows from activeTask.id
 */

import { useState } from 'react'
import BuddyIntro from './components/BuddyIntro'
import BuddyStory from './components/BuddyStory'
import OnboardingForm from './components/OnboardingForm'
import TaskCreate from './components/TaskCreate'
import TaskView from './components/TaskView'
import ChatScreen from './components/ChatScreen'
import AgentBrainScreen from './components/AgentBrainScreen'
import NavBar from './components/NavBar'

export default function App() {
  const [phase, setPhase]         = useState('intro')  // intro | story | onboarding | create-task | app
  const [screen, setScreen]       = useState('task')
  const [messages, setMessages]   = useState([])
  const [reasoning, setReasoning] = useState(null)
  const [initiated, setInitiated] = useState(false)
  const [agentMessage, setAgentMessage] = useState(null)

  // activeTask replaces every hardcoded task_id: 1
  // Set once in create-task phase, read everywhere else
  const [activeTask, setActiveTask] = useState(null)

  function resetChat() {
    setMessages([])
    setReasoning(null)
    setInitiated(false)
  }

  function handleTaskCreated(task) {
    // task = {id, title, deadline, status} from POST /task response
    setActiveTask(task)
    setPhase('app')
  }

  // ── Phase gates ────────────────────────────────────────────────────────────

  if (phase === 'intro') {
    return <BuddyIntro onContinue={() => setPhase('story')} />
  }

  if (phase === 'story') {
    return <BuddyStory onContinue={() => setPhase('onboarding')} />
  }

  if (phase === 'onboarding') {
    return <OnboardingForm onComplete={() => setPhase('create-task')} />
  }

  if (phase === 'create-task') {
    return <TaskCreate onComplete={handleTaskCreated} />
  }

  // ── Main app ───────────────────────────────────────────────────────────────

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <NavBar screen={screen} setScreen={setScreen} />
      <main style={{
        flex:      1,
        padding:   '24px 16px',
        maxWidth:  760,
        margin:    '0 auto',
        width:     '100%',
      }}>

        {screen === 'task' && (
          <TaskView
            activeTask={activeTask}
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
            activeTask={activeTask}
            messages={messages}     setMessages={setMessages}
            reasoning={reasoning}   setReasoning={setReasoning}
            initiated={initiated}   setInitiated={setInitiated}
          />
        )}

        {screen === 'brain' && (
          <AgentBrainScreen reasoning={reasoning} />
        )}

      </main>
    </div>
  )
}