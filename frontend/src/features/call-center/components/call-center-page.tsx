'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { toast } from 'sonner';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Icons } from '@/components/icons';
import {
  endpoints,
  traffic,
  type Site,
  type TrafficCalls,
  type TrafficOverview
} from '@/lib/api/client';
import {
  callCenterApi,
  sourceLabel,
  statusLabel,
  outcomeLabel,
  confidenceLabel,
  type CallAnalytics,
  type CallImportResult,
  type CallWorkbookResult,
  type CallOutcome,
  type CallRecord,
  type CallSource,
  type CallStatus,
  type PanelUser,
  type SourceBasis,
  type SourceConfidence
} from '../api';

const number = new Intl.NumberFormat('fa-IR');
const dateTime = new Intl.DateTimeFormat('fa-IR', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Tehran'
});
const colors: Record<CallSource, string> = {
  seo: 'var(--chart-1)',
  ads: '#066fd1',
  direct: '#f59f00',
  referral: '#ae3ec9',
  unknown: '#9aa7b6'
};
const channels = Object.keys(sourceLabel) as CallSource[];
const localNow = () => new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Tehran' }).replace(' ', 'T').slice(0, 16);
const csvCell = (value: string | number | boolean | null | undefined) => {
  const raw = String(value ?? '');
  const safe = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replaceAll('"', '""')}"`;
};
const empty: CallAnalytics = {
  total: 0,
  by_source: { seo: 0, ads: 0, direct: 0, referral: 0, unknown: 0 },
  by_brand: [],
  by_model: [],
  by_region: [],
  by_status: { new: 0, follow_up: 0, resolved: 0, cancelled: 0, unreviewed: 0 },
  by_outcome: { pending: 0, qualified: 0, unqualified: 0, order: 0, lost: 0 },
  by_source_outcome: Object.fromEntries(channels.map((key) => [key, { total: 0, qualified: 0, orders: 0, order_value: 0, unknown_confidence: 0 }])) as CallAnalytics['by_source_outcome'],
  warranty: 0,
  daily: [],
  days: 30,
  undated: 0,
  future: 0,
  generated_at: ''
};
type Draft = {
  occurred_at: string;
  customer_name: string;
  phone: string;
  warranty: boolean;
  brand: string;
  model: string;
  region: string;
  issue: string;
  source: CallSource;
  source_basis: SourceBasis;
  source_note: string;
  campaign: string;
  status: CallStatus;
  outcome: CallOutcome;
  order_value: string;
  follow_up_at: string;
  source_confidence: SourceConfidence;
  operator_id: string;
  site_id: string;
};
const blank: Draft = {
  occurred_at: '',
  customer_name: '',
  phone: '',
  warranty: false,
  brand: '',
  model: '',
  region: '',
  issue: '',
  source: 'unknown',
  source_basis: 'manual',
  source_note: '',
  campaign: '',
  status: 'new',
  outcome: 'pending',
  order_value: '',
  follow_up_at: '',
  source_confidence: 'unknown',
  operator_id: '',
  site_id: ''
};

function Metric({
  title,
  value,
  caption,
  color,
  onClick
}: {
  title: string;
  value: number;
  caption: string;
  color: string;
  onClick?: () => void;
}) {
  return (
    <button
      type='button'
      onClick={onClick}
      disabled={!onClick}
      className='group relative overflow-hidden rounded-xl border border-border bg-card p-4 text-start shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md disabled:hover:translate-y-0'
    >
      <span className='absolute inset-x-0 top-0 h-0.5' style={{ backgroundColor: color }} />
      <span className='text-muted-foreground block text-xs font-medium'>{title}</span>
      <strong className='mt-2 block text-3xl font-bold tabular-nums' style={{ color }}>
        {number.format(value)}
      </strong>
      <span className='text-muted-foreground mt-2 block text-xs'>{caption}</span>
    </button>
  );
}

function LiveChart({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card className='overflow-hidden'>
      <CardHeader>
        <CardTitle className='text-base'>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className='h-64'>{children}</CardContent>
    </Card>
  );
}

