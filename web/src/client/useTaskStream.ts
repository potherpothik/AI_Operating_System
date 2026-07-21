import { useEffect, useState } from 'react'
import { getToken, type Task } from './api'

// Real SSE against Gateway's existing GET /api/v1/tasks/{id}/stream
// (Phase 2) — EventSource can't send an Authorization header, so the
// token rides as a query param on this one connection only, matching
// the same dev-token posture the rest of this UI already uses.
export function useTaskStream(taskId: string | null): Task | null {
  const [task, setTask] = useState<Task | null>(null)

  useEffect(() => {
    if (!taskId) return
    setTask(null)
    const token = getToken()
    const source = new EventSource(`/api/v1/tasks/${taskId}/stream?token=${encodeURIComponent(token ?? '')}`)
    source.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (!data.error) setTask(data as Task)
    }
    return () => source.close()
  }, [taskId])

  return task
}
