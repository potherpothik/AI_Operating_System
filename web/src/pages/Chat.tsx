import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  createConversation,
  createTask,
  getTimeline,
  listConversations,
  type Conversation,
  type Task,
  type TaskEvent,
} from '../client/api'
import { useTaskStream } from '../client/useTaskStream'

export function Chat() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [turns, setTurns] = useState<{ task: Task; events: TaskEvent[] }[]>([])
  const [composer, setComposer] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [latestTaskId, setLatestTaskId] = useState<string | null>(null)
  const liveTask = useTaskStream(latestTaskId)

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  }, [])

  useEffect(() => {
    if (!conversationId) {
      setTurns([])
      return
    }
    getTimeline(conversationId)
      .then((res) => setTurns(res.turns))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
  }, [conversationId])

  // Real orchestration outcomes, not token-by-token model output (Phase
  // 24 doc §5.1's own honesty note) — this replaces the matching turn's
  // task the instant its status changes.
  useEffect(() => {
    if (!liveTask) return
    setTurns((prev) => prev.map((t) => (t.task.id === liveTask.id ? { ...t, task: liveTask } : t)))
  }, [liveTask])

  async function handleNewConversation() {
    const conv = await createConversation('New conversation')
    setConversations((prev) => [conv, ...prev])
    navigate(`/chat/${conv.id}`)
  }

  async function handleSend() {
    if (!composer.trim()) return
    setSending(true)
    setError(null)
    try {
      let targetConversationId = conversationId
      if (!targetConversationId) {
        const conv = await createConversation(composer.slice(0, 60))
        setConversations((prev) => [conv, ...prev])
        targetConversationId = conv.id
        navigate(`/chat/${conv.id}`)
      }
      const task = await createTask({
        title: composer.slice(0, 120),
        description: composer,
        conversation_id: targetConversationId,
      })
      setTurns((prev) => [...prev, { task, events: [] }])
      setLatestTaskId(task.id)
      setComposer('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-layout">
      <aside className="chat-sidebar">
        <button className="new-conversation" onClick={handleNewConversation}>
          + New conversation
        </button>
        <ul>
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                className={c.id === conversationId ? 'active' : ''}
                onClick={() => navigate(`/chat/${c.id}`)}
              >
                {c.title}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="chat-main">
        {error && <div className="error-banner">{error}</div>}
        <div className="chat-messages">
          {turns.length === 0 && <div className="empty-state">No turns yet — send a message to create a task.</div>}
          {turns.map(({ task, events }) => (
            <div key={task.id} className="chat-turn">
              <div className="turn-user">{task.description || task.title}</div>
              <div className="turn-status">
                <span className={`status-chip status-${task.status}`}>{task.status}</span>
                {events.length > 0 && (
                  <span className="turn-events">{events.length} event{events.length === 1 ? '' : 's'}</span>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="composer">
          <textarea
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            placeholder="Describe a task for an agent to work on..."
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
          />
          <button onClick={handleSend} disabled={sending || !composer.trim()}>
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </section>
    </div>
  )
}
