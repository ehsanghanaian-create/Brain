'use client';

import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { UserDateInput } from '@/components/user-date-input';
import { formatUserDate, formatUserDateTime, useDatePreference } from '@/lib/date-preference';
import { commandApi, type ProjectSummary, type WorkReport } from '../api';

const number = new Intl.NumberFormat('fa-IR');
const persianMonth = new Intl.DateTimeFormat('en-US-u-ca-persian', {
  timeZone: 'Asia/Tehran', year: 'numeric', month: 'numeric'
});
function jalaliMonthBounds(anchor: string) {
  const day = new Date(`${anchor}T12:00:00Z`);
  const key = persianMonth.format(day);
  const start = new Date(day);
  const end = new Date(day);
  for (let index = 0; index < 31; index++) {
    const previous = new Date(start); previous.setUTCDate(previous.getUTCDate() - 1);
    if (persianMonth.format(previous) !== key) break;
    start.setUTCDate(start.getUTCDate() - 1);
  }
  for (let index = 0; index < 32 && persianMonth.format(end) === key; index++) end.setUTCDate(end.getUTCDate() + 1);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}
export function WorkReportPanel({ projects }: { projects: ProjectSummary[] }) {
  const { calendar } = useDatePreference();
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const [anchor, setAnchor] = useState(() => new Date().toISOString().slice(0, 10));
  const [siteId, setSiteId] = useState('');
  const [userId, setUserId] = useState('');
  const [report, setReport] = useState<WorkReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    if (!anchor) return;
    setLoading(true);
    void commandApi.report(period, anchor, siteId || undefined, userId ? Number(userId) : undefined,
      period === 'month' && calendar === 'jalali' ? jalaliMonthBounds(anchor) : undefined)
      .then((result) => { if (active) { setReport(result); setError(''); } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'گزارش بارگیری نشد'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [period, anchor, siteId, userId, calendar]);
  const totals = report?.totals;
  return <div className='space-y-3' dir='rtl'>
    <Card><CardHeader><CardTitle>گزارش کار تیم</CardTitle><CardDescription>ساخت، تکمیل، ارجاع و زمان ثبت‌شده از تاریخچهٔ واقعی تسک‌ها محاسبه می‌شود. هفته از شنبه شروع می‌شود.</CardDescription></CardHeader>
      <CardContent className='flex flex-wrap items-end gap-2'>
        <label className='space-y-1 text-xs'>بازه<NativeSelect value={period} onChange={(event) => setPeriod(event.target.value as 'week' | 'month')}><NativeSelectOption value='week'>هفتگی</NativeSelectOption><NativeSelectOption value='month'>ماهانه ({calendar === 'jalali' ? 'ماه شمسی' : 'ماه میلادی'})</NativeSelectOption></NativeSelect></label>
        <label className='min-w-40 space-y-1 text-xs'>تاریخ در بازه<UserDateInput label='تاریخ گزارش' value={anchor} onChange={setAnchor} /></label>
        <label className='space-y-1 text-xs'>پروژه<NativeSelect value={siteId} onChange={(event) => setSiteId(event.target.value)}><NativeSelectOption value=''>همهٔ پروژه‌ها</NativeSelectOption>{projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}</NativeSelect></label>
        <label className='space-y-1 text-xs'>همکار<NativeSelect value={userId} onChange={(event) => setUserId(event.target.value)}><NativeSelectOption value=''>کل تیم</NativeSelectOption>{report?.people.map((person) => <NativeSelectOption key={person.id} value={String(person.id)}>{person.full_name}</NativeSelectOption>)}</NativeSelect></label>
      </CardContent></Card>
    {error && <p className='rounded-lg border border-rose-500/30 p-3 text-sm text-rose-600'>{error}</p>}
    {loading && <p className='text-muted-foreground p-3 text-sm'>در حال محاسبهٔ گزارش…</p>}
    {report && <>
      <p className='text-muted-foreground text-xs'>از {formatUserDate(report.start_day, calendar)} تا پیش از {formatUserDate(report.end_day, calendar)}</p>
      <div className='grid grid-cols-2 gap-2 md:grid-cols-4'>{([
        ['کار جدید', totals?.created], ['تکمیل‌شده', totals?.completed], ['ارجاع دوباره', totals?.handoffs],
        ['زمان ثبت‌شده', totals ? `${number.format(Math.round(totals.minutes / 60 * 10) / 10)} ساعت` : '۰'],
        ['گفت‌وگو', totals?.comments], ['ویرایش', totals?.updates], ['کار باز اکنون', totals?.open_now]
      ] as const).map(([label, value]) => <Card key={label}><CardContent className='p-3'><span className='text-muted-foreground block text-xs'>{label}</span><strong className='mt-1 block text-xl'>{typeof value === 'number' ? number.format(value) : value}</strong></CardContent></Card>)}</div>
      <div className='grid gap-3 lg:grid-cols-2'>
        <Card><CardHeader><CardTitle className='text-base'>روند روزانه</CardTitle></CardHeader><CardContent className='h-64' dir='ltr'>
          {report.daily.length ? <ResponsiveContainer width='100%' height='100%'><BarChart data={report.daily}><CartesianGrid strokeDasharray='3 3' opacity={.2} /><XAxis dataKey='day' tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey='created' name='ایجاد' fill='#0ea5e9' radius={[3, 3, 0, 0]} /><Bar dataKey='completed' name='تکمیل' fill='#10b981' radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer> : <p className='text-muted-foreground p-6 text-center text-sm'>فعالیتی در این بازه ثبت نشده است.</p>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle className='text-base'>کارکرد همکاران</CardTitle></CardHeader><CardContent className='max-h-64 overflow-auto'><table className='w-full text-right text-xs'><thead><tr className='border-b'><th className='p-2'>همکار</th><th>ساخته</th><th>تکمیل</th><th>ارجاع</th><th>ساعت</th></tr></thead><tbody>{report.by_person.map((row) => <tr key={row.user_id ?? 'system'} className='border-b'><td className='p-2'>{row.name}</td><td>{number.format(row.created)}</td><td>{number.format(row.completed)}</td><td>{number.format(row.handoffs)}</td><td>{number.format(Math.round(row.minutes / 60 * 10) / 10)}</td></tr>)}</tbody></table>{!report.by_person.length && <p className='text-muted-foreground p-3 text-xs'>داده‌ای موجود نیست.</p>}</CardContent></Card>
      </div>
      <div className='grid gap-3 lg:grid-cols-2'>
        <Card><CardHeader><CardTitle className='text-base'>پروژه‌ها</CardTitle></CardHeader><CardContent className='space-y-1'>{report.by_project.map((row) => <div key={row.site_id} className='flex items-center justify-between rounded-lg border p-2 text-xs'><span>{row.name || projects.find((project) => project.site_id === row.site_id)?.name || row.site_id}</span><span>ایجاد {number.format(row.created)} · تکمیل {number.format(row.completed)} · {number.format(Math.round(row.minutes / 60 * 10) / 10)} ساعت</span></div>)}{!report.by_project.length && <p className='text-muted-foreground text-xs'>داده‌ای موجود نیست.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle className='text-base'>کارهای تکمیل‌شده</CardTitle></CardHeader><CardContent className='max-h-72 space-y-1 overflow-auto'>{report.completed_tasks.map((task) => <div key={`${task.id}-${task.completed_at}`} className='rounded-lg border p-2 text-xs'><strong className='block'>{task.title}</strong><span className='text-muted-foreground'>{task.site_name} · {task.actor_name} · {formatUserDateTime(task.completed_at, calendar)}</span></div>)}{!report.completed_tasks.length && <p className='text-muted-foreground text-xs'>کاری در این بازه تکمیل نشده است.</p>}</CardContent></Card>
      </div>
    </>}
  </div>;
}
