'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { api, ApiError } from '@/lib/api/client';
import type { components } from '@/lib/api/schema';

type Method = components['schemas']['RemediationMethodOut'];
type Proposal = components['schemas']['RemediationProposalOut'];
type Run = components['schemas']['RemediationRunOut'];
type StartRun = components['schemas']['StartRun'];
const statusFa: Record<string, string> = {
  queued: 'در صف', running: 'در حال اجرا', verified: 'رفع‌شده و تأییدشده', needs_review: 'نیازمند بررسی',
  needs_connection: 'نیازمند اتصال', failed: 'ناموفق', stale: 'داده تغییر کرده', rolled_back: 'بازگردانده‌شده'
};

export function RemediationAction({ siteId, issueKey }: { siteId: string; issueKey: string }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [pending, setPending] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestKeys = useRef(new Map<string, string>());
  const root = `/sites/${encodeURIComponent(siteId)}/remediation`;

  useEffect(() => {
    if (!run || !['queued', 'running'].includes(run.status)) return;
    const timer = window.setInterval(() => {
      api<Run>(`${root}/runs/${encodeURIComponent(run.id)}`).then(setRun).catch((e) => setError(String(e?.message ?? e)));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [root, run]);

  async function loadMethods() {
    setPending(true); setError(null); setProposal(null); setRun(null);
    try {
      const history = await api<Run[]>(`${root}/problems/${encodeURIComponent(issueKey)}/runs?limit=1`);
      if (history[0]) setRun(history[0]);
      setProposal(await api<Proposal>(`${root}/problems/${encodeURIComponent(issueKey)}/proposals`, { method: 'POST' }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setPending(false); }
  }

  async function execute(method: Method, confirmed = false) {
    if (method.uncertain && !confirmed) { setConfirmId(method.id); return; }
    if (!proposal) return;
    setPending(true); setError(null); setConfirmId(null);
    try {
      const selection = `${proposal.id}:${method.id}`;
      if (!requestKeys.current.has(selection)) requestKeys.current.set(selection, crypto.randomUUID());
      const body: StartRun = {
        proposal_id: proposal.id, method_id: method.id, evidence_hash: proposal.evidence_hash,
        idempotency_key: requestKeys.current.get(selection)!, uncertain_confirmed: confirmed
      };
      const result = await api<Run>(`${root}/runs`, { method: 'POST', json: body });
      setRun(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setPending(false); }
  }

  async function rollback() {
    if (!run) return;
    setPending(true); setError(null);
    try { setRun(await api<Run>(`${root}/runs/${encodeURIComponent(run.id)}/rollback`, { method: 'POST' })); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setPending(false); }
  }

  async function verifyAgain() {
    if (!run) return;
    setPending(true); setError(null);
    try { setRun(await api<Run>(`${root}/runs/${encodeURIComponent(run.id)}/verify`, { method: 'POST' })); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setPending(false); }
  }

  async function resume() {
    if (!run) return;
    setPending(true); setError(null);
    try { setRun(await api<Run>(`${root}/runs/${encodeURIComponent(run.id)}/resume`, { method: 'POST' })); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setPending(false); }
  }

  return <div className='mt-2 space-y-2 text-xs'>
    <Button size='sm' variant='outline' disabled={pending || siteId !== 'gearboxemdad'} onClick={loadMethods}>رفع مشکل</Button>
    {siteId !== 'gearboxemdad' && <p className='text-muted-foreground'>فعلاً فقط برای سایت آزمایشی gearboxemdad فعال است.</p>}
    {pending && <p className='text-muted-foreground'>در حال بررسی…</p>}
    {error && <p className='text-destructive'>{error}</p>}
    {error && <a className='text-primary underline' href='/dashboard/ai-models'>تنظیم مدل و مسیر Atria</a>}
    {proposal && <div className='space-y-2 rounded border p-2'>
      <p className='font-medium'>روش حل را انتخاب کنید</p>
      <ol className='list-inside list-decimal space-y-1 text-muted-foreground'>{proposal.roadmap?.map((step, i) => <li key={i}>{step}</li>)}</ol>
      {proposal.methods.map((method) => <div key={method.id} className='space-y-1 rounded border p-2'>
        <div className='font-medium'>{method.title}</div>
        <div className='text-muted-foreground'>{method.reason}</div>
        {typeof method.value === 'string' && method.value && <div className='break-words'>پیشنهاد: {method.value}</div>}
        {Array.isArray(method.value) && <div>تعداد تصاویر پیشنهادی: {method.value.length}</div>}
        <div>محل تغییر: {method.owner === 'frontend' ? 'قالب Next.js' : method.kind === 'wp_title' ? 'عنوان محتوای وردپرس' : ['wp_meta_title', 'wp_meta_description', 'wp_canonical', 'wp_noindex_off'].includes(method.kind) ? 'فیلد SEO وردپرس' : 'بدنهٔ محتوای وردپرس'}</div>
        <div>نتیجهٔ مورد انتظار: {method.verify}</div>
        <div>دامنهٔ اثر: {method.impact_unknown ? 'پس از اتصال قالب و بررسی diff تعیین می‌شود' : method.affected_urls.filter(Boolean).join('، ')}</div>
        <div>اطمینان: {method.confidence === 'high' ? 'بالا' : method.confidence === 'medium' ? 'متوسط' : 'پایین'}{method.uncertain ? ' · نیازمند تأیید دوم' : ''}</div>
        {method.uncertain && <div className='text-amber-700'>علت عدم‌اطمینان: {method.uncertainty_reason}</div>}
        <div>بازگردانی: {method.rollback ? 'ممکن' : 'پس از اتصال انتشار تعیین می‌شود'}</div>
        {method.access?.status !== 'not_checked' && <div className={method.access?.status === 'ready' ? 'text-emerald-700' : 'text-amber-700'}>
          دسترسی ویرایش: {method.access?.reason}
        </div>}
        {method.available || method.status === 'needs_connection'
          ? confirmId === method.id
            ? <div className='space-y-1 rounded border border-amber-500 p-2'>
                <p>{method.available ? 'تشخیص قطعی نیست. دامنهٔ اثر و مقدار پیشنهادی را بررسی و برای اجرای فوری دوباره تأیید کنید.' : 'این روش تا آماده‌شدن اتصال اجرا نمی‌شود. انتخاب شما با وضعیت نیازمند اتصال ثبت خواهد شد.'}</p>
                <Button size='sm' disabled={pending} onClick={() => execute(method, true)}>{method.available ? 'تأیید دوم و اجرا' : 'تأیید و ثبت روش'}</Button>{' '}
                <Button size='sm' variant='ghost' onClick={() => setConfirmId(null)}>انصراف</Button>
              </div>
            : <Button size='sm' disabled={pending} onClick={() => execute(method)}>{method.available ? 'انتخاب و اجرا' : 'انتخاب و ثبت نیاز به اتصال'}</Button>
          : <p className='text-amber-700'>برای اجرای این روش شواهد بیشتری لازم است؛ پیشنهاد ذخیره شده است.</p>}
        {!method.available && method.status === 'needs_connection' && method.owner !== 'frontend' && <a className='text-primary underline' href={`/dashboard/sites/${encodeURIComponent(siteId)}`}>تنظیم اتصال وردپرس</a>}
      </div>)}
    </div>}
    {run && <div className='rounded border p-2'>
      <p>وضعیت اجرا: {statusFa[run.status] ?? run.status}</p>
      {run.error && <p className='text-destructive'>{run.error}</p>}
      {run.verification?.reason && <p>{run.verification.reason}</p>}
      {run.status === 'needs_connection' && proposal?.methods.find((m) => m.id === run.method_id)?.owner !== 'frontend'
        ? <Button size='sm' variant='outline' disabled={pending} onClick={resume}>بررسی اتصال و ادامه</Button>
        : null}
      {run.status === 'needs_review' && <Button size='sm' variant='outline' disabled={pending} onClick={verifyAgain}>بررسی دوبارهٔ صفحه</Button>}
      {['verified', 'needs_review'].includes(run.status) && <Button size='sm' variant='outline' disabled={pending} onClick={rollback}>بازگردانی تغییر</Button>}
    </div>}
  </div>;
}
