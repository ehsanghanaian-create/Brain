'use client';

import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import type { GraphView, PortfolioSite } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { IconArrowLeft, IconChartDots3, IconFileSearch, IconLink, IconListCheck, IconTargetArrow } from '@tabler/icons-react';
import Link from 'next/link';
import type { ToolbarState } from './graph-toolbar';

const fa = new Intl.NumberFormat('fa-IR');
const LENSES = [
  { key: 'seo', title: 'کجا باید مشکل را رفع کنیم؟', detail: 'صفحه ← کوئری و یافته‌های سئو', evidence: 'PAGE', icon: IconFileSearch, action: 'پرونده‌های سئو', href: (id: string) => `/dashboard/sites/${encodeURIComponent(id)}?tab=issues` },
  { key: 'content', title: 'پوشش محتوایی چه شکلی است؟', detail: 'دسته ← صفحه، نوشته و موضوع', evidence: 'PAGE', icon: IconChartDots3, action: 'موجودی صفحات', href: (id: string) => `/dashboard/sites/${encodeURIComponent(id)}?tab=urls` },
  { key: 'links', title: 'کدام مسیر لینک داخلی ضعیف است؟', detail: 'صفحهٔ مبدأ ← صفحهٔ مقصد', evidence: 'LINKS_TO', icon: IconLink, action: 'فرصت‌های لینک', href: (id: string) => `/dashboard/internal-linking?site=${encodeURIComponent(id)}` },
  { key: 'planner', title: 'محتوا برای چه چیزی برنامه‌ریزی شده؟', detail: 'برنامه ← کلمه، اینتنت و مرحله', evidence: 'CONTENT_PLAN', icon: IconListCheck, action: 'برنامه‌ریز محتوا', href: (id: string) => `/dashboard/content-planner?site=${encodeURIComponent(id)}` }
] as const;

