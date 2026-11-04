import type { GraphView } from '@/lib/api/client';
import { IconChartBar, IconGitBranch, IconLayersIntersect } from '@tabler/icons-react';
import { NODE_STYLE, RELATION_FA } from '../constants';

const fa = new Intl.NumberFormat('fa-IR');

export function GraphInsights({ view, loading }: { view: GraphView | null; loading: boolean }) {
  const allTypes = Object.entries(view?.stats.by_type ?? {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);
  const types = allTypes.slice(0, 5);
  const relations = Object.entries(view?.stats.by_relation ?? {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);
  const sampled = Boolean(view?.truncated || view?.stats.sampled || view?.stats.edges_truncated);
  const totalTypes = allTypes.reduce((sum, [, count]) => sum + count, 0);
  let position = 0;
  const ring = allTypes.map(([type, count]) => {
    const start = position;
    position += (count / Math.max(totalTypes, 1)) * 100;
    return `${NODE_STYLE[type]?.color ?? '#0d9488'} ${start}% ${position}%`;
  });

  return (
    <section className='grid min-w-0 gap-3 xl:grid-cols-3' aria-label='تحلیل نقشه از دادهٔ سایت'>
      <div className='graph-panel min-w-0 rounded-2xl p-4'>
        <div className='flex items-center justify-between gap-2 text-sm font-semibold'>
          <h2>اندازهٔ نقشه</h2><IconLayersIntersect className='size-4 text-teal-700 dark:text-teal-300' aria-hidden='true' />
        </div>
        <div className='mt-3 flex items-center gap-4'>
          <div
            className='relative grid size-[88px] shrink-0 place-items-center rounded-full p-[9px]'
            style={{ background: ring.length ? `conic-gradient(${ring.join(', ')})` : 'conic-gradient(var(--muted) 0% 100%)' }}
            role='img'
            aria-label={ring.length ? `ترکیب ${fa.format(totalTypes)} گره بر اساس نوع` : 'ترکیب گره‌ها در انتظار داده'}
          >
            <div className='grid size-full place-content-center rounded-full bg-card text-center'>
              <strong className='text-xl font-semibold tabular-nums leading-none'>{loading ? '…' : fa.format(view?.nodes.length ?? 0)}</strong>
              <span className='mt-1 text-xs text-muted-foreground'>گره در نما</span>
            </div>
          </div>
          <div className='min-w-0 space-y-2 text-sm'>
            <span className='flex items-center gap-1.5'><IconGitBranch className='size-4 shrink-0 text-teal-700 dark:text-teal-300' />{fa.format(view?.edges.length ?? 0)} رابطه</span>
            <span className='block text-xs text-muted-foreground'>{types[0] ? `بیشترین: ${NODE_STYLE[types[0][0]]?.fa ?? types[0][0]} (${fa.format(types[0][1])})` : 'در انتظار داده'}</span>
          </div>
        </div>
        <p className='mt-3 border-t border-border pt-2 text-xs leading-5 text-muted-foreground'>
          {sampled ? `نمای سبک‌شده از ${fa.format(view?.total_nodes ?? 0)} گره؛ شمارش مربوط به همین نماست.` : 'شمارش بر اساس دادهٔ فعلی گراف این سایت است.'}
        </p>
      </div>
      <div className='graph-panel min-w-0 rounded-2xl p-4'>
        <div className='mb-3 flex items-center justify-between gap-2'><h2 className='text-sm font-semibold'>ترکیب داده‌ها</h2><IconChartBar className='size-4 text-teal-700 dark:text-teal-300' aria-hidden='true' /></div>
        {types.length ? <div className='space-y-2.5'>{types.map(([type, count]) => (
          <div className='grid grid-cols-[minmax(80px,1fr)_minmax(48px,2fr)_38px] items-center gap-2 text-xs' key={type}>
            <span className='truncate' title={NODE_STYLE[type]?.fa ?? type}>{NODE_STYLE[type]?.fa ?? type}</span>
            <div className='h-2 overflow-hidden rounded-full bg-muted' role='img' aria-label={`${NODE_STYLE[type]?.fa ?? type}: ${fa.format(count)} گره`}>
              <div className='h-full rounded-full' style={{ width: `${Math.max(5, count / types[0][1] * 100)}%`, backgroundColor: NODE_STYLE[type]?.color ?? '#0d9488' }} />
            </div>
            <span className='text-left tabular-nums text-muted-foreground'>{fa.format(count)}</span>
          </div>
        ))}</div> : <p className='text-xs text-muted-foreground'>پس از بارگذاری گراف، نوع گره‌ها اینجا دیده می‌شود.</p>}
      </div>
      <div className='graph-panel min-w-0 rounded-2xl p-4'>
        <h2 className='mb-3 text-sm font-semibold'>مسیر رابطه‌ها</h2>
        {relations.length ? <div className='space-y-2.5'>{relations.map(([relation, count]) => (
          <div className='grid grid-cols-[minmax(92px,1fr)_minmax(48px,2fr)_38px] items-center gap-2 text-xs' key={relation}>
            <span className='truncate' title={RELATION_FA[relation] ?? relation}>{RELATION_FA[relation] ?? relation}</span>
            <div className='h-2 overflow-hidden rounded-full bg-muted' role='img' aria-label={`${RELATION_FA[relation] ?? relation}: ${fa.format(count)} رابطه`}>
              <div className='h-full rounded-full bg-teal-600' style={{ width: `${Math.max(5, count / relations[0][1] * 100)}%` }} />
            </div>
            <span className='text-left tabular-nums text-muted-foreground'>{fa.format(count)}</span>
          </div>
        ))}</div> : <p className='text-xs text-muted-foreground'>رابطه‌های ثبت‌شدهٔ همین نما نمایش داده می‌شوند.</p>}
      </div>
    </section>
  );
}
