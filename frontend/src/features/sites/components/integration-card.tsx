'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { ReactNode } from 'react';

/**
 * Integration Center building blocks — one shared frame + the sync-section primitives every
 * integration card (WordPress · GSC · GA4) composes: counters grid, step progress, error list.
 */
export function IntegrationCard({ kind, title, badge, badgeVariant = 'outline', description, children }: {
  kind: string;
  title: string;
  badge: string;
  badgeVariant?: 'default' | 'secondary' | 'destructive' | 'outline';
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card data-testid={`integration-${kind}`}>
      <CardHeader>
        <CardTitle className='flex flex-wrap items-center justify-between gap-2'>
          <span>{title}</span>
          <Badge variant={badgeVariant}>{badge}</Badge>
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className='grid gap-3'>{children}</CardContent>
    </Card>
  );
}

export function SyncCounters({ kind, items }: { kind: string; items: { key: string; fa: string; value: number }[] }) {
  return (
    <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
      {items.map((c) => (
        <div key={c.key} className='rounded-md border p-2 text-center' data-testid={`${kind}-count-${c.key}`}>
          <div className='text-xl font-semibold' dir='ltr'>{c.value.toLocaleString('fa-IR')}</div>
          <div className='text-muted-foreground text-xs'>{c.fa}</div>
        </div>
      ))}
    </div>
  );
}

const DOT: Record<string, string> = {
  done: 'bg-emerald-500', failed: 'bg-red-500', running: 'bg-amber-500 animate-pulse', skipped: 'bg-slate-400'
};

export function SyncProgress({ kind, label, percent, rows }: {
  kind: string;
  label: ReactNode;
  percent: number;
  rows: { key: string; fa: string; status: string; info?: string }[];
}) {
  return (
    <div className='rounded-md border p-2 text-xs'>
      <div className='mb-1 flex items-center justify-between'>
        <span>{label}</span>
        <span dir='ltr'>{percent}%</span>
      </div>
      <div className='bg-muted h-1.5 w-full overflow-hidden rounded'>
        <div className='h-full bg-emerald-500 transition-all' style={{ width: `${percent}%` }} data-testid={`${kind}-progress`} />
      </div>
      <ul className='mt-2 grid gap-1 sm:grid-cols-2'>
        {rows.map((r) => (
          <li key={r.key} className='flex items-center gap-1'>
            <span className={`inline-block h-2 w-2 rounded-full ${DOT[r.status] ?? 'bg-slate-200'}`} />
            <span>{r.fa}</span>
            {r.info && <span className='text-muted-foreground truncate' dir='ltr' title={r.info}>· {r.info}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SyncErrors({ kind, errors }: { kind: string; errors: string[] }) {
  if (!errors.length) return null;
  return (
    <ul className='rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30' data-testid={`${kind}-errors`}>
      {errors.map((e, i) => <li key={i} dir='ltr'>{e}</li>)}
    </ul>
  );
}
