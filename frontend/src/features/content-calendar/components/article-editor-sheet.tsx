'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ApiError, endpoints, type ContentDraft, type ContentReview, type WpMediaItem } from '@/lib/api/client';
import Image from '@tiptap/extension-image';
import { Markdown } from '@tiptap/markdown';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { EditorChatPanel } from './editor-chat-panel';
import { MediaLibraryDialog } from './media-library-dialog';

export type EditorTarget = { cid: number; planId?: number; title: string; keyword?: string; featured?: { id: number; url: string; alt: string } | null };

const fa = new Intl.NumberFormat('fa-IR');
const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
const countWords = (s: string) => s.split(/\s+/).filter(Boolean).length;
const REVIEW_FA: Record<string, string> = { none: 'بازبینی نشده', changes_requested: 'نیاز به اصلاح', ready: 'آماده' };
const EDITOR_CLASS = 'article-editor min-h-[55vh] px-4 py-3 text-[15px] leading-8 outline-none [&_h1]:my-4 [&_h1]:text-2xl [&_h1]:font-bold [&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-xl [&_h2]:font-bold [&_h3]:mt-4 [&_h3]:mb-1 [&_h3]:text-lg [&_h3]:font-semibold [&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:ps-6 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:ps-6 [&_li]:my-0.5 [&_blockquote]:border-s-4 [&_blockquote]:ps-3 [&_blockquote]:text-muted-foreground [&_a]:underline [&_img]:my-3 [&_img]:max-w-full [&_img]:rounded-lg [&_strong]:font-bold [&_hr]:my-4';

