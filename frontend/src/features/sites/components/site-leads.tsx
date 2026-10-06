'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { api } from '@/lib/api/client';
import { commandApi, type ProjectSummary, type WorkPerson } from '@/features/workspace/api';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';

export function SiteLeads() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [people, setPeople] = useState<WorkPerson[]>([]);
  const [admin, setAdmin] = useState(false);
  const [busy, setBusy] = useState('');
  useEffect(() => { void Promise.all([commandApi.projects(), commandApi.people(), api<{ role: string }>('/auth/me')])
    .then(([rows, users, me]) => { setProjects(rows.filter((row) => row.kind === 'site')); setPeople(users); setAdmin(me.role === 'admin'); })
    .catch(() => toast.error('مسئولان سایت‌ها دریافت نشدند')); }, []);
  async function assign(siteId: string, userId: number) {
    setBusy(siteId);
    try { await commandApi.assignProjectMember(siteId, userId, 'lead');
      setProjects((await commandApi.projects()).filter((row) => row.kind === 'site'));
      toast.success('مسئول اصلی سایت ثبت شد'); }
    catch (cause) { toast.error(cause instanceof Error ? cause.message : 'ثبت مسئول سایت انجام نشد'); }
    finally { setBusy(''); }
  }
  if (!projects.length) return null;
  return <section className='rounded-xl border bg-card p-4' dir='rtl'>
    <h2 className='mb-3 text-sm font-bold'>مسئول اصلی سایت‌ها</h2>
    <div className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>{projects.map((project) => <div key={project.site_id} className='flex items-center justify-between gap-2 rounded-lg border p-2 text-xs'>
      <span className='min-w-0 truncate font-medium'>{project.name}</span>
      {admin ? <NativeSelect aria-label={`مسئول اصلی ${project.name}`} value={project.lead_id?.toString() || ''}
        disabled={busy === project.site_id} onChange={(event) => { if (event.target.value) void assign(project.site_id, Number(event.target.value)); }} className='w-36'>
        <NativeSelectOption value=''>انتخاب مسئول</NativeSelectOption>{people.filter((person) => person.active && person.role !== 'call_center').map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}
      </NativeSelect> : <span className='text-muted-foreground'>{project.lead_name || 'تعیین نشده'}</span>}
    </div>)}</div>
  </section>;
}
