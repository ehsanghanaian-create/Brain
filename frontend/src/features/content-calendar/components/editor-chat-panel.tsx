'use client';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type AssistMode } from '@/lib/api/client';
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

type Msg = { role: 'user' | 'assistant'; content: string; revised?: string | null; meta?: string };
const QUICK: { mode: AssistMode; label: string }[] = [
  { mode: 'seo', label: 'بهبود سئو' }, { mode: 'rewrite', label: 'بازنویسی روان‌تر' }, { mode: 'shorten', label: 'کوتاه‌تر کن' }, { mode: 'expand', label: 'مفصل‌تر کن' }, { mode: 'faq', label: 'افزودن FAQ' }
];
const usd = (v: number) => (v ? `${v.toFixed(4)}$` : 'رایگان');

export function EditorChatPanel({ siteId, title, keyword, getMarkdown, onApply }: { siteId: string; title: string; keyword?: string; getMarkdown: () => string; onApply: (markdown: string) => void }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, busy]);

  async function send(mode: AssistMode, text?: string) {
    const shown = text?.trim() || QUICK.find((q) => q.mode === mode)?.label || '';
    if (!shown) return;
    const history = messages.slice(-8).map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: 'user', content: shown }]);
    setInput(''); setBusy(mode);
    try {
      const r = await endpoints.wsAssist(siteId, { markdown: getMarkdown(), message: text?.trim() || '', mode, title, keyword, history });
      setMessages((m) => [...m, { role: 'assistant', content: r.reply || '—', revised: r.revised_markdown, meta: `${r.meta.provider}/${r.meta.model} · ${usd(r.meta.cost_usd)} · ${Math.round(r.meta.elapsed_ms / 1000)} ثانیه` }]);
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.message} (${e.code})` : String(e);
      setMessages((m) => [...m, { role: 'assistant', content: `خطا: ${msg}` }]);
      toast.error(msg);
    } finally { setBusy(null); }
  }

  return (
    <div className='flex h-full min-h-0 flex-col'>
      <div className='border-b p-2 text-xs'>
        <div className='mb-1 font-medium'>گفت‌وگو با نویسندهٔ هوش مصنوعی</div>
        <div className='flex flex-wrap gap-1'>
          {QUICK.map((q) => <Button key={q.mode} size='sm' variant='outline' className='h-7 text-[11px]' disabled={!!busy} onClick={() => send(q.mode)}>{busy === q.mode ? '…' : q.label}</Button>)}
        </div>
      </div>
      <div className='min-h-0 flex-1 space-y-2 overflow-y-auto p-2 text-xs'>
        {messages.length === 0 && <p className='text-muted-foreground'>یکی از دکمه‌های بالا را بزنید یا بنویسید مثلاً: «پاراگراف اول را با تأکید بر تهران بازنویسی کن» یا «کدام بخش ضعیف است؟». متن فعلی ویرایشگر (حتی ذخیره‌نشده) برای مدل ارسال می‌شود.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`rounded-lg p-2 ${m.role === 'user' ? 'bg-primary/10 ms-6' : 'bg-muted me-6'}`}>
            <div className='whitespace-pre-wrap leading-5'>{m.content}</div>
            {m.meta && <div className='text-muted-foreground mt-1 text-[10px]' dir='ltr'>{m.meta}</div>}
            {m.revised && <Button size='sm' className='mt-2 h-7 text-[11px]' onClick={() => { onApply(m.revised!); toast.success('متن جدید در ویرایشگر قرار گرفت — برای ثبت، «ذخیرهٔ نسخهٔ جدید» را بزنید'); }}>اعمال روی متن ویرایشگر</Button>}
          </div>
        ))}
        {busy && <div className='text-muted-foreground animate-pulse'>در حال فکر کردن…</div>}
        <div ref={bottom} />
      </div>
      <form className='border-t p-2' onSubmit={(e) => { e.preventDefault(); if (input.trim()) send('chat', input); }}>
        <Textarea rows={2} value={input} onChange={(e) => setInput(e.target.value)} placeholder='درخواست یا سؤال دربارهٔ همین مقاله…' disabled={!!busy}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && input.trim()) { e.preventDefault(); send('chat', input); } }} />
        <div className='mt-1 flex items-center justify-between'>
          <span className='text-muted-foreground text-[10px]'>Ctrl+Enter برای ارسال</span>
          <Button type='submit' size='sm' disabled={!!busy || !input.trim()}>ارسال</Button>
        </div>
      </form>
    </div>
  );
}
