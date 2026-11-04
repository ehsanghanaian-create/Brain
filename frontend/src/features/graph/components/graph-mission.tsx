'use client';

import type { GraphView, PortfolioSite } from '@/lib/api/client';
import { IconArrowLeft, IconChartDots3, IconFileSearch, IconLink, IconListCheck, IconTargetArrow } from '@tabler/icons-react';
import Link from 'next/link';
import type { ToolbarState } from './graph-toolbar';

const LENSES = [
  { key: 'seo', title: 'نقشه سئو', detail: 'صفحه، جست‌وجو و مشکل', icon: IconFileSearch, href: (id: string) => `/dashboard/sites/${encodeURIComponent(id)}?tab=issues` },
  { key: 'content', title: 'ساختار محتوا', detail: 'دسته، صفحه و موضوع', icon: IconChartDots3, href: (id: string) => `/dashboard/sites/${encodeURIComponent(id)}?tab=urls` },
  { key: 'links', title: 'لینک داخلی', detail: 'مبدأ، مقصد و فرصت', icon: IconLink, href: (id: string) => `/dashboard/internal-linking?site=${encodeURIComponent(id)}` },
  { key: 'planner', title: 'برنامه محتوا', detail: 'کلمه، اینتنت و اقدام', icon: IconListCheck, href: (id: string) => `/dashboard/content-planner?site=${encodeURIComponent(id)}` }
] as const;

export function GraphMission({ site, siteId, mode, view, onModeChange }: {
  site: PortfolioSite | null;
  siteId: string;
  mode: ToolbarState['mode'];
  view: GraphView | null;
  onModeChange: (mode: ToolbarState['mode']) => void;
}) {
  const current = LENSES.find((item) => item.key === mode) ?? LENSES[0];
  const hasEvidence = view?.mode.key === mode && view.nodes.length > 0;
  const sourceIssue = site?.state === 'attention' || (site && !site.setup_steps.graph_ready && !hasEvidence);
  return (
    <header className='space-y-2'>
      <div className='graph-panel rounded-2xl px-4 py-3 sm:px-5'>
        <div className='relative flex flex-wrap items-center justify-between gap-3'>
          <div className='min-w-0 w-full flex-[1_0_100%] sm:flex-1 sm:max-w-[75%]'>
            <div className='flex items-center gap-2 text-xs font-semibold text-teal-700 dark:text-teal-300'><IconTargetArrow className='size-4' /> نقشهٔ تصمیم / {site?.name ?? 'سایت انتخاب‌شده'}</div>
            <h1 className='mt-1 text-xl font-bold tracking-tight sm:text-2xl'>هر رابطه، یک تصمیم روشن</h1>
            <p className='mt-1 text-sm leading-6 text-muted-foreground'>هدف: {site?.mission.objective || 'هدف این سایت هنوز تعریف نشده است.'}</p>
            {site?.mission.success_metric && <p className='mt-0.5 text-xs leading-5 text-muted-foreground'>معیار موفقیت: {site.mission.success_metric}</p>}
          </div>
          <div className='flex flex-wrap items-center gap-2'>
            <span className={`rounded-full border px-3 py-1.5 text-xs ${sourceIssue ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300' : hasEvidence ? 'border-teal-600/30 bg-teal-500/10 text-teal-800 dark:text-teal-200' : 'border-border bg-muted text-muted-foreground'}`}>{sourceIssue ? 'منبع نیازمند بررسی' : hasEvidence ? 'دارای شواهد گراف' : 'در انتظار داده'}</span>
            <Link href={`/dashboard/sites/${encodeURIComponent(siteId)}`} className='inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted'>هدف و دادهٔ سایت <IconArrowLeft className='size-4' /></Link>
          </div>
        </div>
      </div>
      <nav className='graph-panel grid grid-cols-2 gap-1 rounded-2xl p-1 sm:grid-cols-4' aria-label='نماهای نقشه'>
        {LENSES.map((lens) => {
          const active = lens.key === mode;
          const Icon = lens.icon;
          return <button key={lens.key} type='button' aria-current={active ? 'page' : undefined} onClick={() => onModeChange(lens.key)} title={lens.detail} className={`group flex min-h-11 min-w-0 items-center justify-center gap-2 rounded-lg px-2 py-2 text-center transition-colors duration-200 ${active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
            <Icon className='size-4 shrink-0' aria-hidden='true' />
            <strong className='truncate text-xs sm:text-sm'>{lens.title}</strong>
          </button>;
        })}
      </nav>
      <div className='flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-muted-foreground'><p>{hasEvidence ? 'برای دیدن شواهد و اقدام، یک گره را انتخاب کنید.' : 'این نما بعد از دریافت دادهٔ واقعی سایت قابل بررسی است.'}</p><Link href={current.href(siteId)} className='inline-flex min-h-10 items-center gap-1 font-medium text-teal-700 hover:underline dark:text-teal-300'>رفتن به محل اقدام <IconArrowLeft className='size-4' /></Link></div>
    </header>
  );
}
