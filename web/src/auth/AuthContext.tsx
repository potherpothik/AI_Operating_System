import { createContext, useContext, useState, type ReactNode } from 'react'
import { getToken, setToken as storeToken, clearToken } from '../client/api'

interface AuthState {
  token: string | null
  login: (token: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken())

  const login = (t: string) => {
    storeToken(t)
    setTokenState(t)
  }
  const logout = () => {
    clearToken()
    setTokenState(null)
  }

  return <AuthContext.Provider value={{ token, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
