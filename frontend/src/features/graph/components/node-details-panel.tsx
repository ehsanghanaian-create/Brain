'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import type { NodeDetails } from '@/lib/api/client';
import { IconClick, IconFocus2, IconSearch } from '@tabler/icons-react';
import { CONTENT_STATUS_FA, NODE_STYLE, RELATION_FA, SEVERITY_FA } from '../constants';

const fa = new Intl.NumberFormat('fa-IR');
const pct = (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}٪` : '—');
const num = (v: unknown, d = 0) => (typeof v === 'number' ? fa.format(Number(v.toFixed(d))) : '—');

type Neighbor = { id: string; type: string; label: string; url?: string | null; relation: string; direction: 'in' | 'out' };

export function NodeDetailsPanel({
  details,
  loading,
  error,
  onClose,
  onFocus
}: {
  details: NodeDetails | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onFocus: (nodeId: string) => void;
}) {
  if (!details && !loading && !error) {
    return (
      <aside className='bg-card flex h-full w-full flex-col overflow-hidden rounded-xl border shadow-sm'>
        <header className='border-b p-4'><h3 className='font-semibold'>راهنمای خواندن گراف</h3><p className='text-muted-foreground mt-1 text-xs leading-5'>لازم نیست همه گره‌ها را هم‌زمان بررسی کنید؛ از جست‌وجو یا یک گره مهم شروع کنید.</p></header>
        <div className='flex-1 space-y-5 overflow-y-auto p-4 text-sm'>
          <ol className='space-y-3'>
            <li className='flex gap-3'><span className='flex size-8 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600'><IconSearch className='size-4' /></span><span><strong className='block text-sm'>۱. گره را پیدا کن</strong><span className='text-muted-foreground text-xs leading-5'>نام صفحه، URL یا کلمه کلیدی را جست‌وجو کن.</span></span></li>
            <li className='flex gap-3'><span className='flex size-8 shrink-0 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600'><IconClick className='size-4' /></span><span><strong className='block text-sm'>۲. روی گره کلیک کن</strong><span className='text-muted-foreground text-xs leading-5'>فقط همسایه‌های مرتبط پررنگ می‌شوند و اطلاعات اینجا باز می‌شود.</span></span></li>
            <li className='flex gap-3'><span className='flex size-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600'><IconFocus2 className='size-4' /></span><span><strong className='block text-sm'>۳. نمای متمرکز را فعال کن</strong><span className='text-muted-foreground text-xs leading-5'>برای حذف شلوغی، فقط ارتباط‌های مستقیم همان گره را ببین.</span></span></li>
          </ol>
          <Separator />
          <section><h4 className='mb-2 text-xs font-semibold'>راهنمای رنگ‌ها</h4><div className='flex flex-wrap gap-1.5'>{['PAGE', 'QUERY', 'BRAND', 'SERVICE', 'SEO_PROBLEM', 'SEO_OPPORTUNITY'].map((type) => <Badge key={type} variant='outline' className='gap-1.5'><span className='size-2 rounded-full' style={{ background: NODE_STYLE[type]?.color }} />{NODE_STYLE[type]?.fa}</Badge>)}</div></section>
          <p className='text-muted-foreground rounded-lg border bg-muted/25 p-3 text-xs leading-5'>رنگ فقط نوع داده را نشان می‌دهد؛ ضخیم‌شدن رابطه یعنی آن یال مستقیماً به گره انتخاب‌شده وصل است.</p>
        </div>
      </aside>
    );
  }
  const st = details ? NODE_STYLE[details.type] : undefined;
  return (
    <aside className='bg-card flex h-full w-full flex-col overflow-hidden rounded-lg border'>
      <header className='flex items-start justify-between gap-2 border-b p-3'>
        <div className='min-w-0'>
          {details && (
            <>
              <div className='flex items-center gap-2'>
                <span className='h-3 w-3 rounded-full' style={{ background: st?.color }} />
                <Badge variant='outline'>{st?.fa ?? details.type}</Badge>
              </div>
              <h3 className='mt-1 truncate text-sm font-semibold' title={details.label}>{details.label}</h3>
              {details.url && (
                <a href={details.url} target='_blank' rel='noreferrer' className='text-muted-foreground block truncate text-xs hover:underline' dir='ltr'>
                  {details.url}
                </a>
              )}
            </>
          )}
          {loading && <p className='text-muted-foreground text-xs'>در حال بارگذاری…</p>}
        </div>
        <Button variant='ghost' size='sm' onClick={onClose}>✕</Button>
      </header>
      <div className='flex-1 space-y-4 overflow-y-auto p-3 text-sm'>
        {error && <p className='text-destructive'>{error}</p>}
        {details && <Body d={details} onFocus={onFocus} />}
      </div>
    </aside>
  );
}

function Body({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const t = d.type;
  if (t === 'PAGE' || t === 'POST' || t === 'CATEGORY') return <PageBody d={d} onFocus={onFocus} />;
  if (t === 'QUERY' || t === 'KEYWORD') return <KeywordBody d={d} onFocus={onFocus} />;
  if (t === 'SEO_PROBLEM') return <ProblemBody d={d} />;
  if (t === 'SEO_OPPORTUNITY') return <OpportunityBody d={d} />;
  if (t === 'BRAND' || t === 'MODEL' || t === 'SERVICE' || t === 'LOCATION') return <EntityBody d={d} onFocus={onFocus} />;
  if (t === 'SCHEMA') return <SchemaBody d={d} onFocus={onFocus} />;
  if (t === 'SITE') return <SiteBody d={d} />;
  if (t === 'CONTENT_PLAN') return <PlanBody d={d} onFocus={onFocus} />;
  if (t === 'CONTENT_CLUSTER' || t === 'SEARCH_INTENT' || t === 'FUNNEL_STAGE') return <PlanGroupBody d={d} onFocus={onFocus} />;
  return <Generic d={d} onFocus={onFocus} />;
}

function KV({ k, v, ltr }: { k: string; v: React.ReactNode; ltr?: boolean }) {
  return (
    <div className='flex items-start justify-between gap-3 py-1'>
      <span className='text-muted-foreground shrink-0'>{k}</span>
      <span className='text-end break-all' dir={ltr ? 'ltr' : undefined}>{v}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className='mb-1 text-xs font-semibold tracking-wide uppercase opacity-70'>{title}</h4>
      {children}
    </section>
  );
}

function NeighborList({ items, onFocus, empty = 'موردی نیست' }: { items: Neighbor[]; onFocus: (id: string) => void; empty?: string }) {
  if (!items?.length) return <p className='text-muted-foreground text-xs'>{empty}</p>;
  return (
    <ul className='space-y-1'>
      {items.map((n) => (
        <li key={`${n.relation}:${n.id}`}>
          <button className='hover:bg-accent flex w-full items-center gap-2 rounded px-1 py-0.5 text-start text-xs' onClick={() => onFocus(n.id)}>
            <span className='h-2 w-2 shrink-0 rounded-full' style={{ background: NODE_STYLE[n.type]?.color }} />
            <span className='truncate'>{n.label}</span>
            <span className='text-muted-foreground ms-auto shrink-0'>{RELATION_FA[n.relation] ?? n.relation}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function PageBody({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const p = (d.page ?? {}) as Record<string, any>;
  const rel = (d.related ?? {}) as { queries?: Neighbor[]; entities?: Neighbor[] };
  const gsc = p.gsc as Record<string, number> | null;
  return (
    <>
      <Section title='وضعیت'>
        <KV k='وضعیت محتوا' v={<Badge variant={p.content_status === 'ok' ? 'default' : 'destructive'}>{CONTENT_STATUS_FA[p.content_status] ?? p.content_status ?? '—'}</Badge>} />
        <KV k='عنوان' v={p.title ?? '—'} />
        <KV k='H1' v={Array.isArray(p.h1) ? p.h1.filter(Boolean).join(' | ') || '—' : p.h1 ?? '—'} />
        <KV k='تعداد کلمات' v={num(p.word_count)} />
        <KV k='قابل ایندکس' v={p.indexable == null ? '—' : p.indexable ? 'بله' : `خیر (${p.indexability_reason ?? ''})`} />
        <KV k='کد وضعیت' v={p.status_code ?? '—'} ltr />
        <KV k='canonical' v={p.canonical ?? '—'} ltr />
      </Section>
      <Separator />
      <Section title='لینک‌ها'>
        <KV k='ورودی (بدنه)' v={`${num(p.links?.inbound)} (${num(p.links?.inbound_body)})`} />
        <KV k='خروجی داخلی / خارجی' v={`${num(p.links?.outbound)} / ${num(p.links?.external)}`} />
        {p.links?.inbound_sources?.length > 0 && (
          <details className='mt-1'>
            <summary className='cursor-pointer text-xs'>منابع لینک ورودی ({p.links.inbound_sources.length})</summary>
            <ul className='mt-1 space-y-0.5 text-xs' dir='ltr'>
              {p.links.inbound_sources.map((s: any, i: number) => (
                <li key={i} className='truncate'>{s.url} {s.anchor ? `— “${s.anchor}”` : ''}{s.nav ? ' (nav)' : ''}</li>
              ))}
            </ul>
          </details>
        )}
      </Section>
      <Separator />
      <Section title='Search Console'>
        {gsc ? (
          <>
            <KV k='کلیک / ایمپرشن' v={`${num(gsc.clicks)} / ${num(gsc.impressions)}`} />
            <KV k='CTR' v={pct(gsc.ctr)} />
            <KV k='جایگاه میانگین' v={num(gsc.position, 1)} />
          </>
        ) : (
          <p className='text-muted-foreground text-xs'>داده GSC برای این صفحه نیست</p>
        )}
        {p.top_queries?.length > 0 && (
          <ul className='mt-1 space-y-0.5 text-xs'>
            {p.top_queries.slice(0, 8).map((q: any, i: number) => (
              <li key={i} className='flex justify-between gap-2'><span className='truncate'>{q.query}</span><span className='text-muted-foreground shrink-0' dir='ltr'>#{Number(q.position).toFixed(1)} · {q.impressions}</span></li>
            ))}
          </ul>
        )}
      </Section>
      <Separator />
      <Section title={`مشکلات (${p.problems?.length ?? 0})`}>
        {p.problems?.length ? (
          <ul className='space-y-1'>
            {p.problems.map((pr: any, i: number) => (
              <li key={i} className='rounded border p-2 text-xs'>
                <div className='flex items-center justify-between'><span className='font-medium'>{pr.title_fa}</span><Badge variant={pr.severity === 'high' ? 'destructive' : 'secondary'}>{SEVERITY_FA[pr.severity] ?? pr.severity}</Badge></div>
                <div className='text-muted-foreground mt-1'>اقدام: {pr.action_fa}</div>
              </li>
            ))}
          </ul>
        ) : <p className='text-muted-foreground text-xs'>بدون مشکل ثبت‌شده</p>}
      </Section>
      {p.opportunities?.length > 0 && (
        <Section title={`فرصت‌ها (${p.opportunities.length})`}>
          <ul className='space-y-1 text-xs'>
            {p.opportunities.slice(0, 6).map((o: any, i: number) => (
              <li key={i} className='rounded border p-2'><span className='font-medium'>{o.type}</span> · امتیاز {num(o.score, 2)}<div className='text-muted-foreground'>{o.reason}</div><div>اقدام: {o.action_fa}</div></li>
            ))}
          </ul>
        </Section>
      )}
      {(d as any).link_health && (
        <>
          <Separator />
          <Section title='سلامت لینک داخلی'>
            <KV k='امتیاز (۰–۱۰۰)' v={<Badge style={{ background: (d as any).link_health.score >= 70 ? '#16a34a' : (d as any).link_health.score >= 40 ? '#f59e0b' : '#dc2626' }}>{num((d as any).link_health.score)}</Badge>} />
            {Object.entries((d as any).link_health.breakdown ?? {}).map(([k, v]) => <KV key={k} k={k} v={String(v)} ltr />)}
            {(d as any).link_health.flags?.length > 0 && <div className='flex flex-wrap gap-1 pt-1'>{(d as any).link_health.flags.map((f: string) => <Badge key={f} variant='outline'>{f}</Badge>)}</div>}
          </Section>
          <Section title='فرصت‌های لینک'>
            <NeighborList items={[...((d as any).link_suggestions?.to ?? []), ...((d as any).link_suggestions?.from ?? []), ...((d as any).link_suggestions?.supports ?? [])]} onFocus={onFocus} empty='پیشنهادی نیست' />
          </Section>
        </>
      )}
      <Separator />
      <Section title='کوئری‌های مرتبط'><NeighborList items={rel.queries ?? []} onFocus={onFocus} /></Section>
      <Section title='موجودیت‌ها'><NeighborList items={rel.entities ?? []} onFocus={onFocus} /></Section>
    </>
  );
}

function KeywordBody({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const k = (d.keyword ?? {}) as Record<string, any>;
  return (
    <>
      <Section title='عملکرد (GSC)'>
        <KV k='جایگاه' v={num(k.position, 1)} />
        <KV k='CTR' v={pct(k.ctr)} />
        <KV k='ایمپرشن' v={num(k.impressions)} />
        <KV k='کلیک' v={num(k.clicks)} />
        <KV k='تعداد صفحات رتبه‌دار' v={num(k.pages_count)} />
        {k.importance_reason && <KV k='دلیل اهمیت' v={k.importance_reason} ltr />}
        {k.intent && <KV k='اینتنت' v={k.intent} />}
      </Section>
      {k.per_page?.length > 0 && (
        <Section title='به تفکیک صفحه'>
          <ul className='space-y-0.5 text-xs' dir='ltr'>
            {k.per_page.map((r: any, i: number) => (
              <li key={i} className='flex justify-between gap-2'><span className='truncate'>{r.page}</span><span className='shrink-0'>#{Number(r.position).toFixed(1)} · {r.impressions} · {r.clicks}</span></li>
            ))}
          </ul>
        </Section>
      )}
      <Separator />
      <Section title='صفحات مرتبط'><NeighborList items={k.related_pages ?? []} onFocus={onFocus} empty='هیچ صفحه‌ای برای این کوئری رتبه ندارد' /></Section>
    </>
  );
}

function ProblemBody({ d }: { d: NodeDetails }) {
  const p = (d.problem ?? {}) as Record<string, any>;
  return (
    <>
      <Section title='مشکل'>
        <KV k='نوع' v={p.title_fa ?? p.issue} />
        <KV k='شدت' v={<Badge variant={p.severity === 'high' ? 'destructive' : 'secondary'}>{SEVERITY_FA[p.severity] ?? p.severity ?? '—'}</Badge>} />
        <KV k='تعداد صفحات درگیر' v={num(p.count)} />
      </Section>
      <div className='rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2 text-xs'>
        <div className='font-medium'>اقدام پیشنهادی</div>
        <div>{p.action_fa}</div>
      </div>
      <Section title='صفحات درگیر'>
        <ul className='space-y-0.5 text-xs' dir='ltr'>
          {(p.affected_pages ?? []).map((a: any, i: number) => (
            <li key={i} className='truncate'>{a.url}{a.related_url ? ` ↔ ${a.related_url}` : ''}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}

function OpportunityBody({ d }: { d: NodeDetails }) {
  const o = (d.opportunity ?? {}) as Record<string, any>;
  return (
    <>
      <Section title='فرصت'>
        <KV k='نوع' v={o.type} ltr />
        <KV k='تعداد' v={num(o.count)} />
      </Section>
      <div className='rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2 text-xs'><div className='font-medium'>اقدام پیشنهادی</div><div>{o.action_fa}</div></div>
      <Section title='موارد'>
        <ul className='space-y-1 text-xs'>
          {(o.items ?? []).map((it: any, i: number) => (
            <li key={i} className='rounded border p-2'>
              <div dir='ltr' className='truncate'>{it.url}{it.related_url ? ` → ${it.related_url}` : ''}</div>
              {it.query && <div>کوئری: {it.query}</div>}
              <div className='text-muted-foreground'>{it.reason} · امتیاز {num(it.score, 2)}</div>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}

function EntityBody({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const e = (d.entity ?? {}) as Record<string, any>;
  return (
    <>
      <Section title='موجودیت'>
        <KV k='نوع' v={NODE_STYLE[e.kind]?.fa ?? e.kind} />
        {e.aliases?.length > 0 && <KV k='نام‌های دیگر' v={e.aliases.join('، ')} />}
        {e.evidence && <KV k='شواهد' v={<code className='text-[10px]' dir='ltr'>{JSON.stringify(e.evidence)}</code>} />}
      </Section>
      <Section title='صفحات درباره این موجودیت'><NeighborList items={e.pages ?? []} onFocus={onFocus} /></Section>
      {e.children?.length > 0 && <Section title='زیرمجموعه‌ها'><NeighborList items={e.children} onFocus={onFocus} /></Section>}
    </>
  );
}

function SchemaBody({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const s = (d.schema ?? {}) as Record<string, any>;
  return (
    <>
      <Section title='اسکیما'><KV k='نوع' v={s.type} ltr /><KV k='تعداد صفحات' v={num(s.pages?.length)} /></Section>
      <Section title='صفحات دارای این اسکیما'><NeighborList items={s.pages ?? []} onFocus={onFocus} /></Section>
    </>
  );
}

function SiteBody({ d }: { d: NodeDetails }) {
  const s = (d.site ?? {}) as Record<string, any>;
  const counts = (s.counts ?? {}) as Record<string, number>;
  return (
    <Section title='خلاصه سایت'>
      {Object.entries(counts).map(([k, v]) => <KV key={k} k={k} v={num(v)} ltr />)}
    </Section>
  );
}

function Generic({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  return <Section title='همسایه‌ها'><NeighborList items={((d.neighbors ?? (d.content as any)?.neighbors ?? []) as Neighbor[])} onFocus={onFocus} /></Section>;
}

// ---- phase 8.5: content plan nodes
function PlanBody({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const p = (d as any).plan as Record<string, any> | undefined;
  const rel = ((d as any).related ?? {}) as Record<string, Neighbor[]>;
  return (
    <>
      {p && (
        <Section title='برنامه محتوایی'>
          <KV k='وضعیت' v={p.status} /><KV k='نوع صفحه' v={p.page_type ?? '—'} /><KV k='اینتنت' v={`${p.intent ?? '—'}${p.serp_intent && p.serp_intent !== p.intent ? ` (SERP: ${p.serp_intent})` : ''}`} />
          <KV k='مرحله قیف' v={p.funnel_stage ?? '—'} /><KV k='کلمه کلیدی اصلی' v={p.primary_keyword ?? '—'} /><KV k='دسته' v={p.category?.name ?? '—'} />
          <KV k='اولویت' v={`${p.priority ?? '—'} · ${p.priority_score ?? '—'}${p.ai_priority != null ? ` · AI ${p.ai_priority}` : ''}`} /><KV k='شکاف محتوایی' v={p.content_gap ?? '—'} />
          <KV k='ریسک هم‌نوع‌خواری' v={p.cannibalization_risk ?? '—'} /><KV k='URL رتبه‌دار' v={p.ranking_url ?? '—'} ltr /><KV k='فرصت ترافیک' v={p.traffic_opportunity ?? '—'} />
          <KV k='ارزش کسب‌وکار' v={p.business_value ?? '—'} /><KV k='تاریخ انتشار' v={p.publish_date ?? '—'} ltr /><KV k='امتیاز محتوا' v={p.content_score ?? '—'} />
          {p.recommendation?.action_fa && <div className='mt-1 rounded border p-2 text-xs'><div className='font-medium'>پیشنهاد مغز: {p.recommendation.action_fa}</div><ul className='mt-1 list-disc ps-4'>{(p.recommendation.reasons_fa ?? []).slice(0, 5).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></div>}
          <a href={`/dashboard/content-planner?plan=${p.id}`} className='mt-2 inline-block text-xs underline'>باز کردن در برنامه‌ریز محتوا</a>
        </Section>
      )}
      <Section title='کلمات کلیدی هدف'><NeighborList items={rel.keywords ?? []} onFocus={onFocus} /></Section>
      <Section title='دسته / محتوا / اینتنت / مرحله'><NeighborList items={[...(rel.category ?? []), ...(rel.content ?? []), ...(rel.intent ?? []), ...(rel.stage ?? [])]} onFocus={onFocus} /></Section>
      <Section title='صفحات مرتبط و لینک‌ها'><NeighborList items={[...(rel.supports ?? []), ...(rel.links ?? [])]} onFocus={onFocus} /></Section>
    </>
  );
}

function PlanGroupBody({ d, onFocus }: { d: NodeDetails; onFocus: (id: string) => void }) {
  const items = ((d as any).plans ?? (d as any).cluster?.plans ?? []) as Neighbor[];
  return <Section title='برنامه‌های محتوایی'><NeighborList items={items} onFocus={onFocus} /></Section>;
}
