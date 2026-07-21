import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Shell() {
  const { logout } = useAuth()
  return (
    <div className="shell">
      <nav className="nav-primary">
        <div className="brand">AI Operating System</div>
        <NavLink to="/chat" className={({ isActive }) => (isActive ? 'active' : '')}>
          Chat
        </NavLink>
        <NavLink to="/approvals" className={({ isActive }) => (isActive ? 'active' : '')}>
          Approvals
        </NavLink>
        <NavLink to="/ops" className={({ isActive }) => (isActive ? 'active' : '')}>
          Ops
        </NavLink>
        <button className="logout" onClick={logout}>
          Sign out
        </button>
      </nav>
      <main className="main-surface">
        <Outlet />
      </main>
    </div>
  )
}