export function GraphMission({ site, siteId, mode, view, onModeChange }: {
  site: PortfolioSite | null;
  siteId: string;
  mode: ToolbarState['mode'];
  view: GraphView | null;
  onModeChange: (mode: ToolbarState['mode']) => void;
}) {
  const current = LENSES.find((lens) => lens.key === mode) ?? LENSES[0];
  const graphHasEvidence = view?.mode.key === mode && view.nodes.length > 0;
  const needsData = site && site.state !== 'ready' && !site.setup_steps.graph_ready && !graphHasEvidence;
  const action = needsData ? { href: `/dashboard/sites/${encodeURIComponent(siteId)}?tab=${site.state === 'attention' ? 'automation' : 'integrations'}`, label: 'تکمیل داده‌های سایت' } : { href: current.href(siteId), label: current.action };
  const salesObjective = site?.mission.objective.includes('فروش');
  const nextStep = graphHasEvidence ? salesObjective ? 'بررسی مسیر رشد فروش' : action.label : site?.next_action;
  return (
    <section className='space-y-3' aria-label='هدف و مسیر تحلیل سایت'>
      <div className='overflow-hidden rounded-2xl border border-sky-500/20 bg-gradient-to-l from-sky-500/[0.10] via-card to-violet-500/[0.06] p-4 shadow-sm sm:p-5'>
        <div className='flex flex-col justify-between gap-4 lg:flex-row lg:items-start'>
          <div className='min-w-0'>
            <span className='inline-flex items-center gap-1.5 text-xs font-semibold text-sky-700 dark:text-sky-300'><IconTargetArrow className='size-4' /> مسیر این سایت</span>
            <h2 className='mt-1 text-lg font-bold'>{site?.name ?? 'سایت انتخاب‌شده'}</h2>
            <p className='mt-2 max-w-3xl text-sm leading-6'>{site?.mission.objective || 'هنوز هدف کاری برای این سایت ثبت نشده است.'}</p>
            {site?.mission.success_metric && <p className='text-muted-foreground mt-1 text-xs'>معیار موفقیتِ تعریف‌شده: {site.mission.success_metric}</p>}
          </div>
          <Link href={`/dashboard/sites/${encodeURIComponent(siteId)}`} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'shrink-0 self-start')}>
            {site?.mission.objective ? 'ویرایش هدف' : 'تعریف هدف سایت'} <IconArrowLeft className='size-4' />
          </Link>
        </div>
        {site && <div className='mt-4 flex flex-wrap items-center gap-2 border-t border-border/60 pt-3 text-xs'>
          <Badge variant='secondary'>نقشه: {graphHasEvidence ? 'دارای شواهد قابل بررسی' : 'در انتظار شواهد این نما'}</Badge>
          {site.state !== 'ready' && <span className='text-muted-foreground'>پردازش پس‌زمینه: {site.state_reason}</span>}
          <span className='text-muted-foreground'>قدم بعدی: <strong className='text-foreground'>{nextStep}</strong></span>
        </div>}
      </div>
      {salesObjective && <Link href={`/dashboard/sales?site=${encodeURIComponent(siteId)}`} className='flex flex-wrap items-center justify-between gap-2 rounded-xl border border-primary/25 bg-primary/[0.05] px-4 py-3 text-sm font-medium transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'><span>برای هدف فروش، روند صفحات محصول و دسته‌بندی و اقدام‌های مرتبط را ببینید.</span><span className='inline-flex items-center gap-1 text-primary'>مسیر رشد فروش <IconArrowLeft className='size-4' /></span></Link>}
      <div>
        <div className='mb-2 flex flex-wrap items-baseline justify-between gap-2'><h3 className='text-sm font-semibold'>الان دنبال پاسخ کدام سؤال هستید؟</h3><p className='text-muted-foreground text-xs'>هر نما بخشی از داده‌های همین سایت را نشان می‌دهد.</p></div>
        <div className='grid gap-2 sm:grid-cols-2 2xl:grid-cols-4' role='tablist' aria-label='پرسش‌های گراف'>
          {LENSES.map((lens) => {
            const active = lens.key === mode;
            const Icon = lens.icon;
            return <button key={lens.key} type='button' role='tab' aria-selected={active} onClick={() => onModeChange(lens.key)}
              className={cn('group flex min-h-24 flex-col items-start rounded-xl border p-3 text-start transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', active ? 'border-sky-500/50 bg-sky-500/10 shadow-sm' : 'border-border/70 bg-card hover:border-sky-500/30 hover:bg-muted/30')}>
              <span className='flex w-full items-center justify-between gap-2'><Icon className={cn('size-4', active ? 'text-sky-600' : 'text-muted-foreground')} /><span className='text-muted-foreground text-[11px]'>{lens.key === 'seo' ? 'سئو' : lens.key === 'content' ? 'محتوا' : lens.key === 'links' ? 'لینک‌ها' : 'برنامه'}</span></span>
              <strong className='mt-2 text-xs leading-5'>{lens.title}</strong><span className='text-muted-foreground mt-1 text-[11px]'>{lens.detail}</span>
            </button>;
          })}
        </div>
      </div>
      <div className='flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3 text-sm'>
        <div><strong>{current.title}</strong><p className='text-muted-foreground mt-1 text-xs'>
          {view?.mode.key === mode ? view.nodes.length === 0 ? 'این نما هنوز داده ندارد؛ وضعیت اتصال و خزش سایت را بررسی کنید.' : `${fa.format(view.nodes.length)} گره و ${fa.format(view.edges.length)} رابطهٔ قابل پیگیری دیده می‌شود${view.truncated ? `؛ این نمونهٔ متصل از ${fa.format(view.total_nodes)} گره موجود انتخاب شده است` : ''}${view.stats.edges_truncated ? '؛ بخشی از رابطه‌ها برای روان ماندن نما پنهان شده‌اند' : ''}.` : 'در حال بارگذاری شواهد این نما…'}
        </p></div>
        <Link href={action.href} className={cn(buttonVariants({ size: 'sm' }), 'shrink-0')}>{action.label}<IconArrowLeft className='size-4' /></Link>
      </div>
    </section>
  );
}
