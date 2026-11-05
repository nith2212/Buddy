import { createContext, useContext } from 'react';

// The root layout runs the auth bootstrap once and provides the ready token here,
// so screens never trigger a second bootstrap (which could register a second user
// on first launch). `restart` forgets the identity and registers a fresh one.
type Session = { token: string; restart: () => Promise<void> };

const SessionContext = createContext<Session | null>(null);

export const SessionProvider = SessionContext.Provider;

function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useToken must be used inside a SessionProvider');
  return session;
}

export function useToken(): string {
  return useSession().token;
}

export function useRestart(): () => Promise<void> {
  return useSession().restart;
}
