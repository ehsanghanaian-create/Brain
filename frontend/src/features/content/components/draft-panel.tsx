'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type ContentDraft, type ContentReview, type ContentScore } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import Link from 'next/link';
import { DraftFeedback } from './draft-feedback';
import { ArticlePreview } from './article-preview';

const SEV_FA = { high: 'مهم', medium: 'متوسط', low: 'جزئی' } as const;
const SEV_COLOR = { high: '#dc2626', medium: '#f59e0b', low: '#64748b' } as const;
const REVIEW_FA: Record<string, string> = { none: 'بازبینی نشده', changes_requested: 'نیاز به اصلاح', ready: 'آماده' };
const AREA_FA: Record<string, string> = { structure: 'ساختار', entities: 'موجودیت‌ها', quality: 'کیفیت', seo: 'سئو', intent: 'اینتنت', cta: 'CTA', keywords: 'کلمات کلیدی' };
const fa = new Intl.NumberFormat('fa-IR');

/** Draft ↔ score ↔ review loop for one content item (Phase 7). Every save = new version. AI suggestions are advisory. */
export function DraftPanel({ siteId, cid, onChanged }: { siteId: string; cid: number; onChanged: () => void }) {
  const [drafts, setDrafts] = useState<ContentDraft[]>([]);
  const [selected, setSelected] = useState<ContentDraft | null>(null);
  const [editing, setEditing] = useState(false);
  const [f, setF] = useState({ body: '', title: '', meta_description: '', format: 'markdown', change_summary: '' });
  const [score, setScore] = useState<ContentScore | null>(null);
  const [review, setReview] = useState<ContentReview | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await endpoints.contentDrafts(siteId, cid);
      setDrafts(list);
      const latest = list[0] ?? null;
      if (latest) {
        const full = await endpoints.contentDraft(siteId, cid, latest.id);
        setSelected(full);
        const hist = await endpoints.contentIntelligence(siteId, cid);
        const lastReview = hist.reviews.find((r) => r.draft_id === latest.id) as unknown as ContentReview | undefined;
        const lastScore = hist.scores.find((s) => s.draft_id === latest.id) as unknown as ContentScore | undefined;
        setReview(lastReview ? { ...lastReview, score: lastScore ?? (lastReview as unknown as ContentReview).score, findings: lastReview.findings, counts: lastReview.counts as ContentReview['counts'], review_status: latest.review_status, gate: '', summary_fa: String((lastReview as Record<string, unknown>).summary_fa ?? ''), version: latest.version, draft_id: latest.id, id: Number((lastReview as Record<string, unknown>).id), provenance: (lastReview as Record<string, unknown>).provenance as Record<string, unknown> } : null);
        setScore(lastScore ? ({ ...lastScore, label: lastScore.label ?? (lastScore.total >= 80 ? 'ready' : lastScore.total >= 60 ? 'needs_work' : 'weak'), failed: (lastScore.findings ?? []).filter((x) => !x.passed), dims_fa: {} } as ContentScore) : null);
      } else { setSelected(null); setReview(null); setScore(null); setEditing(true); }
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); }
  }, [siteId, cid]);
  useEffect(() => { load(); }, [load]);

  function startEdit(from?: ContentDraft | null) {
    setF({ body: from?.body ?? '', title: from?.title ?? '', meta_description: from?.meta_description ?? '', format: from?.format ?? 'markdown', change_summary: '' });
    setEditing(true);
  }
  async function saveVersion() {
    setBusy('save');
    try {
      const d = await endpoints.createDraft(siteId, cid, { body: f.body, format: f.format, title: f.title || undefined, meta_description: f.meta_description || undefined, change_summary: f.change_summary || undefined, source: 'user' });
      toast.success(`نسخه ${d.version} ثبت شد — ${d.change_summary ?? ''}`);
      setEditing(false); await load(); onChanged();
    } catch (e) { toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)); } finally { setBusy(null); }
  }
  async function runReview(useAi: boolean) {
    setBusy('review');
    try {
      const r = await endpoints.reviewContent(siteId, cid, { use_ai: useAi });
      setReview(r); setScore(r.score);
      toast[r.review_status === 'ready' ? 'success' : 'warning'](`${REVIEW_FA[r.review_status]} — امتیاز ${r.score.total}`);
      await load(); onChanged();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(null); }
  }
  async function pick(did: number) {
    const full = await endpoints.contentDraft(siteId, cid, did); setSelected(full); setEditing(false);
  }

  return (
    <div className='space-y-3 py-3 text-sm'>
      <div className='flex flex-wrap items-center gap-2'>
        {drafts.length > 0 && (
          <NativeSelect value={selected?.id ?? ''} onChange={(e) => pick(Number(e.target.value))} className='h-8 w-56 text-xs'>
            {drafts.map((d) => <NativeSelectOption key={d.id} value={d.id}>v{d.version} · {d.source} · {d.word_count} کلمه · {REVIEW_FA[d.review_status] ?? d.review_status}</NativeSelectOption>)}
          </NativeSelect>
        )}
        {selected && !editing && <Button size='sm' variant='secondary' onClick={() => startEdit(selected)}>ویرایش → نسخه جدید</Button>}
        {!editing && drafts.length === 0 && <Button size='sm' onClick={() => startEdit(null)}>ثبت پیش‌نویس</Button>}
        {!editing && <Button size='sm' variant='outline' nativeButton={false} render={<Link href={`/dashboard/ai-studio?site=${encodeURIComponent(siteId)}&content=${cid}`} aria-label='تولید پیش‌نویس با AI' />} title='تولید چندعاملی با تزریق حافظه سایت؛ خروجی فقط پیش‌نویس است'>تولید با AI</Button>}
        {selected && !editing && (
          <>
            <Button size='sm' disabled={!!busy} onClick={() => runReview(false)}>{busy === 'review' ? '…' : 'بازبینی و امتیاز'}</Button>
            <Button size='sm' variant='outline' disabled={!!busy} onClick={() => runReview(true)} title='با ارائه‌دهنده AI مسیردهی‌شده (مشاوره‌ای)'>بازبینی با AI</Button>
          </>
        )}
        {selected && <span className='ms-auto text-xs'>{REVIEW_FA[selected.review_status] ?? selected.review_status}{selected.change_summary ? ` · ${selected.change_summary}` : ''}</span>}
      </div>

      {editing && (
        <div className='grid gap-2 rounded-md border p-2'>
          <div className='grid grid-cols-2 gap-2'>
            <div className='grid gap-1'><Label>عنوان (H1/تگ title)</Label><Input value={f.title} onChange={(e) => setF((s) => ({ ...s, title: e.target.value }))} /></div>
            <div className='grid gap-1'><Label>قالب</Label><NativeSelect value={f.format} onChange={(e) => setF((s) => ({ ...s, format: e.target.value }))}><NativeSelectOption value='markdown'>Markdown</NativeSelectOption><NativeSelectOption value='html'>HTML</NativeSelectOption><NativeSelectOption value='text'>متن ساده</NativeSelectOption></NativeSelect></div>
          </div>
          <div className='grid gap-1'><Label>توضیحات متا</Label><Input value={f.meta_description} onChange={(e) => setF((s) => ({ ...s, meta_description: e.target.value }))} /><span className='text-muted-foreground text-[10px]'>{f.meta_description.length} نویسه</span></div>
          <div className='grid gap-1'><Label>متن پیش‌نویس</Label><Textarea rows={16} value={f.body} onChange={(e) => setF((s) => ({ ...s, body: e.target.value }))} className='font-mono text-xs' dir='auto' placeholder={'# H1\n\nپاراگراف اول با شماره تماس…\n\n## H2\n…'} /></div>
          <div className='grid gap-1'><Label>خلاصه تغییر (اختیاری)</Label><Input value={f.change_summary} onChange={(e) => setF((s) => ({ ...s, change_summary: e.target.value }))} placeholder='مثلاً: افزودن بخش قیمت و FAQ' /></div>
          <div className='flex justify-end gap-2'><Button variant='ghost' size='sm' onClick={() => setEditing(false)}>انصراف</Button><Button size='sm' onClick={saveVersion} disabled={!!busy || !f.body.trim()}>{busy === 'save' ? '…' : `ثبت به‌عنوان نسخه ${drafts.length + 1}`}</Button></div>
        </div>
      )}

      {selected && !editing && <DraftFeedback siteId={siteId} cid={cid} draftId={selected.id} runId={selected.provenance?.run_id ? String(selected.provenance.run_id) : null} />}

      {selected && !editing && (
        <>
          <ArticlePreview draft={selected} />
          <details className='rounded-md border p-2'>
            <summary className='cursor-pointer text-xs'>جزئیات ساختار v{selected.version} — {selected.structure.h2.length} سرفصل H2، {selected.structure.links.length} لینک، {selected.structure.faq ? 'با FAQ' : 'بدون FAQ'}{selected.provenance && Object.keys(selected.provenance).length ? ` · منشأ: ${String(selected.provenance.provider ?? selected.source)}` : ''}</summary>
            <div className='text-muted-foreground mt-2 grid gap-1 text-xs sm:grid-cols-3'>
              <span>H1: {fa.format(selected.structure.h1.length)}</span>
              <span>H2: {fa.format(selected.structure.h2.length)}</span>
              <span>H3: {fa.format(selected.structure.h3.length)}</span>
              <span>پاراگراف: {fa.format(selected.structure.paragraphs.length)}</span>
              <span>تصویر: {fa.format(selected.structure.images.length)}</span>
              <span>پرسش: {fa.format(selected.structure.questions.length)}</span>
            </div>
          </details>
        </>
      )}

      {score && (
        <div className='rounded-md border p-2'>
          <div className='flex items-center justify-between'>
            <div className='font-medium'>امتیاز کیفیت: <span className='text-lg tabular-nums' style={{ color: score.total >= (score.thresholds?.ready ?? 80) ? '#16a34a' : score.total >= (score.thresholds?.needs_work ?? 60) ? '#f59e0b' : '#dc2626' }}>{fa.format(score.total)}</span> / ۱۰۰</div>
            <Badge variant='outline'>{score.label === 'ready' ? 'آماده' : score.label === 'needs_work' ? 'نیاز به بهبود' : 'ضعیف'}</Badge>
          </div>
          <div className='mt-2 grid gap-1'>
            {Object.entries(score.dims).map(([k, v]) => (
              <div key={k} className='flex items-center gap-2 text-xs'>
                <span className='w-32 shrink-0'>{DIM_FA[k] ?? k}</span>
                <div className='bg-muted h-2 flex-1 overflow-hidden rounded'><div className='h-2 rounded' style={{ width: `${v}%`, background: v >= 80 ? '#16a34a' : v >= 50 ? '#f59e0b' : '#dc2626' }} /></div>
                <span className='w-10 text-end tabular-nums'>{fa.format(v)}</span><span className='text-muted-foreground w-8 text-[10px]'>×{score.weights[k]}</span>
              </div>
            ))}
          </div>
          {score.failed?.length > 0 && (
            <details className='mt-2'><summary className='cursor-pointer text-xs'>قواعد ردشده ({score.failed.length})</summary>
              <ul className='mt-1 space-y-0.5 text-xs'>{score.failed.map((x) => <li key={x.rule}>• <span className='text-muted-foreground'>[{DIM_FA[x.dim] ?? x.dim}]</span> {x.evidence} — <span className='text-emerald-600'>{x.fix_fa}</span></li>)}</ul>
            </details>
          )}
        </div>
      )}

      {review && (
        <div className='rounded-md border p-2'>
          <div className='flex flex-wrap items-center gap-2 text-xs'>
            <span className='font-medium'>بازبینی v{review.version}:</span>
            <Badge style={{ background: review.review_status === 'ready' ? '#16a34a' : '#f59e0b' }}>{REVIEW_FA[review.review_status] ?? review.review_status}</Badge>
            {(['high', 'medium', 'low'] as const).map((s) => <span key={s} className='flex items-center gap-1'><span className='inline-block h-2 w-2 rounded-full' style={{ background: SEV_COLOR[s] }} />{SEV_FA[s]} {fa.format(review.counts?.[s] ?? 0)}</span>)}
            <span className='text-muted-foreground'>{review.summary_fa}</span>
            {review.provenance?.note ? <span className='text-muted-foreground'>· {String(review.provenance.note)}</span> : null}
            {review.provenance?.ai_used ? <Badge variant='outline'>AI: {String(review.provenance.provider)}</Badge> : null}
          </div>
          <ul className='mt-2 space-y-1'>
            {review.findings.map((x, i) => (
              <li key={i} className='rounded border p-2 text-xs' style={{ borderInlineStartWidth: 3, borderInlineStartColor: SEV_COLOR[x.severity] }}>
                <div className='flex items-center gap-2'><Badge variant='outline'>{AREA_FA[x.area] ?? x.area}</Badge><span className='font-medium'>{x.message_fa}</span>{x.auto_fixable && <span className='text-muted-foreground'>قابل اصلاح خودکار (پیشنهادی)</span>}</div>
                {x.evidence && <div className='text-muted-foreground mt-0.5' dir='auto'>{x.evidence}</div>}
                {x.suggestion_fa && <div className='mt-0.5 text-emerald-600'>پیشنهاد: {x.suggestion_fa}</div>}
              </li>
            ))}
            {review.findings.length === 0 && <li className='text-muted-foreground text-xs'>یافته‌ای نیست ✓</li>}
          </ul>
          <p className='text-muted-foreground mt-2 text-[11px]'>پیشنهادها فقط مشاوره‌ای هستند؛ هیچ تغییری خودکار اعمال نمی‌شود. اصلاحات را در «ویرایش → نسخه جدید» وارد کنید و دوباره بازبینی کنید.</p>
        </div>
      )}
    </div>
  );
}

const DIM_FA: Record<string, string> = { intent: 'تطابق با اینتنت', keywords: 'پوشش کلمات کلیدی', entities: 'پوشش موجودیت‌ها', headings: 'ساختار سرفصل‌ها', links: 'کیفیت لینک داخلی', cta: 'کیفیت CTA', completeness: 'کامل بودن' };
