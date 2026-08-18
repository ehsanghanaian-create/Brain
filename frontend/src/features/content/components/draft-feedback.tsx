'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { endpoints } from '@/lib/api/client';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

/** Phase 9 human feedback on a draft: rating 1–5 + optional tags. Feeds the AI learning system (recommendation only). */
export function DraftFeedback({ siteId, cid, draftId, runId }: { siteId: string; cid: number; draftId: number; runId?: string | null }) {
  const [tags, setTags] = useState<{ tag: string; fa: string }[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [rating, setRating] = useState<number | null>(null);
  const [existing, setExisting] = useState<any[]>([]);
  useEffect(() => { endpoints.aiFeedbackTags().then(setTags).catch(() => null); endpoints.genFeedbackList(siteId, cid).then(setExisting).catch(() => null); }, [siteId, cid]);
  const mine = existing.filter((f) => f.draft_id === draftId);
  async function send() {
    if (!rating) return;
    try { await endpoints.genFeedback(siteId, cid, { rating, tags: sel, draft_id: draftId, run_id: runId ?? undefined }); toast.success('بازخورد ثبت شد — در تحلیل یادگیری AI استفاده می‌شود'); setExisting(await endpoints.genFeedbackList(siteId, cid)); setRating(null); setSel([]); } catch (e) { toast.error(String(e)); }
  }
  return (
    <div className='rounded-md border p-2 text-xs'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='font-medium'>بازخورد انسانی روی این پیش‌نویس:</span>
        {[1, 2, 3, 4, 5].map((n) => <button key={n} onClick={() => setRating(n)} className={`h-6 w-6 rounded border ${rating === n ? 'bg-primary text-primary-foreground' : ''}`}>{n}</button>)}
        {tags.map((t) => <button key={t.tag} onClick={() => setSel((s) => (s.includes(t.tag) ? s.filter((x) => x !== t.tag) : [...s, t.tag]))}><Badge variant={sel.includes(t.tag) ? 'default' : 'outline'}>{t.fa}</Badge></button>)}
        <Button size='sm' variant='secondary' disabled={!rating} onClick={send}>ثبت</Button>
        {mine.length > 0 && <span className='text-muted-foreground'>قبلاً: {mine.map((f) => `${f.rating}/5${f.tags?.length ? ` (${f.tags.join('، ')})` : ''}`).join(' · ')}</span>}
      </div>
    </div>
  );
}
