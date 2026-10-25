import { createContext, useContext } from 'react';

// The root layout runs the auth bootstrap once and provides the ready token here,
// so screens never trigger a second bootstrap (which could register a second user
// on first launch).
const SessionContext = createContext<string | null>(null);

export const SessionProvider = SessionContext.Provider;

export function useToken(): string {
  const token = useContext(SessionContext);
  if (!token) throw new Error('useToken must be used inside a SessionProvider');
  return token;
}
