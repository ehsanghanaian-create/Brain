'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { IconArchive, IconBell, IconRestore } from '@tabler/icons-react';
import { toast } from 'sonner';
import { api } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { formatUserDateTime, useDatePreference } from '@/lib/date-preference';

type Audience = 'all' | 'assigned' | 'delegated' | 'discussion' | 'updates';
type Notification = { id: number; work_item_id: number | null; site_id: string | null;
  kind: string; audience: Audience; title: string; body: string; created_at: string;
  read_at: string | null; archived_at: string | null };

export function TaskNotifications() {
  const { calendar } = useDatePreference();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<'active' | 'archived'>('active');
  const [audience, setAudience] = useState<Audience>('all');
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [archived, setArchived] = useState(0);
  const refresh = useCallback(async () => {
    try {
      const result = await api<{ items: Notification[]; unread: number; archived: number }>(
        `/auth/notifications?view=${view}&audience=${audience}`);
      setItems(result.items); setUnread(result.unread); setArchived(result.archived);
    } catch { /* An expired session must not interrupt the active page. */ }
  }, [view, audience]);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 20000); return () => clearInterval(timer); }, [refresh]);

  async function read(item: Notification) {
    if (item.read_at) return;
    try { await api(`/auth/notifications/${item.id}/read`, { method: 'POST' });
      setItems((current) => current.map((row) => row.id === item.id ? { ...row, read_at: new Date().toISOString() } : row));
      setUnread((count) => Math.max(0, count - 1));
    } catch { toast.error('خواندن اعلان ثبت نشد'); }
  }
  async function move(item: Notification) {
    const action = view === 'active' ? 'archive' : 'restore';
    try {
      await api(`/auth/notifications/${item.id}/${action}`, { method: 'POST' });
      setItems((current) => current.filter((row) => row.id !== item.id));
      if (action === 'archive') {
        if (!item.read_at) setUnread((count) => Math.max(0, count - 1));
        setArchived((count) => count + 1);
      } else setArchived((count) => Math.max(0, count - 1));
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : 'تغییر اعلان انجام نشد'); }
  }

  return <div className='relative' dir='rtl'>
    <Button size='icon-sm' variant='ghost' aria-label={`اعلان‌ها${unread ? `، ${unread} خوانده‌نشده` : ''}`}
      aria-expanded={open} onClick={() => setOpen((value) => !value)}>
      <IconBell className='size-4' />{unread > 0 && <span className='absolute -top-0.5 -left-0.5 flex size-4 items-center justify-center rounded-full bg-rose-500 text-[10px] text-white'>{unread > 9 ? '9+' : unread}</span>}
    </Button>
    {open && <section aria-label='اعلان‌های کار' className='absolute top-10 left-0 z-50 w-[min(25rem,calc(100vw-1rem))] rounded-xl border bg-card p-2 shadow-xl'>
      <div className='flex items-center justify-between px-2 py-2'><strong className='text-sm'>اعلان‌ها</strong><span className='text-muted-foreground text-xs'>{unread} خوانده‌نشده</span></div>
      <div className='flex gap-1 border-b pb-2'>
        <Button size='sm' variant={view === 'active' ? 'secondary' : 'ghost'} onClick={() => setView('active')}>صندوق ورودی</Button>
        <Button size='sm' variant={view === 'archived' ? 'secondary' : 'ghost'} onClick={() => setView('archived')}>آرشیو ({archived})</Button>
      </div>
      <NativeSelect aria-label='دستهٔ اعلان‌ها' value={audience} onChange={(event) => setAudience(event.target.value as Audience)} className='my-2 w-full'>
        <NativeSelectOption value='all'>همهٔ بخش‌ها</NativeSelectOption>
        <NativeSelectOption value='assigned'>تسک‌های ارجاع‌شده به من</NativeSelectOption>
        <NativeSelectOption value='delegated'>تسک‌هایی که واگذار کرده‌ام</NativeSelectOption>
        <NativeSelectOption value='discussion'>گفت‌وگوها</NativeSelectOption>
        <NativeSelectOption value='updates'>تغییرات دیگر</NativeSelectOption>
      </NativeSelect>
      <div className='max-h-96 space-y-1 overflow-y-auto'>
        {items.map((item) => <div key={item.id} className={`flex items-start gap-1 rounded-lg p-1 hover:bg-muted ${!item.read_at ? 'bg-primary/5' : ''}`}>
          <Link href='/dashboard/work' onClick={() => { void read(item); setOpen(false); }} className='min-w-0 flex-1 rounded-md p-1.5 text-right'>
            <span className='block truncate text-sm font-medium'>{item.title}</span>
            <span className='text-muted-foreground block text-xs leading-5'>{item.body}</span>
            <span className='text-muted-foreground block text-[11px]'>{formatUserDateTime(item.created_at, calendar)}</span>
          </Link>
          <Button size='icon-sm' variant='ghost' aria-label={view === 'active' ? `بایگانی اعلان ${item.title}` : `بازگرداندن اعلان ${item.title}`}
            title={view === 'active' ? 'بایگانی' : 'بازگرداندن'} onClick={() => void move(item)}>
            {view === 'active' ? <IconArchive className='size-4' /> : <IconRestore className='size-4' />}
          </Button>
        </div>)}
        {!items.length && <p className='text-muted-foreground p-4 text-center text-xs'>اعلانی در این بخش نیست.</p>}
      </div>
    </section>}
  </div>;
}
