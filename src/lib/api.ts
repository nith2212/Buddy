// Thin typed client for the Buddy backend. One place for base URL, auth header,
// timeout and error shape so screens only deal with data.

import { API_BASE_URL } from '@/constants/api';
import type { Reason } from '@/lib/reasons';

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
export type BuddyReply = {
  reply: string;
  state: string | null;
  intervention: string | null;
  ask_reason?: boolean; // Buddy asked what's in the way: show the reason chips under its reply
};

// GET /echo/week (backend brain/echo.py "The user's Echo page"): kind, earned things only.
export type EchoWeekSummary = {
  days: { date: string; active: boolean }[];
  wins: { tasks_finished: number; steps_done: number; started_when_hard: number };
  line: string;
};

export type EchoWeek = EchoWeekSummary & {
  week_start: string;
  first_week: boolean; // no weekly Echo saved yet: the first one comes Monday
  total_days: number;
  helped: { cause: string; move: string; times: number; text: string }[];
  last_week: EchoWeekSummary | null; // saved by the Sunday 23:00 cron; null until the first one
};

// POST /me/onboarding: what the person said about themselves. Every answer is optional; "you said", never a cause.
export type OnboardingAnswers = {
  days?: 'school' | 'work' | 'own_projects' | 'mix';
  click_time?: 'morning' | 'afternoon' | 'evening' | 'late_night' | 'changes';
  gets_in_way?: ('unclear' | 'too_much' | 'afraid' | 'bored' | 'tired' | 'not_sure')[];
};

export class ApiError extends Error {
  constructor(public status: number) {
    super(`Request failed with status ${status}`);
  }
}

// Don't hang past a minute on a bad connection.
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
    // due_date: null clears it; leave a field out to keep it as it is.
    updateTask: (id: number, patch: { status?: 'open' | 'done'; title?: string; due_date?: string | null }) =>
      request<Task>(token, `/tasks/${id}`, 'PATCH', patch),
    // For good: the server also deletes its steps, chat, check-ins and what Buddy learned from it.
    deleteTask: (id: number) => request<void>(token, `/tasks/${id}`, 'DELETE'),
    createSubtask: (taskId: number, title: string) =>
      request<Subtask>(token, `/tasks/${taskId}/subtasks`, 'POST', { title }),
    updateSubtask: (taskId: number, subtaskId: number, patch: { done?: boolean }) =>
      request<Subtask>(token, `/tasks/${taskId}/subtasks/${subtaskId}`, 'PATCH', patch),
    chatHistory: (taskId: number) => request<ChatTurn[]>(token, `/chat/history?task_id=${taskId}`),
    // A typed message, a tapped reason, or both (the backend needs at least one).
    chat: (taskId: number, input: { message?: string; reason?: Reason }) =>
      request<BuddyReply>(token, '/chat', 'POST', { task_id: taskId, ...input }),
    initiate: (taskId: number) => request<BuddyReply>(token, '/initiate', 'POST', { task_id: taskId }),
    echoWeek: () => request<EchoWeek>(token, '/echo/week'),
    deleteMe: () => request<void>(token, '/me', 'DELETE'),
    saveOnboarding: (answers: OnboardingAnswers) =>
      request<OnboardingAnswers>(token, '/me/onboarding', 'POST', answers),
  };
}
