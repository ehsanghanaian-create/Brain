import { api } from '@/lib/api/client';

export type SupportStatus = 'open' | 'waiting' | 'closed';
export type SupportTicket = {
  id: number;
  reference: string;
  owner: string;
  subject: string;
  category: 'problem' | 'question' | 'idea';
  site_id: string | null;
  context_path: string;
  status: SupportStatus;
  created_at: string;
  updated_at: string;
  message_count?: number;
};
export type SupportDetail = SupportTicket & {
  messages: { id: number; author: string; is_staff: number; body: string; created_at: string }[];
};
export const supportApi = {
  list: (status: string, offset = 0) =>
    api<{ items: SupportTicket[]; total: number; is_staff: boolean; account: string }>(
      `/support/tickets?status=${encodeURIComponent(status)}&limit=50&offset=${offset}`
    ),
  detail: (id: number) => api<SupportDetail>(`/support/tickets/${id}`),
  create: (body: {
    subject: string;
    message: string;
    category: string;
    site_id: string | null;
    context_path: string;
  }) => api<SupportDetail>('/support/tickets', { method: 'POST', json: body }),
  reply: (id: number, message: string, as_support: boolean) =>
    api<SupportDetail>(`/support/tickets/${id}/messages`, {
      method: 'POST',
      json: { message, as_support }
    }),
  status: (id: number, status: 'open' | 'closed') =>
    api<SupportDetail>(`/support/tickets/${id}`, { method: 'PATCH', json: { status } })
};
