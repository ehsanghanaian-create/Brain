'use client';

import { Button } from '@/components/ui/button';
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import { Icons } from '@/components/icons';
import { ApiError } from '@/lib/api/client';
import type { ReactNode } from 'react';

/** Shared SaaS-style state blocks (Persian, RTL): empty / loading / error / inline stat. Use across pages for a consistent feel. */
export function EmptyState({ icon = 'sparkles', title, description, action, className = '' }: { icon?: keyof typeof Icons; title: string; description?: ReactNode; action?: ReactNode; className?: string }) {
  const Icon = Icons[icon] ?? Icons.sparkles;
  return (
    <Empty className={`border-dashed py-10 ${className}`}>
      <EmptyHeader>
        <EmptyMedia variant='icon'><Icon className='size-5' /></EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description && <EmptyDescription>{description}</EmptyDescription>}
      </EmptyHeader>
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  );
}

export function LoadingState({ label = 'در حال بارگذاری…', rows = 3, className = '' }: { label?: string; rows?: number; className?: string }) {
  return (
    <div role='status' aria-live='polite' className={`flex flex-col gap-2 ${className}`}>
      <div className='text-muted-foreground flex items-center gap-2 text-xs'><Spinner className='size-3.5' />{label}</div>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className='h-9 w-full' style={{ opacity: 1 - i * 0.2 }} />)}
    </div>
  );
}

export function ErrorState({ error, title = 'خطا', onRetry, className = '' }: { error: unknown; title?: string; onRetry?: () => void; className?: string }) {
  const e = error instanceof ApiError ? error : null;
  const msg = e ? e.message : error instanceof Error ? error.message : String(error ?? 'خطای ناشناخته');
  return (
    <div role='alert' className={`border-destructive/30 bg-destructive/5 text-destructive flex flex-wrap items-start gap-3 rounded-lg border p-3 text-sm ${className}`}>
      <Icons.warning className='mt-0.5 size-4 shrink-0' />
      <div className='min-w-0 flex-1'>
        <div className='font-medium'>{title}</div>
        <div className='opacity-90'>{msg}</div>
        {e && <div className='mt-0.5 text-[11px] opacity-70' dir='ltr'>{e.code} · HTTP {e.status || '—'} · {e.requestId}</div>}
      </div>
      {onRetry && <Button size='sm' variant='outline' onClick={onRetry}>تلاش مجدد</Button>}
    </div>
  );
}

export function StatChip({ label, value, hint, tone = 'default' }: { label: string; value: ReactNode; hint?: string; tone?: 'default' | 'good' | 'warn' | 'bad' }) {
  const color = tone === 'good' ? 'text-emerald-600' : tone === 'warn' ? 'text-amber-600' : tone === 'bad' ? 'text-red-600' : '';
  return (
    <div className='bg-card flex min-w-28 flex-col rounded-lg border px-3 py-2 text-xs' title={hint}>
      <span className='text-muted-foreground'>{label}</span>
      <span className={`text-base font-semibold tabular-nums ${color}`}>{value}</span>
    </div>
  );
}
