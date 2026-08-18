'use client';

import { KpiCard } from '@/components/seo-brain/kpi-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type ContentBoard, type ContentItem, type ContentStatus, type Site } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { PRIORITY_FA, STATUS_COLOR, STATUS_FA, STATUS_ORDER, faNum } from '../constants';
import { ContentEditor } from './content-editor';
import { AnalyticsPanel } from './analytics-panel';

export function ContentBrainPage({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [board, setBoard] = useState<ContentBoard | null>(null);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try { setBoard(await endpoints.contentBoard(siteId)); } catch (e) { setError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); }
  }, [siteId]);
  useEffect(() => { load(); }, [load]);

  const items = board?.columns.flatMap((c) => c.items) ?? [];
  const filtered = items.filter((i) => (!q || i.title.includes(q) || (i.target_keyword ?? '').includes(q)) && (!statusFilter || i.status === statusFilter));

  async function move(item: ContentItem, to: ContentStatus) {
    if (item.status === to) return;
    try { await endpoints.transitionContent(siteId, item.id, to); toast.success(`${item.title} → ${STATUS_FA[to]}`); load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }
  async function syncGraph() {
    try { const r = await endpoints.syncContentGraph(siteId); toast.success(`گراف: ${r.nodes} گره محتوا، ${r.edges} یال`); } catch (e) { toast.error(String(e)); }
  }

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={siteId} onChange={(e) => setSiteId(e.target.value)} className='w-44'>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
        <Button onClick={() => setEditing('new')}>محتوای جدید</Button>
        <Button variant='outline' render={<Link href={`/dashboard/keywords?site=${siteId}`} />}>از فرصت‌های کلمات کلیدی</Button>
        <Button variant='ghost' onClick={syncGraph}>همگام‌سازی گراف</Button>
        <Link href={`/dashboard/calendar?site=${siteId}`} className='text-xs underline'>تقویم محتوایی</Link>
        <Link href={`/dashboard/graph?site=${siteId}`} className='text-xs underline'>گراف</Link>
      </div>
      {error && <p className='text-destructive text-sm'>{error}</p>}
      <div className='grid grid-cols-2 gap-3 md:grid-cols-4'>
        <KpiCard label='کل محتوا' value={board?.counts.total ?? null} />
        <KpiCard label='زمان‌بندی‌شده' value={board?.counts.scheduled ?? null} />
        <KpiCard label='در جریان' value={board ? board.counts.by_status.brief_ready + board.counts.by_status.writing + board.counts.by_status.review : null} hint='بریف آماده + نگارش + بازبینی' />
        <KpiCard label='منتشرشده' value={board?.counts.by_status.published ?? null} hint='انتشار خودکار غیرفعال است' />
      </div>
      <Tabs defaultValue='board'>
        <TabsList><TabsTrigger value='board'>کانبان</TabsTrigger><TabsTrigger value='list'>فهرست</TabsTrigger><TabsTrigger value='analytics'>تحلیل و یادگیری</TabsTrigger></TabsList>
        <TabsContent value='board'>
          <p className='text-muted-foreground mb-2 text-xs'>کارت‌ها را بین ستون‌ها بکشید (فقط یک مرحله جلو یا عقب؛ «بریف آماده» بریف می‌خواهد و «منتشرشده» URL). تأیید همیشه با شماست.</p>
          <div className='grid gap-2 overflow-x-auto md:grid-cols-3 xl:grid-cols-6'>
            {board?.columns.map((col) => (
              <div key={col.status} className='bg-card flex min-h-[260px] flex-col rounded-lg border' onDragOver={(e) => e.preventDefault()}
                   onDrop={() => { const it = items.find((i) => i.id === dragId); if (it) move(it, col.status); setDragId(null); }}>
                <div className='flex items-center justify-between border-b px-2 py-1.5 text-sm font-medium' style={{ borderTop: `3px solid ${STATUS_COLOR[col.status]}` }}>
                  <span>{col.status_fa}</span><Badge variant='secondary'>{faNum.format(col.items.length)}</Badge>
                </div>
                <div className='flex flex-1 flex-col gap-1.5 p-1.5'>
                  {col.items.map((it) => (
                    <div key={it.id} draggable onDragStart={() => setDragId(it.id)} onClick={() => setEditing(it.id)}
                         className='bg-background hover:border-primary cursor-pointer rounded-md border p-2 text-xs shadow-sm'>
                      <div className='font-medium'>{it.title}</div>
                      {it.target_keyword && <div className='text-muted-foreground truncate'>🔑 {it.target_keyword}</div>}
                      <div className='mt-1 flex flex-wrap items-center gap-1'>
                        {it.priority && <Badge variant={it.priority === 'high' ? 'default' : 'outline'} className='text-[10px]'>{PRIORITY_FA[it.priority]}</Badge>}
                        {it.publish_date && <span className='text-muted-foreground' dir='ltr'>{it.publish_date}</span>}
                        {it.has_brief && <span title='بریف دارد'>📄</span>}
                        {it.latest_score != null && <span className='rounded px-1 text-[10px] text-white' style={{ background: it.latest_score >= 80 ? '#16a34a' : it.latest_score >= 60 ? '#f59e0b' : '#dc2626' }} title={`امتیاز کیفیت · ${it.review_status === 'ready' ? 'آماده' : it.review_status === 'changes_requested' ? 'نیاز به اصلاح' : 'بازبینی نشده'}`}>{Math.round(it.latest_score)}{it.review_status === 'ready' ? ' ✓' : ''}</span>}
                        {it.url && <span title={it.url}>🔗</span>}
                      </div>
                    </div>
                  ))}
                  {col.items.length === 0 && <div className='text-muted-foreground m-auto text-[11px]'>—</div>}
                </div>
              </div>
            ))}
          </div>
        </TabsContent>
        <TabsContent value='list' className='flex flex-col gap-2'>
          <div className='flex flex-wrap items-center gap-2'>
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder='جست‌وجو…' className='w-56' />
            <NativeSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className='w-44'><NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>{STATUS_ORDER.map((s) => <NativeSelectOption key={s} value={s}>{STATUS_FA[s]}</NativeSelectOption>)}</NativeSelect>
            <span className='text-muted-foreground ms-auto text-xs'>{faNum.format(filtered.length)} مورد</span>
          </div>
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader><TableRow><TableHead>عنوان</TableHead><TableHead>کلمه کلیدی</TableHead><TableHead>موضوع</TableHead><TableHead>وضعیت</TableHead><TableHead>اولویت</TableHead><TableHead>تاریخ انتشار</TableHead><TableHead>AI</TableHead><TableHead>URL</TableHead><TableHead>بریف</TableHead></TableRow></TableHeader>
              <TableBody>
                {filtered.map((it) => (
                  <TableRow key={it.id} className='cursor-pointer' onClick={() => setEditing(it.id)}>
                    <TableCell className='font-medium'>{it.title}</TableCell><TableCell>{it.target_keyword ?? '—'}</TableCell><TableCell>{it.topic ?? '—'}</TableCell>
                    <TableCell><Badge style={{ background: STATUS_COLOR[it.status] }}>{it.status_fa}</Badge></TableCell>
                    <TableCell>{it.priority ? PRIORITY_FA[it.priority] : '—'}</TableCell><TableCell dir='ltr'>{it.publish_date ?? '—'}{it.publish_time ? ` ${it.publish_time}` : ''}</TableCell>
                    <TableCell dir='ltr'>{it.ai_provider ?? '—'}</TableCell><TableCell className='max-w-48 truncate' dir='ltr'>{it.url ?? '—'}</TableCell><TableCell>{it.has_brief ? '✓' : '—'}</TableCell>
                  </TableRow>
                ))}
                {filtered.length === 0 && <TableRow><TableCell colSpan={9} className='text-muted-foreground text-center'>محتوایی نیست.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
        <TabsContent value='analytics'><AnalyticsPanel siteId={siteId} onOpen={(cid) => setEditing(cid)} /></TabsContent>
      </Tabs>
      <ContentEditor siteId={siteId} cid={editing} onClose={() => setEditing(null)} onChanged={load} />
    </div>
  );
}
