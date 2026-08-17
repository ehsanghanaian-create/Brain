'use client';

import { KpiCard } from '@/components/seo-brain/kpi-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError, endpoints, type KeywordList, type KeywordOpportunity, type KeywordsMeta, type Site, type TopicMap } from '@/lib/api/client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { INTENT_FA, KW_STATUS_FA, OPP_KIND_FA, OPP_STATUS_FA, PRIORITY_FA, num, pct } from '../constants';
import { ImportDialog } from './import-dialog';
import { KeywordEditor } from './keyword-editor';

const PAGE = 25;

export function KeywordsPage({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const [siteId, setSiteId] = useState(initialSiteId);
  const [meta, setMeta] = useState<KeywordsMeta | null>(null);
  const [tab, setTab] = useState('list');
  const [list, setList] = useState<KeywordList | null>(null);
  const [filters, setFilters] = useState({ q: '', status: '', intent: '', priority: '', cluster_id: '', sort: 'updated_at', order: 'desc' });
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [topicMap, setTopicMap] = useState<TopicMap | null>(null);
  const [opps, setOpps] = useState<{ items: KeywordOpportunity[]; total: number } | null>(null);
  const [oppFilter, setOppFilter] = useState({ kind: '', status: 'new' });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const l = await endpoints.keywords(siteId, { ...filters, limit: PAGE, offset: page * PAGE });
      setList(l);
    } catch (e) { setError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); }
  }, [siteId, filters, page]);
  const loadTopics = useCallback(async () => { try { setTopicMap(await endpoints.topicMap(siteId)); } catch (e) { setError(String(e)); } }, [siteId]);
  const loadOpps = useCallback(async () => { try { setOpps(await endpoints.keywordOpportunities(siteId, { ...oppFilter, limit: 200 })); } catch (e) { setError(String(e)); } }, [siteId, oppFilter]);

  useEffect(() => { endpoints.keywordsMeta(siteId).then(setMeta).catch(() => null); }, [siteId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'topics') loadTopics(); if (tab === 'opps') loadOpps(); }, [tab, loadTopics, loadOpps]);

  const refreshAll = () => { load(); if (tab === 'topics') loadTopics(); if (tab === 'opps') loadOpps(); };
  const run = async (name: string, fn: () => Promise<Record<string, unknown>>, msg: (r: Record<string, unknown>) => string) => {
    setBusy(name);
    try { const r = await fn(); toast.success(msg(r)); refreshAll(); } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  };
  const counts = list?.counts;
  const oppNew = counts ? Object.values(counts.opportunities_new).reduce((a, b) => a + b, 0) : 0;
  const withGsc = list?.items.filter((i) => i.gsc).length ?? 0;
  const setSort = (col: string) => setFilters((f) => ({ ...f, sort: col, order: f.sort === col && f.order === 'desc' ? 'asc' : 'desc' }));

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={siteId} onChange={(e) => { setSiteId(e.target.value); setPage(0); }} className='w-44'>
          {sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}
        </NativeSelect>
        <Button onClick={() => setEditing('new')}>افزودن کلمه کلیدی</Button>
        <Button variant='secondary' onClick={() => setImportOpen(true)}>ورود فایل (CSV / Excel / Sheet)</Button>
        <Button variant='outline' disabled={!!busy} onClick={() => run('cluster', () => endpoints.runClustering(siteId), (r) => `خوشه‌بندی انجام شد: ${r.clusters} خوشه برای ${r.keywords} کلمه`)}>{busy === 'cluster' ? '…' : 'خوشه‌بندی'}</Button>
        <Button variant='outline' disabled={!!busy} onClick={() => run('analyze', () => endpoints.analyzeKeywords(siteId), (r) => `تحلیل انجام شد: ${r.opportunities} فرصت (${r.with_gsc} کلمه با داده GSC)`)}>{busy === 'analyze' ? '…' : 'تحلیل فرصت‌ها'}</Button>
        <Button variant='ghost' disabled={!!busy} onClick={() => run('sync', () => endpoints.syncKeywordGraph(siteId), (r) => `گراف به‌روزرسانی شد: ${r.nodes} گره، ${r.edges} یال`)}>همگام‌سازی گراف</Button>
        <Link href={`/dashboard/graph?site=${siteId}`} className='text-xs underline'>مشاهده در گراف</Link>
      </div>
      {error && <p className='text-destructive text-sm'>{error}</p>}
      <div className='grid grid-cols-2 gap-3 md:grid-cols-5'>
        <KpiCard label='کلمات کلیدی' value={counts?.total ?? null} />
        <KpiCard label='با داده GSC (این صفحه)' value={list ? withGsc : null} hint={`از ${list?.items.length ?? 0} ردیف`} />
        <KpiCard label='خوشه‌ها' value={counts?.clusters ?? null} />
        <KpiCard label='با صفحه هدف' value={counts?.with_target ?? null} />
        <KpiCard label='فرصت‌های جدید' value={counts ? oppNew : null} hint={counts ? Object.entries(counts.opportunities_new).map(([k, v]) => `${OPP_KIND_FA[k] ?? k} ${v}`).join(' · ') : undefined} />
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList>
          <TabsTrigger value='list'>کلمات کلیدی</TabsTrigger>
          <TabsTrigger value='topics'>خوشه‌ها و نقشه موضوعی</TabsTrigger>
          <TabsTrigger value='opps'>فرصت‌ها {oppNew ? <Badge className='ms-1'>{oppNew}</Badge> : null}</TabsTrigger>
        </TabsList>

        <TabsContent value='list' className='flex flex-col gap-2'>
          <div className='flex flex-wrap items-center gap-2'>
            <Input value={filters.q} onChange={(e) => { setFilters((f) => ({ ...f, q: e.target.value })); setPage(0); }} placeholder='جست‌وجو (کلمه، URL)…' className='w-56' />
            <NativeSelect value={filters.status} onChange={(e) => { setFilters((f) => ({ ...f, status: e.target.value })); setPage(0); }} className='w-40'><NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>{Object.entries(KW_STATUS_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
            <NativeSelect value={filters.intent} onChange={(e) => { setFilters((f) => ({ ...f, intent: e.target.value })); setPage(0); }} className='w-36'><NativeSelectOption value=''>همه اینتنت‌ها</NativeSelectOption>{Object.entries(INTENT_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
            <NativeSelect value={filters.priority} onChange={(e) => { setFilters((f) => ({ ...f, priority: e.target.value })); setPage(0); }} className='w-32'><NativeSelectOption value=''>همه اولویت‌ها</NativeSelectOption>{Object.entries(PRIORITY_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
            {filters.cluster_id && <Badge variant='secondary' className='cursor-pointer' onClick={() => setFilters((f) => ({ ...f, cluster_id: '' }))}>خوشه: {filters.cluster_id} ✕</Badge>}
            <span className='text-muted-foreground ms-auto text-xs'>{list ? `${num(list.total)} نتیجه` : ''}</span>
          </div>
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader>
                <TableRow>
                  {[['keyword', 'کلمه کلیدی'], ['intent', 'اینتنت'], ['topic', 'خوشه / موضوع'], ['volume', 'حجم'], ['difficulty', 'سختی'], ['priority', 'اولویت'], ['target_url', 'صفحه هدف'], ['status', 'وضعیت']].map(([k, l]) => (
                    <TableHead key={k} className='cursor-pointer select-none whitespace-nowrap' onClick={() => setSort(k)}>{l}{filters.sort === k ? (filters.order === 'desc' ? ' ↓' : ' ↑') : ''}</TableHead>
                  ))}
                  <TableHead className='whitespace-nowrap'>جایگاه</TableHead><TableHead>CTR</TableHead><TableHead>ایمپرشن</TableHead><TableHead>کلیک</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list?.items.map((k) => (
                  <TableRow key={k.id} className='cursor-pointer' onClick={() => setEditing(k.id)}>
                    <TableCell className='font-medium'>{k.keyword}</TableCell>
                    <TableCell>{k.intent ? INTENT_FA[k.intent] ?? k.intent : '—'}</TableCell>
                    <TableCell>{k.cluster ? <button className='underline decoration-dotted' onClick={(e) => { e.stopPropagation(); setFilters((f) => ({ ...f, cluster_id: k.cluster_id ?? '' })); }}>{k.topic ?? k.cluster.name}</button> : k.topic ?? '—'}</TableCell>
                    <TableCell className='tabular-nums'>{num(k.volume)}</TableCell>
                    <TableCell className='tabular-nums'>{num(k.difficulty)}</TableCell>
                    <TableCell>{k.priority ? <Badge variant={k.priority === 'high' ? 'default' : 'secondary'}>{PRIORITY_FA[k.priority]}</Badge> : '—'}</TableCell>
                    <TableCell className='max-w-56 truncate' dir='ltr' title={k.target_url ?? k.gsc?.top_page ?? ''}>{k.target_url ?? (k.gsc?.top_page ? <span className='text-muted-foreground'>{k.gsc.top_page}</span> : '—')}</TableCell>
                    <TableCell><Badge variant='outline'>{KW_STATUS_FA[k.status] ?? k.status}</Badge></TableCell>
                    <TableCell className='tabular-nums'>{num(k.gsc?.position, 1)}</TableCell>
                    <TableCell className='tabular-nums'>{pct(k.gsc?.ctr)}</TableCell>
                    <TableCell className='tabular-nums'>{num(k.gsc?.impressions)}</TableCell>
                    <TableCell className='tabular-nums'>{num(k.gsc?.clicks)}</TableCell>
                  </TableRow>
                ))}
                {list && list.items.length === 0 && <TableRow><TableCell colSpan={12} className='text-muted-foreground text-center'>کلمه کلیدی‌ای نیست — فایل وارد کنید یا دستی اضافه کنید.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
          {list && list.total > PAGE && (
            <div className='flex items-center justify-between text-xs'>
              <Button size='sm' variant='outline' disabled={page === 0} onClick={() => setPage((p) => p - 1)}>قبلی</Button>
              <span>صفحه {num(page + 1)} از {num(Math.ceil(list.total / PAGE))}</span>
              <Button size='sm' variant='outline' disabled={(page + 1) * PAGE >= list.total} onClick={() => setPage((p) => p + 1)}>بعدی</Button>
            </div>
          )}
        </TabsContent>

        <TabsContent value='topics'>
          {!topicMap ? <p className='text-muted-foreground text-sm'>در حال بارگذاری…</p> : topicMap.clusters.length === 0 ? (
            <p className='text-muted-foreground text-sm'>هنوز خوشه‌ای نیست — «خوشه‌بندی» را اجرا کنید (یا ستون خوشه/موضوع را در فایل ورودی پر کنید).</p>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
              {topicMap.clusters.map((c) => <ClusterCard key={c.cluster_id} c={c} siteId={siteId} onChanged={loadTopics} onOpen={(kid) => setEditing(kid)} onFilter={() => { setFilters((f) => ({ ...f, cluster_id: c.cluster_id })); setTab('list'); }} />)}
              {topicMap.unclustered.length > 0 && (
                <div className='rounded-lg border border-dashed p-3 text-sm'><div className='font-medium'>بدون خوشه ({topicMap.unclustered.length})</div>
                  <div className='mt-1 flex flex-wrap gap-1'>{topicMap.unclustered.map((k) => <Badge key={k.id} variant='outline' className='cursor-pointer' onClick={() => setEditing(k.id)}>{k.keyword}</Badge>)}</div></div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value='opps' className='flex flex-col gap-2'>
          <div className='flex flex-wrap items-center gap-2'>
            <NativeSelect value={oppFilter.kind} onChange={(e) => setOppFilter((f) => ({ ...f, kind: e.target.value }))} className='w-48'><NativeSelectOption value=''>همه انواع</NativeSelectOption>{Object.entries(OPP_KIND_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
            <NativeSelect value={oppFilter.status} onChange={(e) => setOppFilter((f) => ({ ...f, status: e.target.value }))} className='w-40'><NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>{Object.entries(OPP_STATUS_FA).map(([k, v]) => <NativeSelectOption key={k} value={k}>{v}</NativeSelectOption>)}</NativeSelect>
            <span className='text-muted-foreground ms-auto text-xs'>{opps ? `${num(opps.total)} فرصت` : ''}</span>
          </div>
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader><TableRow><TableHead>نوع</TableHead><TableHead>کلمه کلیدی</TableHead><TableHead>صفحه هدف</TableHead><TableHead>امتیاز</TableHead><TableHead>دلیل</TableHead><TableHead>شواهد</TableHead><TableHead>وضعیت</TableHead></TableRow></TableHeader>
              <TableBody>
                {opps?.items.map((o) => {
                  const ev = o.evidence as Record<string, number | null>;
                  return (
                    <TableRow key={o.id}>
                      <TableCell><Badge>{OPP_KIND_FA[o.kind] ?? o.kind}</Badge></TableCell>
                      <TableCell className='font-medium'><button className='hover:underline' onClick={() => setEditing(o.keyword_id)}>{o.keyword}</button></TableCell>
                      <TableCell className='max-w-56 truncate' dir='ltr' title={o.target_url ?? ''}>{o.target_url ?? '—'}</TableCell>
                      <TableCell className='tabular-nums'>{num(o.score, 2)}</TableCell>
                      <TableCell className='max-w-md text-xs'>{o.reason}</TableCell>
                      <TableCell className='text-muted-foreground text-xs whitespace-nowrap' dir='ltr'>{ev.position != null ? `#${Number(ev.position).toFixed(1)} · ` : ''}{ev.impressions ?? 0} imp · {ev.clicks ?? 0} clk{ev.inbound_links != null ? ` · ${ev.inbound_links} in` : ''}</TableCell>
                      <TableCell>
                        <div className='flex gap-1'>
                          {o.status === 'new' ? (<>
                            <Button size='sm' variant='outline' onClick={async () => { await endpoints.setOpportunityStatus(siteId, o.id, 'accepted'); loadOpps(); load(); }}>پذیرش</Button>
                            <Button size='sm' variant='ghost' onClick={async () => { await endpoints.setOpportunityStatus(siteId, o.id, 'dismissed'); loadOpps(); load(); }}>رد</Button>
                          </>) : (<>
                            <Badge variant='secondary'>{OPP_STATUS_FA[o.status] ?? o.status}</Badge>
                            {o.status === 'accepted' && <Button size='sm' variant='ghost' onClick={async () => { await endpoints.setOpportunityStatus(siteId, o.id, 'done'); loadOpps(); }}>انجام شد</Button>}
                          </>)}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {opps && opps.items.length === 0 && <TableRow><TableCell colSpan={7} className='text-muted-foreground text-center'>فرصتی نیست — «تحلیل فرصت‌ها» را اجرا کنید (نیازمند کلمات کلیدی + داده GSC).</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>

      <ImportDialog siteId={siteId} open={importOpen} onOpenChange={setImportOpen} onDone={refreshAll} />
      <KeywordEditor siteId={siteId} kid={editing} meta={meta} onClose={() => setEditing(null)} onChanged={refreshAll} />
    </div>
  );
}

function ClusterCard({ c, siteId, onChanged, onOpen, onFilter }: { c: TopicMap['clusters'][number]; siteId: string; onChanged: () => void; onOpen: (kid: number) => void; onFilter: () => void }) {
  const [topic, setTopic] = useState(c.topic ?? '');
  const [edit, setEdit] = useState(false);
  return (
    <div className='rounded-lg border p-3 text-sm'>
      <div className='flex items-start justify-between gap-2'>
        <div className='min-w-0'>
          {edit ? (
            <form className='flex gap-1' onSubmit={async (e) => { e.preventDefault(); await endpoints.updateCluster(siteId, c.cluster_id, { topic }); setEdit(false); onChanged(); toast.success('موضوع ذخیره شد'); }}>
              <Input value={topic} onChange={(e) => setTopic(e.target.value)} className='h-7 text-xs' /><Button size='sm' type='submit'>ذخیره</Button>
            </form>
          ) : (
            <button className='truncate font-semibold hover:underline' title='ویرایش موضوع' onClick={() => setEdit(true)}>{c.topic ?? c.name}</button>
          )}
          <div className='text-muted-foreground truncate text-xs'>{c.name} · {c.method?.includes('manual') ? 'دستی' : 'خودکار'}</div>
        </div>
        <Badge variant='outline' className='cursor-pointer whitespace-nowrap' onClick={onFilter}>{num(c.keywords_count)} کلمه</Badge>
      </div>
      <div className='text-muted-foreground mt-2 grid grid-cols-4 gap-1 text-center text-[11px]'>
        <div><div>حجم</div><div className='text-foreground tabular-nums'>{num(c.volume)}</div></div>
        <div><div>ایمپرشن</div><div className='text-foreground tabular-nums'>{num(c.gsc.impressions)}</div></div>
        <div><div>کلیک</div><div className='text-foreground tabular-nums'>{num(c.gsc.clicks)}</div></div>
        <div><div>جایگاه</div><div className='text-foreground tabular-nums'>{num(c.gsc.avg_position, 1)}</div></div>
      </div>
      <div className='mt-2 flex flex-wrap gap-1'>
        {c.members.slice(0, 12).map((k) => <Badge key={k.id} variant='secondary' className='cursor-pointer' onClick={() => onOpen(k.id)}>{k.keyword}{k.gsc?.position != null ? <span className='ms-1 opacity-70' dir='ltr'>#{k.gsc.position.toFixed(0)}</span> : null}</Badge>)}
        {c.members.length > 12 && <Badge variant='outline'>+{c.members.length - 12}</Badge>}
      </div>
      {c.targets.length > 0 && <div className='text-muted-foreground mt-2 truncate text-xs' dir='ltr'>→ {c.targets.join(' , ')}</div>}
    </div>
  );
}