export function ArticleEditorSheet({ siteId, target, onClose, onChanged }: { siteId: string; target: EditorTarget | null; onClose: () => void; onChanged: () => void }) {
  const open = target !== null;
  const [drafts, setDrafts] = useState<ContentDraft[]>([]);
  const [current, setCurrent] = useState<ContentDraft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [review, setReview] = useState<ContentReview | null>(null);
  const [media, setMedia] = useState<'insert' | 'featured' | null>(null);
  const [featured, setFeatured] = useState<EditorTarget['featured']>(null);
  const [summary, setSummary] = useState('');
  const [wordCount, setWordCount] = useState(0);
  const [chat, setChat] = useState(true);

  const editor = useEditor({
    extensions: [StarterKit, Image.configure({ inline: false }), Markdown],
    content: '',
    contentType: 'markdown',
    immediatelyRender: false,
    editorProps: { attributes: { dir: 'rtl', class: EDITOR_CLASS } },
    onUpdate: ({ editor: ed }) => { setDirty(true); setWordCount(countWords(ed.getText())); }
  });
  const getMarkdown = useCallback(() => editor?.getMarkdown() ?? '', [editor]);
  const setMarkdown = useCallback((md: string) => { editor?.commands.setContent(md, { contentType: 'markdown' }); setWordCount(countWords(editor?.getText() ?? '')); }, [editor]);

  const load = useCallback(async (cid: number, pick?: number) => {
    try {
      const list = await endpoints.contentDrafts(siteId, cid);
      setDrafts(list);
      const chosen = list.find((d) => d.id === pick) ?? list[0] ?? null;
      if (chosen) { const full = await endpoints.contentDraft(siteId, cid, chosen.id); setCurrent(full); setMarkdown(full.body ?? ''); }
      else { setCurrent(null); setMarkdown(''); }
      setDirty(false);
    } catch (e) { err(e); }
  }, [siteId, setMarkdown]);
  useEffect(() => {
    if (!target || !editor) return;
    setReview(null); setSummary(''); setFeatured(target.featured ?? null);
    load(target.cid);
  }, [target, editor, load]);

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    try { await fn(); } catch (e) { err(e); } finally { setBusy(null); }
  }
  const save = () => run('save', async () => {
    if (!target) return;
    const md = getMarkdown().trim();
    if (!md) throw new Error('متن مقاله خالی است');
    const d = await endpoints.createDraft(siteId, target.cid, { body: md, format: 'markdown', title: current?.title ?? target.title, meta_description: current?.meta_description ?? undefined, change_summary: summary.trim() || undefined, source: 'user' });
    toast.success(`نسخهٔ ${fa.format(d.version)} ذخیره شد`);
    setSummary(''); await load(target.cid, d.id); onChanged();
  });
  const runReview = () => run('review', async () => {
    if (!target) return;
    if (dirty) throw new Error('ابتدا نسخهٔ جدید را ذخیره کنید تا همان متن بازبینی شود');
    const r = await endpoints.reviewContent(siteId, target.cid, { use_ai: false });
    setReview(r);
    (r.review_status === 'ready' ? toast.success : toast.warning)(`${REVIEW_FA[r.review_status] ?? r.review_status} — امتیاز ${fa.format(r.score.total)}`);
    onChanged();
  });
  const pickMedia = (it: WpMediaItem) => {
    if (media === 'insert') { editor?.chain().focus().setImage({ src: it.url, alt: it.alt }).run(); setMedia(null); return; }
    if (media === 'featured' && target?.planId) {
      const planId = target.planId;
      run('featured', async () => {
        const p = await endpoints.plan(siteId, planId);
        await endpoints.planPatch(siteId, planId, { metadata: { ...(p.metadata ?? {}), featured_media_id: it.id, featured_media: { id: it.id, url: it.url, alt: it.alt } } });
        setFeatured({ id: it.id, url: it.url, alt: it.alt }); toast.success('تصویر شاخص تنظیم شد'); onChanged();
      });
    }
    setMedia(null);
  };
  const clearFeatured = () => { if (!target?.planId) return; const planId = target.planId; run('featured', async () => { const p = await endpoints.plan(siteId, planId); const meta = { ...(p.metadata ?? {}) }; delete meta.featured_media_id; delete meta.featured_media; await endpoints.planPatch(siteId, planId, { metadata: meta }); setFeatured(null); onChanged(); }); };
  const tb = (label: string, active: boolean, onClick: () => void, title?: string) => <Button type='button' size='sm' variant={active ? 'default' : 'ghost'} className='h-7 px-2 text-xs' title={title ?? label} onClick={onClick}>{label}</Button>;
  const score = review?.score?.total;

  return (
    <>
      <Sheet open={open} onOpenChange={(o) => { if (!o && !busy) { if (dirty && !confirm('تغییرات ذخیره‌نشده از بین می‌رود؟')) return; onClose(); } }}>
        <SheetContent side='left' className='flex flex-col gap-0 p-0 data-[side=left]:w-full data-[side=left]:sm:max-w-5xl data-[side=left]:xl:max-w-6xl' dir='rtl'>
          <SheetHeader className='border-b p-3'>
            <SheetTitle className='flex flex-wrap items-center gap-2 text-base'>
              {target?.title ?? '…'}
              {current && <Badge variant='outline'>نسخه {fa.format(current.version)}</Badge>}
              {dirty && <Badge variant='secondary'>ذخیره‌نشده</Badge>}
              {typeof score === 'number' && <Badge style={{ background: score >= 80 ? '#16a34a' : score >= 60 ? '#f59e0b' : '#dc2626' }}>امتیاز سئو {fa.format(score)}</Badge>}
            </SheetTitle>
            <SheetDescription className='flex flex-wrap items-center gap-2'>
              <span>{fa.format(wordCount)} کلمه</span>
              {target?.keyword && <span>· کلمهٔ کلیدی: {target.keyword}</span>}
              {drafts.length > 1 && <NativeSelect value={current?.id ?? ''} onChange={(e) => target && load(target.cid, Number(e.target.value))} className='h-7 w-56 text-xs'>{drafts.map((d) => <NativeSelectOption key={d.id} value={d.id}>نسخه {d.version} · {d.source} · {d.word_count} کلمه</NativeSelectOption>)}</NativeSelect>}
            </SheetDescription>
          </SheetHeader>
          <div className='flex min-h-0 flex-1'>
            <div className='flex min-w-0 flex-1 flex-col'>
              <div className='flex flex-wrap items-center gap-0.5 border-b px-2 py-1'>
                {tb('H2', !!editor?.isActive('heading', { level: 2 }), () => editor?.chain().focus().toggleHeading({ level: 2 }).run(), 'سرفصل H2')}
                {tb('H3', !!editor?.isActive('heading', { level: 3 }), () => editor?.chain().focus().toggleHeading({ level: 3 }).run(), 'زیرعنوان H3')}
                {tb('پاراگراف', !!editor?.isActive('paragraph'), () => editor?.chain().focus().setParagraph().run())}
                <span className='bg-border mx-1 h-5 w-px' />
                {tb('B', !!editor?.isActive('bold'), () => editor?.chain().focus().toggleBold().run(), 'پررنگ')}
                {tb('I', !!editor?.isActive('italic'), () => editor?.chain().focus().toggleItalic().run(), 'مورب')}
                {tb('• فهرست', !!editor?.isActive('bulletList'), () => editor?.chain().focus().toggleBulletList().run())}
                {tb('۱. فهرست', !!editor?.isActive('orderedList'), () => editor?.chain().focus().toggleOrderedList().run())}
                {tb('نقل‌قول', !!editor?.isActive('blockquote'), () => editor?.chain().focus().toggleBlockquote().run())}
                {tb('لینک', !!editor?.isActive('link'), () => { const prev = editor?.getAttributes('link').href as string | undefined; const url = prompt('آدرس لینک (خالی = حذف)', prev ?? 'https://'); if (url === null) return; if (!url.trim()) editor?.chain().focus().unsetLink().run(); else editor?.chain().focus().extendMarkRange('link').setLink({ href: url.trim() }).run(); })}
                {tb('تصویر', false, () => setMedia('insert'), 'درج تصویر از رسانهٔ وردپرس')}
                <span className='bg-border mx-1 h-5 w-px' />
                {tb('↶', false, () => editor?.chain().focus().undo().run(), 'واگرد')}
                {tb('↷', false, () => editor?.chain().focus().redo().run(), 'ازنو')}
                <span className='ms-auto flex items-center gap-1'>
                  {target?.planId && (featured
                    ? <span className='flex items-center gap-1 text-xs'><img src={featured.url} alt={featured.alt} className='h-7 w-10 rounded object-cover' />تصویر شاخص<button type='button' className='text-destructive ms-1' onClick={clearFeatured} title='حذف تصویر شاخص'>×</button></span>
                    : <Button type='button' size='sm' variant='outline' className='h-7 text-xs' onClick={() => setMedia('featured')}>تصویر شاخص</Button>)}
                  <Button type='button' size='sm' variant='ghost' className='h-7 text-xs' onClick={() => setChat((v) => !v)}>{chat ? 'بستن چت' : 'چت با AI'}</Button>
                </span>
              </div>
              <div className='min-h-0 flex-1 overflow-y-auto'>
                {editor ? <EditorContent editor={editor} /> : <p className='text-muted-foreground p-4 text-sm'>در حال آماده‌سازی ویرایشگر…</p>}
                {review && (
                  <div className='mx-4 mb-4 rounded-md border p-2 text-xs'>
                    <div className='flex flex-wrap items-center gap-2'><b>بازبینی سئو:</b><Badge variant='outline'>{REVIEW_FA[review.review_status] ?? review.review_status}</Badge><span className='text-muted-foreground'>{review.summary_fa}</span></div>
                    <ul className='mt-1 space-y-0.5'>{review.findings.slice(0, 8).map((x, i) => <li key={i}>• <span className='font-medium'>{x.message_fa}</span>{x.suggestion_fa ? <span className='text-emerald-600'> — {x.suggestion_fa}</span> : null}</li>)}{review.findings.length === 0 && <li className='text-muted-foreground'>یافته‌ای نیست ✓</li>}</ul>
                  </div>
                )}
              </div>
              <div className='flex flex-wrap items-center gap-2 border-t p-2'>
                <Input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder='خلاصهٔ تغییر (اختیاری)' className='h-8 max-w-xs text-xs' />
                <Button size='sm' disabled={!!busy || !editor} onClick={save}>{busy === 'save' ? '…' : `ذخیرهٔ نسخهٔ ${fa.format(drafts.length + 1)}`}</Button>
                <Button size='sm' variant='outline' disabled={!!busy || !current} onClick={runReview}>{busy === 'review' ? '…' : 'بازبینی سئو'}</Button>
                {current?.change_summary && <span className='text-muted-foreground text-[11px]'>آخرین تغییر: {current.change_summary}</span>}
              </div>
            </div>
            {chat && target && (
              <aside className='hidden w-80 shrink-0 border-s md:block'>
                <EditorChatPanel siteId={siteId} title={target.title} keyword={target.keyword} getMarkdown={getMarkdown} onApply={(md) => { setMarkdown(md); setDirty(true); }} />
              </aside>
            )}
          </div>
        </SheetContent>
      </Sheet>
      <MediaLibraryDialog siteId={siteId} open={media !== null} onClose={() => setMedia(null)} onPick={pickMedia} title={media === 'featured' ? 'انتخاب تصویر شاخص' : 'درج تصویر در متن'} />
    </>
  );
}