export function CallCenterPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [users, setUsers] = useState<Pick<PanelUser, 'id' | 'full_name' | 'active'>[]>([]);
  const [records, setRecords] = useState<CallRecord[]>([]);
  const [recordTotal, setRecordTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [analytics, setAnalytics] = useState<CallAnalytics>(empty);
  const [detailAnalytics, setDetailAnalytics] = useState<CallAnalytics>(empty);
  const [webTraffic, setWebTraffic] = useState<TrafficOverview | null>(null);
  const [webCalls, setWebCalls] = useState<TrafficCalls | null>(null);
  const [siteId, setSiteId] = useState('');
  const [days, setDays] = useState(30);
  const [source, setSource] = useState<CallSource | ''>('');
  const [status, setStatus] = useState<CallStatus | ''>('');
  const [query, setQuery] = useState('');
  const [live, setLive] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>(blank);
  const [quick, setQuick] = useState({ occurred_at: '', customer_name: '', phone: '', brand: '', model: '', region: '', issue: '', warranty: false });
  const [quickSite, setQuickSite] = useState('');
  const [quickSaving, setQuickSaving] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importMapping, setImportMapping] = useState<Record<string, string>>({});
  const [importPreview, setImportPreview] = useState<CallImportResult | null>(null);
  const [workbookPreview, setWorkbookPreview] = useState<CallWorkbookResult | null>(null);
  const [importPreviewReady, setImportPreviewReady] = useState(false);
  const [importing, setImporting] = useState(false);
  useEffect(() => { setImportPreviewReady(false); }, [siteId]);
  const reduced = useReducedMotion();

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const [list, summary, focused] = await Promise.all([
          callCenterApi.calls({
            source,
            status,
            site_id: siteId,
            q: query,
            limit: 50,
            offset: page * 50
          }),
          callCenterApi.analytics(days, siteId || undefined),
          source
            ? callCenterApi.analytics(days, siteId || undefined, source)
            : Promise.resolve(null)
        ]);
        setRecords(list.items);
        setRecordTotal(list.total);
        setAnalytics(summary);
        setDetailAnalytics(focused ?? summary);
        setLastUpdated(new Date());
        setError('');
        if (siteId) {
          const [visits, clicks] = await Promise.allSettled([
            traffic.overview(siteId, days),
            traffic.calls(siteId, days)
          ]);
          setWebTraffic(visits.status === 'fulfilled' ? visits.value : null);
          setWebCalls(clicks.status === 'fulfilled' ? clicks.value : null);
        } else {
          setWebTraffic(null);
          setWebCalls(null);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [source, status, siteId, query, days, page]
  );
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    Promise.all([endpoints.sites(), callCenterApi.operators()])
      .then(([s, u]) => {
        setSites(s);
        setUsers(u.filter((x) => x.active));
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void load(true);
    }, 20000);
    return () => window.clearInterval(timer);
  }, [live, load]);

  const sourcePie = useMemo(
    () =>
      channels
        .filter((key) => analytics.by_source[key] > 0)
        .map((key) => ({
          name: sourceLabel[key],
          value: analytics.by_source[key],
          color: colors[key]
        })),
    [analytics]
  );
  const brandBars = useMemo(
    () => detailAnalytics.by_brand.slice(0, 7).map(([name, value]) => ({ name, value })),
    [detailAnalytics]
  );
  const regionBars = useMemo(
    () => detailAnalytics.by_region.slice(0, 7).map(([name, value]) => ({ name, value })),
    [detailAnalytics]
  );
  const sortedModels = useMemo(() => detailAnalytics.by_model.slice(0, 8), [detailAnalytics]);
  const chartDaily = useMemo(
    () => detailAnalytics.daily.map((row) => ({ ...row, label: row.date.slice(5) })),
    [detailAnalytics]
  );
  const webChannels = useMemo(
    () =>
      (webTraffic?.by_channel ?? []).map((item) => ({
        name:
          item.channel === 'organic'
            ? 'گوگل / ارگانیک'
            : item.channel === 'paid'
              ? 'تبلیغات'
              : item.channel,
        value: item.sessions
      })),
    [webTraffic]
  );

  async function saveCall(e: React.FormEvent) {
    e.preventDefault();
    if (!/[0-9۰-۹٠-٩]/.test(draft.phone)) {
      toast.error('شماره تماس الزامی است');
      return;
    }
    setSaving(true);
    try {
      const values: Partial<CallRecord> = {
        ...draft,
        occurred_at: draft.occurred_at ? new Date(draft.occurred_at).toISOString() : null,
        follow_up_at: draft.follow_up_at ? new Date(draft.follow_up_at).toISOString() : null,
        order_value: draft.outcome === 'order' && draft.order_value ? Number(draft.order_value) : null,
        operator_id: draft.operator_id ? Number(draft.operator_id) : null,
        site_id: draft.site_id || null
      };
      if (editingId !== null && records.find((row) => row.id === editingId)?.source === draft.source) delete values.source;
      if (editingId === null) await callCenterApi.addCall(values);
      else await callCenterApi.patchCall(editingId, values);
      setDraft(blank);
      setEditingId(null);
      setFormOpen(false);
      toast.success(editingId === null ? 'تماس ثبت شد' : 'تماس ویرایش شد');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }
  async function saveQuick(e: React.FormEvent) {
    e.preventDefault();
    if (!/[0-9۰-۹٠-٩]/.test(quick.phone)) {
      toast.error('شماره تماس الزامی است');
      return;
    }
    setQuickSaving(true);
    try {
      const row = await callCenterApi.addCall({ ...quick, site_id: quickSite || siteId || null,
        occurred_at: quick.occurred_at || localNow(),
        source: 'unknown' });
      setQuick({ occurred_at: localNow(), customer_name: '', phone: '', brand: '', model: '', region: '', issue: '', warranty: false });
      toast.success(row.auto_attributed ? `ثبت شد؛ منبع ${sourceLabel[row.source]} به‌صورت احتمالی تشخیص داده شد` : 'تماس ثبت شد؛ منبع هنوز نامشخص است');
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      setQuickSaving(false);
    }
  }
  async function update(id: number, patch: Partial<CallRecord>) {
    try {
      await callCenterApi.patchCall(id, patch);
      toast.success('تغییر ثبت شد');
      await load(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }
  async function exportCsv() {
    setExporting(true);
    try {
      const all: CallRecord[] = [];
      let offset = 0;
      while (true) {
        const batch = await callCenterApi.calls({
          source,
          status,
          site_id: siteId,
          q: query,
          limit: 500,
          offset
        });
        all.push(...batch.items);
        offset += batch.items.length;
        if (!batch.items.length || offset >= batch.total) break;
      }
      const headings = [
        'زمان تماس',
        'نام تماس‌گیرنده',
        'شماره تماس',
        'گارانتی',
        'برند',
        'مدل',
        'منطقه',
        'مشکل',
        'منبع',
        'مبنای تشخیص',
        'توضیح منبع',
        'کمپین',
        'وضعیت',
        'نتیجه',
        'ارزش سفارش',
        'زمان پیگیری',
        'اطمینان منبع',
        'اپراتور',
        'سایت'
      ];
      const rows = all.map((row) => [
        row.occurred_at,
        row.customer_name,
        row.phone,
        row.warranty ? 'بله' : 'خیر',
        row.brand,
        row.model,
        row.region,
        row.issue,
        sourceLabel[row.source],
        row.source_basis,
        row.source_note,
        row.campaign,
        statusLabel[row.status],
        outcomeLabel[row.outcome],
        row.order_value,
        row.follow_up_at,
        confidenceLabel[row.source_confidence],
        row.operator_name,
        row.site_id
      ]);
      const csv =
        '\uFEFF' + [headings, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n');
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `seo-brain-calls-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`${number.format(all.length)} تماس خروجی گرفته شد`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }

  async function runImport(dryRun: boolean) {
    if (!importFile || importing) return;
    setImporting(true);
    try {
      if (importFile.name.toLowerCase().endsWith('.xlsx')) {
        const result = await callCenterApi.importWorkbook(importFile, dryRun, siteId || undefined);
        setWorkbookPreview(result);
        if (dryRun) {
          setImportPreviewReady(true);
          toast.info(`پیش‌نمایش ${number.format(result.rows_valid)} تماس آماده شد`);
        } else {
          toast.success(`${number.format(result.rows_imported)} تماس وارد شد؛ ${number.format(result.rows_skipped)} تکراری بود`);
          await load();
        }
        return;
      }
      const result = await callCenterApi.importCalls(importFile, importMapping, dryRun, siteId || undefined);
      setImportPreview(result);
      if (dryRun) {
        setImportPreviewReady(true);
        setImportMapping(Object.fromEntries(Object.entries(result.mapping).filter(([, value]) => value)) as Record<string, string>);
        toast.info(`پیش‌نمایش ${number.format(result.rows_valid)} ردیف معتبر آماده شد`);
      } else {
        toast.success(`${number.format(result.rows_imported)} تماس وارد شد؛ ${number.format(result.rows_skipped)} تکراری بود`);
        await load();
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  }
  function beginEdit(row: CallRecord) {
    setDraft({
      occurred_at: row.occurred_at
        ? new Date(row.occurred_at)
            .toLocaleString('sv-SE', { timeZone: 'Asia/Tehran' })
            .replace(' ', 'T')
            .slice(0, 16)
        : '',
      customer_name: row.customer_name,
      phone: row.phone,
      warranty: row.warranty,
      brand: row.brand,
      model: row.model,
      region: row.region,
      issue: row.issue,
      source: row.source,
      source_basis: row.source_basis,
      source_note: row.source_note,
      campaign: row.campaign,
      status: row.status,
      outcome: row.outcome,
      order_value: row.order_value?.toString() || '',
      follow_up_at: row.follow_up_at ? new Date(row.follow_up_at).toLocaleString('sv-SE', { timeZone: 'Asia/Tehran' }).replace(' ', 'T').slice(0, 16) : '',
      source_confidence: row.source_confidence,
      operator_id: row.operator_id ? String(row.operator_id) : '',
      site_id: row.site_id || ''
    });
    setEditingId(row.id);
    setFormOpen(true);
    window.requestAnimationFrame(() =>
      document
        .getElementById('call-entry-form')
        ?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' })
    );
  }
  const field = (key: keyof Draft, value: string | boolean) =>
    setDraft((old) => ({ ...old, [key]: value }));
  const chartAnimation = !reduced;

  return (
    <div className='space-y-5'>
      <section className='relative overflow-hidden rounded-2xl border border-[#1abb9c]/20 bg-[linear-gradient(120deg,#1a2332,#26394a)] p-5 text-white shadow-md'>
        <div
          className='absolute -top-24 -left-16 size-64 rounded-full bg-[#1abb9c]/20 blur-3xl'
          aria-hidden='true'
        />
        <div className='relative flex flex-wrap items-center justify-between gap-4'>
          <div>
            <div className='mb-2 flex items-center gap-2 text-xs text-[#9be5d4]'>
              <span className={`size-2 rounded-full bg-[#1abb9c] ${live ? 'animate-pulse' : ''}`} />
              {live ? 'پایش زنده · هر ۲۰ ثانیه' : 'پایش متوقف است'}
              {lastUpdated && (
                <span className='text-white/60'>آخرین دریافت: {dateTime.format(lastUpdated)}</span>
              )}
            </div>
            <h2 className='text-2xl font-bold'>فرماندهی تماس‌ها</h2>
            <p className='mt-1 text-sm text-white/65'>
              تماس واقعی را سریع ثبت کنید؛ سیستم منبع را از شواهد کلیک پیشنهاد می‌دهد و اپراتور می‌تواند اصلاح کند.
            </p>
          </div>
          <div className='flex flex-wrap gap-2'>
            <Button
              variant='outline'
              onClick={() => setLive((v) => !v)}
              className='border-white/25 bg-white/5 text-white hover:bg-white/15'
            >
              {live ? 'توقف پایش' : 'شروع پایش'}
            </Button>
            <Button
              onClick={() => {
                setQuick((current) => ({ ...current, occurred_at: current.occurred_at || localNow() }));
                document.getElementById('quick-call-entry')?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'center' });
              }}
              className='bg-[#1abb9c] text-white hover:bg-[#169f85]'
            >
              <Icons.add className='size-4' /> ثبت سریع در جدول
            </Button>
          </div>
        </div>
      </section>

      <div className='flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3 shadow-sm'>
        <NativeSelect
          value={siteId}
          onChange={(e) => {
            setSiteId(e.target.value);
            setPage(0);
          }}
          aria-label='سایت'
          className='w-44'
        >
          <NativeSelectOption value=''>همه سایت‌ها</NativeSelectOption>
          {sites.map((s) => (
            <NativeSelectOption key={s.site_id} value={s.site_id}>
              {s.name}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          aria-label='بازه زمانی'
          className='w-32'
        >
          {[7, 30, 90, 180].map((d) => (
            <NativeSelectOption key={d} value={d}>
              {number.format(d)} روز
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={source}
          onChange={(e) => {
            setSource(e.target.value as CallSource | '');
            setPage(0);
          }}
          aria-label='فیلتر منبع'
          className='w-32'
        >
          <NativeSelectOption value=''>همه منابع</NativeSelectOption>
          {channels.map((key) => (
            <NativeSelectOption key={key} value={key}>
              {sourceLabel[key]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as CallStatus | '');
            setPage(0);
          }}
          aria-label='فیلتر وضعیت'
          className='w-32'
        >
          <NativeSelectOption value=''>همه وضعیت‌ها</NativeSelectOption>
          {Object.entries(statusLabel).map(([key, label]) => (
            <NativeSelectOption key={key} value={key}>
              {label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <Input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          aria-label='جست‌وجوی تماس'
          placeholder='جست‌وجوی نام، تلفن، مدل یا منطقه'
          className='min-w-48 flex-1'
        />
        <Button variant='outline' onClick={() => load()} disabled={loading}>
          <Icons.spinner className={`size-4 ${loading ? 'animate-spin' : ''}`} /> تازه‌سازی
        </Button>
        <Button variant='outline' onClick={exportCsv} disabled={exporting}>
          {exporting ? 'در حال خروجی…' : 'خروجی CSV'}
        </Button>
        <Button variant='outline' onClick={() => setImportOpen((value) => !value)} aria-expanded={importOpen}>ورود فایل تماس‌ها</Button>
      </div>

      {importOpen && <Card className='border-border/70'><CardHeader><CardTitle className='text-base'>ورود دادهٔ تماس‌ها</CardTitle><CardDescription>فایل XLSX شیت کال‌سنتر یا CSV را انتخاب کنید و پیش از ثبت، ردیف‌ها را بررسی کنید. منبع نامشخص خودکار به سئو یا ادز نسبت داده نمی‌شود.</CardDescription></CardHeader><CardContent className='space-y-4'>
        <div className='flex flex-wrap items-center gap-2'><Input type='file' accept='.csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' aria-label='فایل CSV یا XLSX تماس‌ها' className='max-w-sm' onChange={(event) => { setImportFile(event.target.files?.[0] ?? null); setImportMapping({}); setImportPreview(null); setWorkbookPreview(null); setImportPreviewReady(false); }} /><Button onClick={() => runImport(true)} disabled={!importFile || importing}>{importing ? 'در حال بررسی…' : 'پیش‌نمایش و اعتبارسنجی'}</Button></div>
        {workbookPreview && <div className='space-y-3'>
          <p className='text-sm'>این فایل {number.format(workbookPreview.rows_valid)} تماس دارد. منبع همهٔ تماس‌ها «نامشخص» ثبت می‌شود؛ فایل ستونی برای تشخیص سئو یا ادز ندارد.</p>
          {Object.values(workbookPreview.sheets).some((count) => count.missing_phone > 0) && <p role='alert' className='text-xs text-amber-500'>ردیف‌های بدون شماره تماس در ورود فایل نادیده گرفته می‌شوند.</p>}
          <div className='overflow-x-auto'><table className='w-full min-w-[690px] text-right text-xs'><thead><tr className='border-b text-muted-foreground'><th className='py-2'>تب</th><th>تماس معتبر</th><th>تکراری</th><th>ردیف تغییرکرده</th><th>بدون تاریخ</th><th>شماره کوتاه</th><th>کنسل‌شده</th></tr></thead><tbody>{Object.entries(workbookPreview.sheets).map(([name, count]) => <tr key={name} className='border-b last:border-0'><td className='py-2 font-medium'>{name}</td><td>{number.format(count.valid)}</td><td>{number.format(count.skipped_existing)}</td><td>{number.format(count.changed_rows)}</td><td>{number.format(count.missing_date)}</td><td>{number.format(count.short_phone)}</td><td>{number.format(count.cancelled)}</td></tr>)}</tbody></table></div>
          {workbookPreview.rows_changed > 0 && <p role='alert' className='rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-xs'>محتوای {number.format(workbookPreview.rows_changed)} ردیف نسبت به ورود قبلی تغییر کرده است. برای جلوگیری از بازنویسی اصلاحات اپراتور، این ردیف‌ها خودکار به‌روزرسانی نمی‌شوند.</p>}
          <Button onClick={() => runImport(false)} disabled={!importPreviewReady || !workbookPreview.dry_run || workbookPreview.rows_valid <= workbookPreview.rows_skipped + workbookPreview.rows_changed || importing}>ثبت {number.format(Math.max(0, workbookPreview.rows_valid - workbookPreview.rows_skipped - workbookPreview.rows_changed))} تماس جدید</Button>
        </div>}
        {importPreview && <>
          <div className='flex flex-wrap gap-2 text-xs'><Badge variant='secondary'>{number.format(importPreview.rows_total)} ردیف</Badge><Badge variant='outline'>{number.format(importPreview.rows_valid)} معتبر</Badge><Badge variant='outline'>{number.format(importPreview.rows_skipped)} تکراری</Badge><Badge variant={importPreview.errors_count ? 'destructive' : 'outline'}>{number.format(importPreview.errors_count)} خطا</Badge></div>
          <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-4'>{([['phone', 'شماره تماس'], ['customer_name', 'نام مشتری'], ['occurred_at', 'زمان تماس'], ['source', 'منبع تماس'], ['site_id', 'سایت'], ['region', 'منطقه'], ['brand', 'برند'], ['model', 'مدل'], ['issue', 'مشکل'], ['outcome', 'نتیجه'], ['order_value', 'ارزش سفارش'], ['status', 'وضعیت']] as const).map(([field, label]) => <label key={field} className='text-xs'><span className='mb-1 block text-muted-foreground'>{label}</span><NativeSelect value={importMapping[field] ?? ''} onChange={(event) => { setImportMapping((current) => { const next = { ...current }; if (event.target.value) next[field] = event.target.value; else delete next[field]; return next; }); setImportPreviewReady(false); }} aria-label={`ستون ${label}`}><NativeSelectOption value=''>نگاشت نشده</NativeSelectOption>{importPreview.columns.map((column) => <NativeSelectOption key={column} value={column}>{column}</NativeSelectOption>)}</NativeSelect></label>)}</div>
          <div className='overflow-x-auto'><table className='w-full min-w-[520px] text-right text-xs'><thead><tr className='border-b text-muted-foreground'><th className='py-2'>نام</th><th>تلفن</th><th>منبع</th><th>منطقه</th><th>نتیجه</th></tr></thead><tbody>{importPreview.preview.map((row, index) => <tr key={index} className='border-b last:border-0'><td className='py-2'>{row.customer_name || '—'}</td><td dir='ltr'>{row.phone || '—'}</td><td>{sourceLabel[row.source]}</td><td>{row.region || '—'}</td><td>{outcomeLabel[row.outcome]}</td></tr>)}</tbody></table></div>
          {importPreview.errors.length > 0 && <div role='alert' className='rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs'><strong>خطاهای نمونه:</strong>{importPreview.errors.slice(0, 5).map((item) => <p key={item.row}>ردیف {number.format(item.row)}: {item.error}</p>)}</div>}
          {!importPreviewReady && <p className='text-amber-700 text-xs'>نگاشت تغییر کرده است؛ پیش‌نمایش را دوباره اجرا کنید.</p>}
          <Button onClick={() => runImport(false)} disabled={!importPreviewReady || !importPreview.dry_run || importPreview.rows_valid <= importPreview.rows_skipped || importing}>ثبت {number.format(Math.max(0, importPreview.rows_valid - importPreview.rows_skipped))} ردیف معتبر</Button>
        </>}
        <p className='text-muted-foreground text-xs'>CSV: حداکثر ۱۰۰۰ ردیف و ۲ مگابایت، تاریخ میلادی ISO. XLSX شیت معرفی‌شده: حداکثر ۵ مگابایت، تب‌های گارانتی و غیر گارانتی. ردیف‌های تکراری دوباره ثبت نمی‌شوند.</p>
      </CardContent></Card>}

      {error && (
        <div
          role='alert'
          className='border-destructive/30 bg-destructive/10 text-destructive rounded-xl border p-4 text-sm'
        >
          {error}
        </div>
      )}
      <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-5'>
        <Metric
          title='کل تماس‌های ثبت‌شده'
          value={analytics.total}
          caption={`در ${number.format(days)} روز گذشته`}
          color='#1e2633'
        />
        <Metric
          title='تماس‌های سئو'
          value={analytics.by_source.seo}
          caption='انتساب خودکار احتمالی یا انتخاب اپراتور'
          color={colors.seo}
          onClick={() => {
            setSource('seo');
            setPage(0);
          }}
        />
        <Metric
          title='تماس‌های ادز'
          value={analytics.by_source.ads}
          caption='مجزا از ورودی ارگانیک'
          color={colors.ads}
          onClick={() => {
            setSource('ads');
            setPage(0);
          }}
        />
        <Metric
          title='منبع نامشخص'
          value={analytics.by_source.unknown}
          caption='نیازمند تعیین منبع'
          color={colors.unknown}
          onClick={() => {
            setSource('unknown');
            setPage(0);
          }}
        />
        <Metric
          title='نیازمند پیگیری'
          value={analytics.by_status.follow_up}
          caption={`${number.format(analytics.by_status.cancelled)} تماس کنسل شده`}
          color='#f59f00'
          onClick={() => {
            setStatus('follow_up');
            setPage(0);
          }}
        />
      </div>

      <div className='grid gap-3 lg:grid-cols-2'>
        {(['seo', 'ads'] as const).map((channel) => {
          const flow = analytics.by_source_outcome[channel];
          return <Card key={channel}><CardHeader><CardTitle className='text-base'>قیف تماس {sourceLabel[channel]}</CardTitle>
            <CardDescription>تماس واقعی ← سرنخ واجدکیفیت ← سفارش؛ بر اساس نتیجهٔ ثبت‌شده توسط اپراتور.</CardDescription></CardHeader>
            <CardContent className='space-y-3'>
              {([['تماس', flow.total], ['واجدکیفیت', flow.qualified], ['سفارش', flow.orders]] as const).map(([label, value]) =>
                <div key={label} className='space-y-1'><div className='flex justify-between text-xs'><span>{label}</span><strong>{number.format(value)}</strong></div>
                  <div className='h-2 overflow-hidden rounded-full bg-muted'><motion.div initial={false}
                    animate={{ width: `${flow.total ? Math.max(2, value / flow.total * 100) : 0}%` }}
                    transition={reduced ? { duration: 0 } : { duration: 0.7 }}
                    className='h-full rounded-full' style={{ backgroundColor: colors[channel] }} /></div></div>)}
              <div className='text-muted-foreground flex justify-between border-t pt-2 text-xs'>
                <span>ارزش سفارش‌های ثبت‌شده: {number.format(flow.order_value)}</span>
                <span>اطمینان نامشخص: {number.format(flow.unknown_confidence)}</span>
              </div>
            </CardContent></Card>;
        })}
      </div>

      {siteId && (
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>ورودی وب این سایت</CardTitle>
            <CardDescription>
              دادهٔ ترکر سایت؛ برای مقایسه کنار تماس‌های ثبت‌شده نمایش داده می‌شود و به‌تنهایی تماس واقعی
              را اثبات نمی‌کند.
            </CardDescription>
          </CardHeader>
          <CardContent className='grid gap-4 lg:grid-cols-[1fr_1fr]'>
            <div className='grid grid-cols-2 gap-3 text-sm'>
              <div className='rounded-lg bg-[#1abb9c]/10 p-3'>
                <span className='text-muted-foreground block text-xs'>جلسه‌های ارگانیک</span>
                <strong className='text-xl text-[#1abb9c]'>
                  {number.format(
                    webTraffic?.by_channel.find((x) => x.channel === 'organic')?.sessions ?? 0
                  )}
                </strong>
              </div>
              <div className='rounded-lg bg-[#066fd1]/10 p-3'>
                <span className='text-muted-foreground block text-xs'>جلسه‌های تبلیغاتی</span>
                <strong className='text-xl text-[#066fd1]'>
                  {number.format(
                    webTraffic?.by_channel.find((x) => x.channel === 'paid')?.sessions ?? 0
                  )}
                </strong>
              </div>
              <div className='rounded-lg bg-muted p-3'>
                <span className='text-muted-foreground block text-xs'>کلیک روی شماره</span>
                <strong className='text-xl'>{number.format(webCalls?.total ?? 0)}</strong>
              </div>
              <div className='rounded-lg bg-muted p-3'>
                <span className='text-muted-foreground block text-xs'>تماس ثبت‌شده</span>
                <strong className='text-xl'>{number.format(analytics.total)}</strong>
              </div>
            </div>
            <div className='h-44'>
              <ResponsiveContainer width='100%' height='100%'>
                <BarChart data={webChannels} layout='vertical'>
                  <XAxis type='number' allowDecimals={false} />
                  <YAxis type='category' dataKey='name' width={100} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(value) => number.format(Number(value))} />
                  <Bar
                    dataKey='value'
                    fill='#1abb9c'
                    radius={[4, 4, 4, 4]}
                    isAnimationActive={chartAnimation}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      <div className='flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2 text-xs'>
        <span>
          تحلیل روند، برند، منطقه و مدل برای:{' '}
          <strong className='text-primary'>{source ? sourceLabel[source] : 'همهٔ منابع'}</strong>
        </span>
        {source && (
          <Button
            variant='ghost'
            size='sm'
            onClick={() => {
              setSource('');
              setPage(0);
            }}
          >
            نمایش همه
          </Button>
        )}
      </div>
      <div className='grid gap-4 xl:grid-cols-[1.5fr_1fr]'>
        <LiveChart
          title='روند تماس‌ها بر اساس منبع'
          description='هر نقطه یک روز است؛ با ثبت یا ویرایش تماس نمودار به‌روزرسانی می‌شود.'
        >
          {chartDaily.length ? (
            <ResponsiveContainer width='100%' height='100%'>
              <AreaChart data={chartDaily} margin={{ top: 8, right: 2, left: -24, bottom: 0 }}>
                <defs>
                  {(['seo', 'ads', 'unknown'] as const).map((key) => (
                    <linearGradient key={key} id={`fill-${key}`} x1='0' x2='0' y1='0' y2='1'>
                      <stop offset='0%' stopColor={colors[key]} stopOpacity={0.28} />
                      <stop offset='95%' stopColor={colors[key]} stopOpacity={0.01} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray='4 6' vertical={false} opacity={0.28} />
                <XAxis dataKey='label' tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value, name) => [
                    number.format(Number(value)),
                    sourceLabel[name as CallSource] ?? name
                  ]}
                />
                <Area
                  type='monotone'
                  dataKey='seo'
                  stroke={colors.seo}
                  strokeWidth={3}
                  fill='url(#fill-seo)'
                  isAnimationActive={chartAnimation}
                  animationDuration={850}
                />
                <Area
                  type='monotone'
                  dataKey='ads'
                  stroke={colors.ads}
                  strokeWidth={3}
                  fill='url(#fill-ads)'
                  isAnimationActive={chartAnimation}
                  animationDuration={1000}
                />
                <Area
                  type='monotone'
                  dataKey='unknown'
                  stroke={colors.unknown}
                  strokeWidth={2}
                  fill='url(#fill-unknown)'
                  isAnimationActive={chartAnimation}
                  animationDuration={1150}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className='text-muted-foreground flex h-full items-center justify-center text-sm'>
              در این بازه تماسی ثبت نشده است.
            </div>
          )}
        </LiveChart>
        <LiveChart
          title='سهم کانال‌ها'
          description='درصد هر کانال از تماس‌های ثبت‌شده، نه کلیک روی شماره تماس.'
        >
          {sourcePie.length ? (
            <ResponsiveContainer width='100%' height='100%'>
              <PieChart>
                <Pie
                  data={sourcePie}
                  dataKey='value'
                  nameKey='name'
                  innerRadius='53%'
                  outerRadius='78%'
                  paddingAngle={3}
                  isAnimationActive={chartAnimation}
                  animationDuration={900}
                >
                  {sourcePie.map((item) => (
                    <Cell key={item.name} fill={item.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => number.format(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className='text-muted-foreground flex h-full items-center justify-center text-sm'>
              داده‌ای برای این بازه ثبت نشده است.
            </div>
          )}
        </LiveChart>
        <LiveChart title='برندهای پرتکرار' description='شمار تماس به تفکیک برند خودرو.'>
          {brandBars.length ? (
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart
                data={brandBars}
                layout='vertical'
                margin={{ top: 4, right: 10, left: 8, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray='4 6' horizontal={false} opacity={0.25} />
                <XAxis type='number' allowDecimals={false} tick={{ fontSize: 11 }} />
                <YAxis type='category' dataKey='name' width={90} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value) => number.format(Number(value))} />
                <Bar
                  dataKey='value'
                  fill='#1abb9c'
                  radius={[4, 4, 4, 4]}
                  isAnimationActive={chartAnimation}
                  animationDuration={900}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className='text-muted-foreground flex h-full items-center justify-center text-sm'>
              داده‌ای برای این بخش ثبت نشده است.
            </div>
          )}
        </LiveChart>
        <LiveChart
          title='مناطق پرتکرار'
          description='تمرکز جغرافیایی درخواست‌ها؛ برای شیت گارانتی منطقهٔ خالی شمرده نمی‌شود.'
        >
          {regionBars.length ? (
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart data={regionBars} margin={{ top: 6, right: 4, left: -22, bottom: 0 }}>
                <CartesianGrid strokeDasharray='4 6' vertical={false} opacity={0.25} />
                <XAxis
                  dataKey='name'
                  tick={{ fontSize: 10 }}
                  interval={0}
                  angle={-18}
                  textAnchor='end'
                  height={46}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value) => number.format(Number(value))} />
                <Bar
                  dataKey='value'
                  fill='#066fd1'
                  radius={[5, 5, 0, 0]}
                  isAnimationActive={chartAnimation}
                  animationDuration={1050}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className='text-muted-foreground flex h-full items-center justify-center text-sm'>
              داده‌ای برای این بخش ثبت نشده است.
            </div>
          )}
        </LiveChart>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>مدل‌های پرتکرار</CardTitle>
          <CardDescription>برای برنامه‌ریزی محتوا و کمپین بر اساس تقاضای تماس.</CardDescription>
        </CardHeader>
        <CardContent className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
          {sortedModels.map(([name, count]) => (
            <div key={name} className='rounded-lg border border-border/70 p-3'>
              <div className='flex justify-between gap-2 text-sm'>
                <span className='truncate'>{name}</span>
                <strong>{number.format(count)}</strong>
              </div>
              <div className='bg-muted mt-2 h-1.5 overflow-hidden rounded-full'>
                <motion.div
                  initial={reduced ? false : { width: 0 }}
                  animate={{
                    width: `${Math.max(5, (count / (sortedModels[0]?.[1] || 1)) * 100)}%`
                  }}
                  transition={{ duration: 0.75 }}
                  className='h-full rounded-full bg-[#ae3ec9]'
                />
              </div>
            </div>
          ))}
          {!sortedModels.length && (
            <p className='text-muted-foreground text-sm'>هنوز مدلی ثبت نشده است.</p>
          )}
        </CardContent>
      </Card>

      {formOpen && editingId !== null && (
        <motion.section
          id='call-entry-form'
          initial={reduced ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className='scroll-mt-8 rounded-xl border border-primary/30 bg-card p-4 shadow-md'
          aria-label='فرم تماس'
        >
          <form onSubmit={saveCall} className='space-y-4'>
            <div className='flex items-center justify-between'>
              <h3 className='font-semibold'>
                {editingId === null ? 'ثبت تماس جدید' : `ویرایش تماس ${number.format(editingId)}`}
              </h3>
              <Button
                variant='ghost'
                type='button'
                onClick={() => {
                  setFormOpen(false);
                  setEditingId(null);
                }}
              >
                بستن
              </Button>
            </div>
            <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-4'>
              <label htmlFor='call-occurred-at' className='space-y-1 text-xs'>
                زمان تماس
                <Input
                  id='call-occurred-at'
                  type='datetime-local'
                  value={draft.occurred_at}
                  onChange={(e) => field('occurred_at', e.target.value)}
                  dir='ltr'
                />
                <span className='text-muted-foreground block text-[10px]'>
                  خالی = اکنون؛ در ویرایش خالی = زمان نامشخص
                </span>
              </label>
              <label htmlFor='call-customer-name' className='space-y-1 text-xs'>
                نام تماس‌گیرنده
                <Input
                  id='call-customer-name'
                  value={draft.customer_name}
                  onChange={(e) => field('customer_name', e.target.value)}
                  placeholder='اختیاری'
                />
              </label>
              <label htmlFor='call-phone' className='space-y-1 text-xs'>
                شماره تماس *
                <Input
                  id='call-phone'
                  required
                  value={draft.phone}
                  onChange={(e) => field('phone', e.target.value)}
                  dir='ltr'
                  inputMode='tel'
                  placeholder='09…'
                />
              </label>
              <label htmlFor='call-brand' className='space-y-1 text-xs'>
                برند خودرو
                <Input
                  id='call-brand'
                  value={draft.brand}
                  onChange={(e) => field('brand', e.target.value)}
                  placeholder='مثلاً مدیران'
                />
              </label>
              <label htmlFor='call-model' className='space-y-1 text-xs'>
                مدل خودرو
                <Input
                  id='call-model'
                  value={draft.model}
                  onChange={(e) => field('model', e.target.value)}
                  placeholder='مثلاً X22'
                />
              </label>
              <label htmlFor='call-region' className='space-y-1 text-xs'>
                منطقه
                <Input
                  id='call-region'
                  value={draft.region}
                  onChange={(e) => field('region', e.target.value)}
                  placeholder='محله یا شهر'
                />
              </label>
              <label htmlFor='call-source' className='space-y-1 text-xs'>
                منبع تماس
                <NativeSelect
                  id='call-source'
                  value={draft.source}
                  onChange={(e) => field('source', e.target.value)}
                >
                  {channels.map((key) => (
                    <NativeSelectOption key={key} value={key}>
                      {sourceLabel[key]}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
              <label htmlFor='call-source-basis' className='space-y-1 text-xs'>
                مبنای تشخیص
                <NativeSelect
                  id='call-source-basis'
                  value={draft.source_basis}
                  onChange={(e) => field('source_basis', e.target.value)}
                >
                  <NativeSelectOption value='manual'>انتخاب اپراتور</NativeSelectOption>
                  <NativeSelectOption value='customer'>اظهار تماس‌گیرنده</NativeSelectOption>
                  <NativeSelectOption value='gclid'>شناسه GCLID</NativeSelectOption>
                  <NativeSelectOption value='utm'>پارامتر UTM</NativeSelectOption>
                  {draft.source_basis === 'import' && (
                    <NativeSelectOption value='import'>واردشده از شیت</NativeSelectOption>
                  )}
                </NativeSelect>
              </label>
              <label htmlFor='call-operator' className='space-y-1 text-xs'>
                اپراتور
                <NativeSelect
                  id='call-operator'
                  value={draft.operator_id}
                  onChange={(e) => field('operator_id', e.target.value)}
                >
                  <NativeSelectOption value=''>ثبت‌کننده نامشخص</NativeSelectOption>
                  {users.map((u) => (
                    <NativeSelectOption key={u.id} value={u.id}>
                      {u.full_name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
              <label htmlFor='call-site' className='space-y-1 text-xs'>
                سایت
                <NativeSelect
                  id='call-site'
                  value={draft.site_id}
                  onChange={(e) => field('site_id', e.target.value)}
                >
                  <NativeSelectOption value=''>بدون سایت مشخص</NativeSelectOption>
                  {sites.map((s) => (
                    <NativeSelectOption key={s.site_id} value={s.site_id}>
                      {s.name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
              <label htmlFor='call-campaign' className='space-y-1 text-xs'>
                کمپین یا شناسه
                <Input
                  id='call-campaign'
                  value={draft.campaign}
                  onChange={(e) => field('campaign', e.target.value)}
                  placeholder='اختیاری'
                />
              </label>
              <label htmlFor='call-status' className='space-y-1 text-xs'>
                وضعیت
                <NativeSelect
                  id='call-status'
                  value={draft.status}
                  onChange={(e) => field('status', e.target.value)}
                >
                  {Object.entries(statusLabel).map(([key, label]) => (
                    <NativeSelectOption key={key} value={key}>
                      {label}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
              <label htmlFor='call-outcome' className='space-y-1 text-xs'>
                نتیجهٔ کسب‌وکار
                <NativeSelect id='call-outcome' value={draft.outcome} onChange={(e) => field('outcome', e.target.value)}>
                  {Object.entries(outcomeLabel).map(([key, label]) => <NativeSelectOption key={key} value={key}>{label}</NativeSelectOption>)}
                </NativeSelect>
              </label>
              <label htmlFor='call-confidence' className='space-y-1 text-xs'>
                اطمینان به منبع
                <NativeSelect id='call-confidence' value={draft.source_confidence} onChange={(e) => field('source_confidence', e.target.value)}>
                  {Object.entries(confidenceLabel).map(([key, label]) => <NativeSelectOption key={key} value={key}>{label}</NativeSelectOption>)}
                </NativeSelect>
              </label>
              <label htmlFor='call-order-value' className='space-y-1 text-xs'>
                ارزش سفارش
                <Input id='call-order-value' type='number' min='0' value={draft.order_value}
                  onChange={(e) => field('order_value', e.target.value)} disabled={draft.outcome !== 'order'} />
              </label>
              <label htmlFor='call-follow-up' className='space-y-1 text-xs'>
                زمان پیگیری بعدی
                <Input id='call-follow-up' type='datetime-local' value={draft.follow_up_at}
                  onChange={(e) => field('follow_up_at', e.target.value)} dir='ltr' />
              </label>
              <label className='flex items-center gap-2 self-end pb-2 text-sm'>
                <input
                  type='checkbox'
                  checked={draft.warranty}
                  onChange={(e) => field('warranty', e.target.checked)}
                />{' '}
                گارانتی
              </label>
            </div>
            <div className='grid gap-3 md:grid-cols-2'>
              <label htmlFor='call-issue' className='space-y-1 text-xs'>
                شرح مشکل یا درخواست
                <Input
                  id='call-issue'
                  value={draft.issue}
                  onChange={(e) => field('issue', e.target.value)}
                />
              </label>
              <label htmlFor='call-source-note' className='space-y-1 text-xs'>
                توضیح منبع
                <Input
                  id='call-source-note'
                  value={draft.source_note}
                  onChange={(e) => field('source_note', e.target.value)}
                  placeholder='مثلاً عبارت جست‌وجو یا پاسخ مشتری'
                />
              </label>
            </div>
            <div className='flex justify-end'>
              <Button type='submit' disabled={saving}>
                {saving ? 'در حال ذخیره…' : editingId === null ? 'ثبت تماس' : 'ذخیره تغییرات'}
              </Button>
            </div>
          </form>
        </motion.section>
      )}

      <Card>
        <CardHeader>
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <div>
              <CardTitle className='text-base'>دفتر تماس‌ها</CardTitle>
              <CardDescription>
                مثل شیت، تماس را در ردیف اول وارد کنید. زمان تماس واقعی را ثبت کنید تا منبع از کلیک‌های همان بازه پیشنهاد شود.
              </CardDescription>
            </div>
            <div className='flex items-center gap-2'><Badge variant='outline'>{number.format(recordTotal)} ردیف</Badge>
              <Button variant='outline' size='sm' onClick={async () => {
                try { const result = await callCenterApi.reconcile(siteId || undefined); toast.success(`${number.format(result.checked)} تماس بررسی شد؛ ${number.format(result.changed)} منبع تغییر کرد`); await load(); }
                catch (error) { toast.error(error instanceof Error ? error.message : String(error)); }
              }}>بازبینی منبع</Button></div>
          </div>
        </CardHeader>
        <CardContent>
          <form id='quick-call-entry' onSubmit={saveQuick} className='mb-3 rounded-lg border border-primary/30 bg-primary/5 p-3'>
            <div className='mb-2 flex items-center justify-between gap-2'><strong className='text-sm'>ردیف جدید</strong><span className='text-muted-foreground text-xs'>منبع خودکار بررسی می‌شود؛ در صورت نیاز از ستون منبع اصلاح کنید.</span></div>
            <div className='grid gap-2 md:grid-cols-2 xl:grid-cols-[170px_140px_1fr_150px_120px_120px_120px_1.5fr_auto]'>
              <Input aria-label='زمان واقعی تماس' title='زمان واقعی تماس' type='datetime-local' dir='ltr' value={quick.occurred_at} onFocus={() => setQuick((v) => ({ ...v, occurred_at: v.occurred_at || localNow() }))} onChange={(e) => setQuick((v) => ({ ...v, occurred_at: e.target.value }))} />
              <NativeSelect aria-label='سایت تماس' value={quickSite || siteId} onChange={(e) => setQuickSite(e.target.value)}><NativeSelectOption value=''>سایت نامشخص</NativeSelectOption>{sites.map((s) => <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>)}</NativeSelect>
              <Input aria-label='نام تماس‌گیرنده' placeholder='نام تماس‌گیرنده' value={quick.customer_name} onChange={(e) => setQuick((v) => ({ ...v, customer_name: e.target.value }))} />
              <Input aria-label='شماره تماس‌گیرنده، الزامی' placeholder='شماره تماس *' required dir='ltr' inputMode='tel' value={quick.phone} onChange={(e) => setQuick((v) => ({ ...v, phone: e.target.value }))} />
              <Input aria-label='برند خودرو' placeholder='برند' value={quick.brand} onChange={(e) => setQuick((v) => ({ ...v, brand: e.target.value }))} />
              <Input aria-label='مدل خودرو' placeholder='مدل' value={quick.model} onChange={(e) => setQuick((v) => ({ ...v, model: e.target.value }))} />
              <Input aria-label='منطقه' placeholder='منطقه' value={quick.region} onChange={(e) => setQuick((v) => ({ ...v, region: e.target.value }))} />
              <Input aria-label='شرح تماس' placeholder='شرح تماس' value={quick.issue} onChange={(e) => setQuick((v) => ({ ...v, issue: e.target.value }))} />
              <Button type='submit' disabled={quickSaving}>{quickSaving ? '...' : 'ثبت ردیف'}</Button>
            </div>
            <label className='mt-2 inline-flex items-center gap-1 text-xs'><input type='checkbox' checked={quick.warranty} onChange={(e) => setQuick((v) => ({ ...v, warranty: e.target.checked }))} /> گارانتی</label>
          </form>
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[950px] text-sm'>
              <thead>
                <tr className='border-b text-start text-xs text-muted-foreground'>
                  <th className='p-3 text-start'>زمان / تماس‌گیرنده</th>
                  <th className='p-3 text-start'>خودرو</th>
                  <th className='p-3 text-start'>منطقه</th>
                  <th className='p-3 text-start'>منبع</th>
                  <th className='p-3 text-start'>وضعیت</th>
                  <th className='p-3 text-start'>اپراتور</th>
                  <th className='p-3 text-start'>شرح</th>
                  <th className='p-3 text-start'>عملیات</th>
                </tr>
              </thead>
              <tbody>
                {records.map((row) => (
                  <tr
                    key={row.id}
                    className='border-b border-border/60 transition-colors hover:bg-muted/40'
                  >
                    <td className='p-3'>
                      <span className='block text-xs text-muted-foreground'>
                        {row.occurred_at
                          ? dateTime.format(new Date(row.occurred_at))
                          : 'زمان نامشخص'}
                      </span>
                      <strong className='block'>{row.customer_name || 'بدون نام'}</strong>
                      <span dir='ltr' className='block text-xs'>
                        {row.phone}
                      </span>
                    </td>
                    <td className='p-3'>
                      {row.brand} {row.model}
                      <span className='text-muted-foreground block text-xs'>
                        {row.warranty ? 'گارانتی' : 'غیرگارانتی'}
                      </span>
                    </td>
                    <td className='p-3'>{row.region || '—'}</td>
                    <td className='p-3'>
                      <NativeSelect
                        value={row.source}
                        onChange={(e) =>
                          update(row.id, {
                            source: e.target.value as CallSource,
                            source_basis: 'manual'
                          })
                        }
                        aria-label={`منبع تماس ${row.id}`}
                        className='w-28'
                        style={{ color: colors[row.source] }}
                      >
                        {channels.map((key) => (
                          <NativeSelectOption key={key} value={key}>
                            {sourceLabel[key]}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                      <span className='text-muted-foreground block pt-1 text-[10px]' title={row.attribution_event ?? undefined}>
                        {row.auto_attributed ? 'پیشنهاد از کلیک تماس · احتمالی' : row.source === 'unknown' ? 'بدون شواهد کافی' : row.source_basis === 'manual' ? 'انتخاب اپراتور' : row.source_basis}
                      </span>
                    </td>
                    <td className='p-3'>
                      <NativeSelect
                        value={row.status}
                        onChange={(e) => update(row.id, { status: e.target.value as CallStatus })}
                        aria-label={`وضعیت تماس ${row.id}`}
                        className='w-30'
                      >
                        {Object.entries(statusLabel).map(([key, label]) => (
                          <NativeSelectOption key={key} value={key}>
                            {label}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </td>
                    <td className='p-3 text-xs'>{row.operator_name || '—'}</td>
                    <td className='max-w-52 truncate p-3 text-xs' title={row.issue}>
                      {row.issue || '—'}
                    </td>
                    <td className='p-3'>
                      <Button variant='outline' size='sm' onClick={() => beginEdit(row)}>
                        ویرایش
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!records.length && (
              <div className='text-muted-foreground p-12 text-center text-sm'>
                {loading ? 'در حال دریافت تماس‌ها…' : 'تماسی با این فیلترها ثبت نشده است.'}
              </div>
            )}
          </div>
          <div className='mt-4 flex items-center justify-between gap-3 text-xs text-muted-foreground'>
            <span>
              نمایش {number.format(recordTotal ? page * 50 + 1 : 0)} تا{' '}
              {number.format(Math.min((page + 1) * 50, recordTotal))} از{' '}
              {number.format(recordTotal)}
            </span>
            <div className='flex gap-2'>
              <Button
                variant='outline'
                size='sm'
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                صفحه قبل
              </Button>
              <Button
                variant='outline'
                size='sm'
                disabled={(page + 1) * 50 >= recordTotal}
                onClick={() => setPage((p) => p + 1)}
              >
                صفحه بعد
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <p className='text-muted-foreground text-xs leading-6'>
        منبع تماس بر اساس ثبت اپراتور یا شواهدی که در ردیف مشخص شده گزارش می‌شود. دادهٔ بازدید، کلیک
        روی شماره و تماس انجام‌شده سه رویداد متفاوت‌اند.{' '}
        {analytics.undated > 0 &&
          `${number.format(analytics.undated)} ردیف واردشده تاریخ معتبر ندارند و در نمودارهای بازه‌ای محاسبه نمی‌شوند. `}
        {analytics.future > 0 &&
          `${number.format(analytics.future)} ردیف تاریخ آینده دارند و تا رسیدن آن تاریخ در آمار امروز محاسبه نمی‌شوند.`}
      </p>
    </div>
  );
}
