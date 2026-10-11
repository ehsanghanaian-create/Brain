'use client';

import type { SalesPath } from '@/lib/api/client';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const names = { product: 'محصول', category: 'دسته‌بندی', shop: 'فروشگاه' } as const;
const colors = { product: 'var(--chart-1)', category: 'var(--chart-2)', shop: 'var(--chart-3)' } as const;
const fa = new Intl.NumberFormat('fa-IR');

export function SalesTrend({ daily }: { daily: SalesPath['daily'] }) {
  return <div className='h-56 w-full' dir='ltr' role='img' aria-label='روند کلیک‌های مشاهده‌شده در جست‌وجوی گوگل برای صفحات محصول، دسته‌بندی و فروشگاه؛ جدول همان داده‌ها پایین نمودار است'>
    <ResponsiveContainer width='100%' height='100%'>
      <AreaChart data={daily} margin={{ top: 10, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke='var(--border)' strokeOpacity={0.55} />
        <XAxis dataKey='date' tickFormatter={(value) => String(value).slice(5).replace('-', '/')} tick={{ fontSize: 11 }} minTickGap={22} />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip labelFormatter={(value) => String(value)} formatter={(value, key) => [fa.format(Number(value)), `${names[key as keyof typeof names] ?? key} · کلیک مشاهده‌شده`]} />
        {(Object.keys(names) as (keyof typeof names)[]).map((key) => <Area key={key} type='monotone' dataKey={key} stackId='commercial' stroke={colors[key]} fill={colors[key]} fillOpacity={0.35} strokeWidth={2} isAnimationActive={false} />)}
      </AreaChart>
    </ResponsiveContainer>
  </div>;
}
