'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ErrorState, LoadingState } from '@/components/seo-brain/states';
import { ApiError, endpoints } from '@/lib/api/client';
import type { WorkEvent, WorkItem, WorkList, WorkStatus } from '@/features/reports/types';

const fa = new Intl.NumberFormat('fa-IR');
const labels: Record<WorkStatus, string> = {
  new: 'جدید', triaged: 'بررسی اولیه', approved: 'تأییدشده', assigned: 'واگذارشده',
  in_progress: 'در حال اجرا', review: 'بازبینی', published: 'منتشرشده',
  measurement_pending: 'در انتظار سنجش', verified: 'سنجیده‌شده', blocked: 'مسدود',
  rejected: 'ردشده', deferred: 'تعویق'
};
const active = new Set<WorkStatus>(['approved', 'assigned', 'in_progress', 'review', 'published', 'measurement_pending', 'verified', 'blocked']);
type Form = { title: string; description: string; url: string; status: WorkStatus; owner_id: string;
  due_at: string; blocked_reason: string; verification_note: string; note: string };
const empty: Form = { title: '', description: '', url: '', status: 'new', owner_id: '', due_at: '',
  blocked_reason: '', verification_note: '', note: '' };

export function WorkPanel({ siteId, refreshKey }: { siteId: string; refreshKey: number }) {
  const [data, setData] = useState<WorkList | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [users, setUsers] = useState<{ id: number; full_name: string; active: boolean }[]>([]);
  const [editing, setEditing] = useState<WorkItem | 'new' | null>(null);
  const [form, setForm] = useState<Form>(empty);
  const [saving, setSaving] = useState(false);
  const [events, setEvents] = useState<WorkEvent[] | null>(null);
  const [eventsFor, setEventsFor] = useState<WorkItem | null>(null);

  useEffect(() => { setOffset(0); }, [siteId, q, statusFilter]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([endpoints.siteWork(siteId, { q, status: statusFilter, limit: 50, offset }), endpoints.panelUsers()])
      .then(([work, people]) => { if (!cancelled) { setData(work); setUsers(people); setError(null); } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof ApiError ? cause : new ApiError(0, 'unknown', String(cause), null, '')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [siteId, refreshKey, retry, q, statusFilter, offset]);

  const edit = (item: WorkItem | 'new') => {
    setEditing(item);
    setForm(item === 'new' ? empty : {
      title: item.title, description: item.description, url: item.url || '', status: item.status,
      owner_id: item.owner_id?.toString() || '', due_at: item.due_at?.slice(0, 16) || '',
      blocked_reason: item.blocked_reason || '', verification_note: item.verification_note || '', note: ''
    });
  };
  const save = async () => {
    if (!editing) return;
    if (active.has(form.status) && (!form.owner_id || !form.due_at)) {
      toast.error('برای کار فعال، مسئول و موعد را مشخص کنید'); return;
    }
    if (form.status === 'blocked' && !form.blocked_reason.trim()) { toast.error('دلیل مانع را بنویسید'); return; }
    if (form.status === 'verified' && !form.verification_note.trim()) { toast.error('نتیجهٔ سنجش را بنویسید'); return; }
    setSaving(true);
    const body = { title: form.title.trim(), description: form.description, url: form.url || null,
      status: form.status, owner_id: form.owner_id ? Number(form.owner_id) : null,
      due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
      blocked_reason: form.blocked_reason || null, verification_note: form.verification_note || null,
      note: form.note || null };
    try {
      if (editing === 'new') await endpoints.createSiteWork(siteId, body);
      else await endpoints.updateSiteWork(siteId, editing.id, body);
      setEditing(null); setRetry((value) => value + 1); toast.success('کار ثبت شد');
    } catch (cause) { toast.error(cause instanceof ApiError ? cause.message : String(cause)); }
    finally { setSaving(false); }
  };
  const showEvents = async (item: WorkItem) => {
    setEventsFor(item); setEvents(null);
    try { setEvents(await endpoints.siteWorkEvents(siteId, item.id)); }
    catch (cause) { toast.error(cause instanceof ApiError ? cause.message : String(cause)); }
  };

  return <div className='space-y-4'>
    {error && <ErrorState error={error} onRetry={() => setRetry((value) => value + 1)} />}
    {loading && !data && <LoadingState label='در حال خواندن کارهای سایت…' rows={5} />}
    {data && <>
      <div className='grid grid-cols-2 gap-2 md:grid-cols-4'>
        {([['کل کارها', data.summary.total], ['بی‌مسئول', data.summary.unassigned],
          ['موعدگذشته', data.summary.overdue], ['مسدود', data.summary.blocked]] as const).map(([label, value]) =>
          <Card key={label}><CardContent className='pt-4'><div className='text-muted-foreground text-xs'>{label}</div>
            <div className='mt-1 text-2xl font-bold'>{fa.format(value)}</div></CardContent></Card>)}
      </div>
      <Card><CardHeader className='flex-row items-center justify-between'><div><CardTitle className='text-base'>میز کار SEO</CardTitle>
        <p className='text-muted-foreground mt-1 text-xs'>از کشف مسئله تا اجرا و سنجش نتیجه؛ هر تغییر در تاریخچه می‌ماند.</p></div>
        <Button onClick={() => edit('new')}>کار جدید</Button></CardHeader>
        <CardContent className='space-y-3'>
          <div className='flex flex-wrap gap-2'><Input value={q} onChange={(event) => setQ(event.target.value)}
            placeholder='جست‌وجوی کار یا URL' aria-label='جست‌وجوی کار' className='min-w-48 flex-1' />
            <NativeSelect value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label='فیلتر وضعیت' className='w-48'>
              <NativeSelectOption value=''>همهٔ وضعیت‌ها</NativeSelectOption>
              {(Object.keys(labels) as WorkStatus[]).map((key) => <NativeSelectOption key={key} value={key}>{labels[key]}</NativeSelectOption>)}
            </NativeSelect></div>
          {data.items.length ? <div className='overflow-x-auto rounded-md border'><Table><TableHeader><TableRow>
          <TableHead>کار</TableHead><TableHead>وضعیت</TableHead><TableHead>مسئول</TableHead><TableHead>موعد</TableHead><TableHead>اقدام</TableHead>
        </TableRow></TableHeader><TableBody>{data.items.map((item) => <TableRow key={item.id}>
          <TableCell><div className='font-medium'>{item.title}</div>{item.url && <div className='text-muted-foreground max-w-64 truncate text-xs' dir='ltr'>{item.url}</div>}</TableCell>
          <TableCell><Badge variant='outline'>{labels[item.status]}</Badge></TableCell>
          <TableCell>{item.owner_name || users.find((user) => user.id === item.owner_id)?.full_name || '—'}</TableCell>
          <TableCell className='text-xs' dir='ltr'>{item.due_at?.slice(0, 10) || '—'}</TableCell>
          <TableCell><div className='flex gap-1'><Button size='sm' variant='outline' onClick={() => edit(item)}>ویرایش</Button>
            <Button size='sm' variant='ghost' onClick={() => showEvents(item)}>تاریخچه</Button></div></TableCell>
        </TableRow>)}</TableBody></Table></div> : <p className='text-muted-foreground py-8 text-center text-sm'>کاری مطابق فیلتر پیدا نشد.</p>}
          <div className='flex items-center justify-between text-xs'><span>{fa.format(data.total)} کار مطابق فیلتر</span>
            <div className='flex gap-2'><Button size='sm' variant='outline' disabled={!offset || loading} onClick={() => setOffset(Math.max(0, offset - 50))}>قبلی</Button>
              <Button size='sm' variant='outline' disabled={offset + 50 >= data.total || loading} onClick={() => setOffset(offset + 50)}>بعدی</Button></div></div>
        </CardContent>
      </Card>
    </>}
    <Dialog open={editing !== null} onOpenChange={(open) => { if (!open) setEditing(null); }}><DialogContent dir='rtl' className='max-h-[90vh] overflow-y-auto'>
      <DialogHeader><DialogTitle>{editing === 'new' ? 'کار جدید' : 'ویرایش کار'}</DialogTitle><DialogDescription>مسئول، موعد و نتیجهٔ بازبینی را ثبت کنید.</DialogDescription></DialogHeader>
      <div className='space-y-3'>
        <div><Label htmlFor='work-title'>عنوان</Label><Input id='work-title' value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></div>
        <div><Label htmlFor='work-description'>شرح</Label><Input id='work-description' value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></div>
        <div><Label htmlFor='work-url'>URL مرتبط</Label><Input id='work-url' dir='ltr' value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} /></div>
        <div className='grid grid-cols-2 gap-2'><div><Label htmlFor='work-status'>وضعیت</Label><NativeSelect id='work-status' value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as WorkStatus })}>
          {(Object.keys(labels) as WorkStatus[]).map((key) => <NativeSelectOption key={key} value={key}>{labels[key]}</NativeSelectOption>)}
        </NativeSelect></div><div><Label htmlFor='work-owner'>مسئول</Label><NativeSelect id='work-owner' value={form.owner_id} onChange={(event) => setForm({ ...form, owner_id: event.target.value })}>
          <NativeSelectOption value=''>انتخاب نشده</NativeSelectOption>{users.filter((user) => user.active).map((user) => <NativeSelectOption key={user.id} value={user.id.toString()}>{user.full_name}</NativeSelectOption>)}
        </NativeSelect></div></div>
        <div><Label htmlFor='work-due'>موعد</Label><Input id='work-due' type='datetime-local' value={form.due_at} onChange={(event) => setForm({ ...form, due_at: event.target.value })} /></div>
        {form.status === 'blocked' && <div><Label htmlFor='work-blocked'>دلیل مانع</Label><Input id='work-blocked' value={form.blocked_reason} onChange={(event) => setForm({ ...form, blocked_reason: event.target.value })} /></div>}
        {form.status === 'verified' && <div><Label htmlFor='work-verified'>نتیجهٔ سنجش</Label><Input id='work-verified' value={form.verification_note} onChange={(event) => setForm({ ...form, verification_note: event.target.value })} /></div>}
        <div><Label htmlFor='work-note'>یادداشت تغییر</Label><Input id='work-note' value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></div>
        <Button onClick={save} disabled={saving || form.title.trim().length < 3}>{saving ? 'در حال ذخیره…' : 'ذخیره'}</Button>
      </div>
    </DialogContent></Dialog>
    <Dialog open={eventsFor !== null} onOpenChange={(open) => { if (!open) setEventsFor(null); }}><DialogContent dir='rtl' className='max-h-[85vh] overflow-y-auto'>
      <DialogHeader><DialogTitle>تاریخچهٔ {eventsFor?.title}</DialogTitle><DialogDescription>ثبت رویدادهای این کار</DialogDescription></DialogHeader>
      <ol className='space-y-2'>{events?.map((event) => <li key={event.id} className='rounded-md border p-2 text-sm'>
        <div className='flex justify-between'><span>{event.event_type === 'created' ? 'ایجاد' : 'ویرایش'}</span><span dir='ltr' className='text-muted-foreground text-xs'>{event.created_at}</span></div>
        {event.note && <p className='mt-1 text-muted-foreground'>{event.note}</p>}
      </li>)}</ol>
    </DialogContent></Dialog>
  </div>;
}
