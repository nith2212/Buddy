// Thin typed client for the Buddy backend. One place for base URL, auth header,
// timeout and error shape so screens only deal with data.

import { API_BASE_URL } from '@/constants/api';

export type Subtask = { id: number; title: string; done: boolean; position: number; created_at: string };

export type Task = {
  id: number;
  title: string | null;
  due_date: string | null;
  status: 'open' | 'done';
  task_state: string | null;
  created_at: string;
  subtasks: Subtask[];
};

export type ChatTurn = { role: 'user' | 'assistant'; content: string };
export type BuddyReply = { reply: string; state: string | null; intervention: string | null };

export class ApiError extends Error {
  constructor(public status: number) {
    super(`Request failed with status ${status}`);
  }
}

// Render's free tier can take ~50s to wake from sleep; don't hang past a minute.
const TIMEOUT_MS = 60_000;

async function request<T>(token: string, path: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new ApiError(res.status);
    return (res.status === 204 ? undefined : await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export function api(token: string) {
  return {
    listTasks: () => request<Task[]>(token, '/tasks'),
    getTask: (id: number) => request<Task>(token, `/tasks/${id}`),
    createTask: (title: string, due_date: string | null) =>
      request<Task>(token, '/tasks', 'POST', { title, due_date }),
    updateTask: (id: number, patch: { status?: 'open' | 'done' }) =>
      request<Task>(token, `/tasks/${id}`, 'PATCH', patch),
    createSubtask: (taskId: number, title: string) =>
      request<Subtask>(token, `/tasks/${taskId}/subtasks`, 'POST', { title }),
    updateSubtask: (taskId: number, subtaskId: number, patch: { done?: boolean }) =>
      request<Subtask>(token, `/tasks/${taskId}/subtasks/${subtaskId}`, 'PATCH', patch),
    chatHistory: (taskId: number) => request<ChatTurn[]>(token, `/chat/history?task_id=${taskId}`),
    chat: (taskId: number, message: string) =>
      request<BuddyReply>(token, '/chat', 'POST', { task_id: taskId, message }),
    initiate: (taskId: number) => request<BuddyReply>(token, '/initiate', 'POST', { task_id: taskId }),
  };
}
