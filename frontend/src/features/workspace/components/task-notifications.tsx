'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { IconBell } from '@tabler/icons-react';
import { api } from '@/lib/api/client';
import { Button } from '@/components/ui/button';

type Notification = { id: number; work_item_id: number | null; site_id: string | null;
  title: string; body: string; created_at: string; read_at: string | null };

export function TaskNotifications() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const refresh = useCallback(async () => {
    try { const result = await api<{ items: Notification[]; unread: number }>('/auth/notifications'); setItems(result.items); setUnread(result.unread); }
    catch { /* The header must not interrupt the active page when a session expires. */ }
  }, []);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 20000); return () => clearInterval(timer); }, [refresh]);
  async function read(item: Notification) {
    if (!item.read_at) {
      try { await api(`/auth/notifications/${item.id}/read`, { method: 'POST' });
        setItems((current) => current.map((row) => row.id === item.id ? { ...row, read_at: new Date().toISOString() } : row));
        setUnread((count) => Math.max(0, count - 1)); }
      catch { return; }
    }
    setOpen(false);
  }
  return <div className='relative' dir='rtl'>
    <Button size='icon-sm' variant='ghost' aria-label={`اعلان‌ها${unread ? `، ${unread} خوانده‌نشده` : ''}`} onClick={() => setOpen((value) => !value)}>
      <IconBell className='size-4' />{unread > 0 && <span className='absolute -top-0.5 -left-0.5 flex size-4 items-center justify-center rounded-full bg-rose-500 text-[10px] text-white'>{unread > 9 ? '9+' : unread}</span>}
    </Button>
    {open && <div className='absolute top-10 left-0 z-50 max-h-96 w-80 overflow-y-auto rounded-xl border bg-card p-2 shadow-xl'>
      <strong className='block px-2 py-2 text-sm'>اعلان‌های واگذاری</strong>
      {items.map((item) => <Link key={item.id} href='/dashboard/work' onClick={() => void read(item)} className={`block rounded-lg p-2 text-right hover:bg-muted ${!item.read_at ? 'bg-primary/5' : ''}`}>
        <span className='block truncate text-sm font-medium'>{item.title}</span>
        <span className='text-muted-foreground block text-xs'>{item.body}</span>
        <span className='text-muted-foreground block text-[11px]'>{new Date(item.created_at).toLocaleString('fa-IR')}</span>
      </Link>)}
      {!items.length && <p className='text-muted-foreground p-4 text-center text-xs'>اعلان تازه‌ای نیست.</p>}
    </div>}
  </div>;
}
