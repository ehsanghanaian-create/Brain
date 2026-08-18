'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError, endpoints, type PlanCategory } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { INTENT_FA, SOURCE_FA, fa } from '../constants';

const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));

export function PlanCategories({ siteId, hasWp, onOpen, onChanged, refreshKey }: { siteId: string; hasWp: boolean; onOpen: (pid: number) => void; onChanged: () => void; refreshKey: number }) {
  const [tree, setTree] = useState<PlanCategory[]>([]);
  const [sel, setSel] = useState<PlanCategory | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [newParent, setNewParent] = useState('');
  const load = useCallback(async () => { try { setTree(await endpoints.planCategories(siteId, true)); } catch (e) { err(e); } }, [siteId]);
  useEffect(() => { load(); }, [load, refreshKey]);
  const flat = (nodes: PlanCategory[], depth = 0): (PlanCategory & { depth: number })[] => nodes.flatMap((n) => [{ ...n, depth }, ...flat(n.children ?? [], depth + 1)]);
  const all = flat(tree);
  async function openCat(c: PlanCategory) { try { setSel(await endpoints.planCategory(siteId, c.id)); } catch (e) { err(e); } }
  const groups: Record<string, (PlanCategory & { depth: number })[]> = { wordpress: [], brain: [], manual: [] };
  all.forEach((c) => groups[c.source]?.push(c));
  return (
    <div className='grid gap-3 lg:grid-cols-[380px_1fr]'>
      <div className='flex flex-col gap-2 text-sm'>
        <div className='flex flex-wrap gap-1'>
          <Button size='sm' disabled={!!busy} onClick={async () => { setBusy('sync'); try { const r = await endpoints.planCategoriesSync(siteId); toast.success(`همگام‌سازی: ${r.wordpress ? `${r.wordpress.terms} دسته وردپرس` : 'وردپرس متصل نیست'} · ${r.brain?.categories ?? 0} دسته موضوعی مغز · ${r.analysis?.analyzed ?? 0} تحلیل`); load(); onChanged(); } catch (e) { err(e); } finally { setBusy(null); } }} title={hasWp ? 'خواندن دسته‌ها از REST وردپرس (فقط‌خواندنی) + ساخت دسته‌های موضوعی مغز از خوشه‌های کلمات کلیدی' : 'وردپرس برای این سایت تنظیم نشده — فقط دسته‌های موضوعی مغز ساخته می‌شود'}>{busy === 'sync' ? '…' : 'همگام‌سازی (وردپرس + مغز)'}</Button>
          <Button size='sm' variant='secondary' disabled={!!busy} onClick={async () => { setBusy('an'); try { const r = await endpoints.planCategoriesAnalyze(siteId); toast.success(`${r.analyzed} دسته تحلیل شد`); load(); } catch (e) { err(e); } finally { setBusy(null); } }}>تحلیل پوشش</Button>
        </div>
        {!hasWp && <p className='text-muted-foreground text-xs'>آدرس وردپرس در «سایت‌ها» تنظیم نشده؛ دسته‌ها را دستی بسازید یا از خوشه‌های مغز استفاده کنید.</p>}
        {(['wordpress', 'brain', 'manual'] as const).map((src) => (
          <div key={src} className='rounded-md border p-2'>
            <div className='mb-1 text-xs font-medium'>{SOURCE_FA[src]} ({fa.format(groups[src].length)})</div>
            <div className='flex flex-col gap-0.5'>
              {groups[src].map((c) => (
                <button key={c.id} onClick={() => openCat(c)} className={`flex items-center gap-1 rounded px-1 py-0.5 text-start text-xs hover:bg-accent ${sel?.id === c.id ? 'bg-accent' : ''}`} style={{ paddingInlineStart: 4 + c.depth * 14 }}>
                  <span className='font-medium'>{c.depth > 0 ? '└ ' : ''}{c.name}</span>
                  <span className='text-muted-foreground ms-auto flex gap-1'><span title='نوشته‌های وردپرس'>📄{c.post_count}</span><span title='صفحات'>🌐{c.page_count}</span><span title='کلمات کلیدی مرتبط'>🔑{c.keyword_count}</span><span title='برنامه‌ها'>📋{c.plan_count}</span>{c.coverage_score != null && <span title='پوشش' style={{ color: c.coverage_score >= 70 ? '#16a34a' : c.coverage_score >= 40 ? '#f59e0b' : '#dc2626' }}>{Math.round(c.coverage_score)}٪</span>}</span>
                </button>
              ))}
              {groups[src].length === 0 && <span className='text-muted-foreground text-xs'>—</span>}
            </div>
          </div>
        ))}
        <form className='flex gap-1' onSubmit={async (e) => { e.preventDefault(); if (!newName.trim()) return; try { await endpoints.planCategoryCreate(siteId, { name: newName.trim(), parent_id: newParent ? Number(newParent) : null }); setNewName(''); load(); onChanged(); } catch (er) { err(er); } }}>
          <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder='دسته دستی جدید…' className='h-8' /><NativeSelect value={newParent} onChange={(e) => setNewParent(e.target.value)} className='h-8 w-32'><NativeSelectOption value=''>بدون والد</NativeSelectOption>{all.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}</NativeSelect><Button size='sm' type='submit'>افزودن</Button>
        </form>
      </div>
      <div className='rounded-md border p-3 text-sm'>
        {!sel ? <p className='text-muted-foreground'>یک دسته انتخاب کنید تا هوش دسته (صفحات، کلمات، شکاف‌ها، اینتنت‌ها، برنامه‌ها) نمایش داده شود.</p> : (
          <div className='grid gap-2'>
            <div className='flex flex-wrap items-center gap-2'><span className='text-base font-semibold'>{sel.name}</span><Badge variant='outline'>{sel.source_fa}</Badge>{sel.url && <a className='text-xs underline' href={sel.url} target='_blank' rel='noreferrer' dir='ltr'>{sel.url}</a>}{sel.metadata?.related_wp_category && <Badge variant='secondary'>مرتبط با دسته وردپرس: {sel.metadata.related_wp_category}</Badge>}
              {sel.source !== 'wordpress' && <Button size='sm' variant='ghost' className='text-destructive ms-auto' onClick={async () => { if (!confirm('حذف شود؟')) return; await endpoints.planCategoryDelete(siteId, sel.id); setSel(null); load(); }}>حذف</Button>}</div>
            <div className='grid grid-cols-2 gap-2 text-xs md:grid-cols-5'>
              {[['نوشته‌های وردپرس', sel.post_count], ['صفحات نگاشت‌شده', sel.page_count], ['کلمات مرتبط', sel.keyword_count], ['برنامه‌ها', sel.plan_count], ['پوشش', sel.coverage_score != null ? `${Math.round(sel.coverage_score)}٪` : '—']].map(([k, v]) => <div key={String(k)} className='rounded border p-2'><div className='text-muted-foreground'>{k}</div><div className='text-lg font-semibold'>{typeof v === 'number' ? fa.format(v) : v}</div></div>)}
            </div>
            <div className='text-xs'>اینتنت‌ها: {Object.entries(sel.intelligence?.intents ?? {}).map(([k, v]) => <Badge key={k} variant='outline' className='me-1'>{INTENT_FA[k] ?? k} {String(v)}</Badge>)}</div>
            <div className='grid gap-2 md:grid-cols-2 text-xs'>
              <div className='rounded border p-2'><div className='mb-1 font-medium'>شکاف‌های محتوایی (کلمات بدون پوشش)</div><ul className='space-y-0.5'>{(sel.intelligence?.gaps ?? []).map((g: any) => <li key={g.id} className='flex items-center gap-1'><span>{g.keyword}</span><span className='text-muted-foreground'>· {g.volume ?? '—'} · {INTENT_FA[g.intent] ?? g.intent}</span><Button size='sm' variant='ghost' className='ms-auto h-6' onClick={async () => { try { const r = await endpoints.planKeywordApply(siteId, [{ keyword_id: g.id, plan_id: 'new' }]); toast.success('برنامه ساخته شد'); onChanged(); if (r.created[0]) onOpen(r.created[0].plan_id); } catch (e) { err(e); } }}>+ برنامه</Button></li>)}{!(sel.intelligence?.gaps ?? []).length && <li className='text-muted-foreground'>—</li>}</ul></div>
              <div className='rounded border p-2'><div className='mb-1 font-medium'>کلمات کلیدی برتر</div><ul className='space-y-0.5'>{(sel.intelligence?.top_keywords ?? []).map((g: any) => <li key={g.id}>{g.keyword} <span className='text-muted-foreground'>· {g.volume ?? '—'}</span></li>)}</ul></div>
              <div className='rounded border p-2'><div className='mb-1 font-medium'>صفحات ({sel.intelligence?.pages?.length ?? 0})</div><ul className='space-y-0.5'>{(sel.intelligence?.pages ?? []).slice(0, 12).map((p: any) => <li key={p.node_id} className='truncate' dir='auto'>{p.title}</li>)}</ul></div>
              <div className='rounded border p-2'><div className='mb-1 font-medium'>برنامه‌های این دسته ({sel.plans?.length ?? 0})</div><ul className='space-y-0.5'>{(sel.plans ?? []).map((p) => <li key={p.id}><button className='hover:underline' onClick={() => onOpen(p.id)}>{p.title}</button> <span className='text-muted-foreground'>· {p.status_fa}</span></li>)}</ul></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
