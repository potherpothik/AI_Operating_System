import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { Shell } from './components/Shell'
import { Login } from './pages/Login'
import { Chat } from './pages/Chat'
import { Approvals } from './pages/Approvals'
import { Ops } from './pages/Ops'

export default function App() {
  const { token } = useAuth()

  if (!token) return <Login />

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/:conversationId" element={<Chat />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/ops" element={<Ops />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  )
}
