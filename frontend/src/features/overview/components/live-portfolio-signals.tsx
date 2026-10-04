'use client';

import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Line, LineChart, ResponsiveContainer, Tooltip } from 'recharts';
import { endpoints, type PortfolioOverview } from '@/lib/api/client';

type Snapshot = { at: string; nodes: number; content: number; keywords: number };
const nf = new Intl.NumberFormat('fa-IR');
const getSnapshot = (data: PortfolioOverview): Snapshot => ({
  at: new Intl.DateTimeFormat('fa-IR', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tehran'
  }).format(new Date()),
  nodes: data.totals.graph_nodes,
  content: data.totals.content,
  keywords: data.totals.keywords
});
const metrics = [
  { key: 'nodes' as const, title: 'گره‌های گراف', color: 'var(--chart-1)' },
  { key: 'content' as const, title: 'موجودی محتوا', color: '#066fd1' },
  { key: 'keywords' as const, title: 'کلمات کلیدی', color: '#ae3ec9' }
];

export function LivePortfolioSignals({ initial }: { initial: PortfolioOverview }) {
  const [samples, setSamples] = useState<Snapshot[]>(() => [getSnapshot(initial)]);
  const [connected, setConnected] = useState(true);
  const reduced = useReducedMotion();
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      if (document.hidden) return;
      try {
        const data = await endpoints.portfolioOverview();
        if (active) {
          setSamples((old) => [...old, getSnapshot(data)].slice(-18));
          setConnected(true);
        }
      } catch {
        if (active) setConnected(false);
      }
    };
    const timer = window.setInterval(refresh, 20000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  const latest = samples.at(-1)!;
  return (
    <section
      aria-label='شاخص‌های زنده'
      className='rounded-xl border border-border bg-card p-4 shadow-sm'
    >
      <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
        <div>
          <h3 className='text-sm font-semibold'>نبض زندهٔ داشبورد</h3>
          <p className='text-muted-foreground text-xs'>
            نمونه‌برداری از دادهٔ واقعی هر ۲۰ ثانیه؛ نمودار فقط تاریخچهٔ همین نشست را نشان می‌دهد.
          </p>
        </div>
        <span
          className={`flex items-center gap-2 rounded-full px-2.5 py-1 text-xs ${connected ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'}`}
        >
          <motion.span
            animate={connected && !reduced ? { opacity: [1, 0.35, 1] } : undefined}
            transition={{ repeat: Infinity, duration: 2 }}
            className={`size-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-amber-500'}`}
          />
          {connected ? 'متصل' : 'در انتظار اتصال'}
        </span>
      </div>
      <div className='grid gap-3 md:grid-cols-3'>
        {metrics.map((metric) => (
          <div key={metric.key} className='rounded-lg border border-border/70 bg-muted/20 p-3'>
            <span className='text-muted-foreground text-xs'>{metric.title}</span>
            <div className='mt-1 flex items-end justify-between gap-3'>
              <strong className='text-xl tabular-nums'>{nf.format(latest[metric.key])}</strong>
              <div className='h-12 w-28'>
                <ResponsiveContainer width='100%' height='100%'>
                  <LineChart data={samples}>
                    <Tooltip
                      formatter={(value) => nf.format(Number(value))}
                      labelFormatter={(_, items) => items[0]?.payload?.at ?? ''}
                    />
                    <Line
                      type='monotone'
                      dataKey={metric.key}
                      stroke={metric.color}
                      strokeWidth={2.5}
                      dot={samples.length < 3}
                      isAnimationActive={!reduced}
                      animationDuration={650}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
