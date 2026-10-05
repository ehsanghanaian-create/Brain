import { api } from '@/lib/api/client';
import type { WorkItem, WorkStatus } from '@/features/reports/types';

export type WorkPriority = 'critical' | 'high' | 'normal' | 'low';
export type CommandWorkItem = WorkItem & {
  site_name: string;
  team_id: number | null;
  team_name: string | null;
  team_color: string | null;
  priority: WorkPriority;
  estimated_hours: number | null;
};
export type WorkTeam = { id: number; name: string; color: string; description: string; active: boolean;
  members: number; open_work: number };
export type WorkPerson = { id: number; full_name: string; active: boolean; team_id: number | null; role: string };
export type CommandOverview = {
  summary: { total: number; open: number; overdue: number; unassigned: number; blocked: number; due_week: number; hours_open: number };
  items: CommandWorkItem[];
  limit: number;
  offset: number;
  by_status: { key: WorkStatus; count: number }[];
  by_site: { key: string; name: string; total: number; open: number; overdue: number; unassigned: number }[];
  by_owner: { key: number | null; name: string; total: number; open: number; overdue: number; hours_open: number }[];
  by_team: { key: number | null; name: string; total: number; open: number; overdue: number }[];
  due_days: { day: string; count: number }[];
  recent: { id: number; site_id: string; work_item_id: number; event_type: string; note: string | null; actor_username: string | null;
    created_at: string; title: string; site_name: string }[];
};
export type CommandFilters = { site_id?: string; owner_id?: number; team_id?: number;
  status?: string; priority?: string; q?: string; limit?: number; offset?: number };
export const commandApi = {
  me: () => api<{ id: number; role: 'admin' | 'analyst' | 'call_center' }>('/auth/me'),
  overview: (filters: CommandFilters = {}) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') query.set(key, String(value)); });
    return api<CommandOverview>(`/work/overview?${query.toString()}`);
  },
  teams: () => api<WorkTeam[]>('/work/teams'),
  people: () => api<WorkPerson[]>('/call-center/operators'),
  createTeam: (body: { name: string; color: string; description: string }) =>
    api<WorkTeam>('/work/teams', { method: 'POST', json: body }),
  updateTeam: (id: number, body: Partial<Pick<WorkTeam, 'name' | 'color' | 'description' | 'active'>>) =>
    api<WorkTeam>(`/work/teams/${id}`, { method: 'PATCH', json: body }),
  assignMember: (userId: number, teamId: number | null) =>
    api(`/call-center/users/${userId}`, { method: 'PATCH', json: { team_id: teamId } }),
  createWork: (siteId: string, body: Record<string, unknown>) =>
    api<CommandWorkItem>(`/sites/${encodeURIComponent(siteId)}/work`, { method: 'POST', json: body }),
  updateWork: (item: CommandWorkItem, body: Record<string, unknown>) =>
    api<CommandWorkItem>(`/sites/${encodeURIComponent(item.site_id)}/work/${item.id}`, { method: 'PATCH', json: body }),
  events: (item: CommandWorkItem) =>
    api<{ id: number; event_type: string; before_json: string | null; after_json: string; note: string | null; actor_username: string | null; created_at: string }[]>(
      `/sites/${encodeURIComponent(item.site_id)}/work/${item.id}/events`)
};
