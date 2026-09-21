'use client';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ApiError, endpoints, type WpMediaItem } from '@/lib/api/client';
import { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { toast } from 'sonner';

const fa = new Intl.NumberFormat('fa-IR');
const err = (e: unknown) => toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));

export function MediaLibraryDialog({ siteId, open, onClose, onPick, title = 'رسانهٔ وردپرس' }: { siteId: string; open: boolean; onClose: () => void; onPick: (item: WpMediaItem) => void; title?: string }) {
  const [items, setItems] = useState<WpMediaItem[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const r = await endpoints.wpMediaList(siteId, { page, per_page: 24, search: q }); setItems(r.items); setPages(r.total_pages); setTotal(r.total); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setItems([]); }
    finally { setLoading(false); }
  }, [siteId, page, q]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const onDrop = useCallback(async (files: File[]) => {
    const f = files[0];
    if (!f) return;
    setUploading(f.name);
    try { const it = await endpoints.wpMediaUpload(siteId, f, { alt_text: f.name.replace(/\.[^.]+$/, '') }); toast.success('تصویر در وردپرس بارگذاری شد'); onPick(it); }
    catch (e) { err(e); } finally { setUploading(null); }
  }, [siteId, onPick]);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'image/jpeg': [], 'image/png': [], 'image/webp': [], 'image/gif': [] }, maxSize: 10 * 1024 * 1024, multiple: false, disabled: !!uploading });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-3xl' dir='rtl'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>تصاویر کتابخانهٔ رسانهٔ همین سایت؛ برای بارگذاری تصویر جدید، فایل را در کادر بیندازید.</DialogDescription>
        </DialogHeader>
        <div {...getRootProps()} className={`cursor-pointer rounded-lg border border-dashed p-4 text-center text-xs transition-colors ${isDragActive ? 'border-primary bg-primary/5' : 'hover:bg-muted/40'}`}>
          <input {...getInputProps()} />
          {uploading ? `در حال بارگذاری ${uploading}…` : 'تصویر را اینجا بیندازید یا کلیک کنید (JPG، PNG، WebP یا GIF تا ۱۰ مگابایت)'}
        </div>
        <form className='flex gap-2' onSubmit={(e) => { e.preventDefault(); setPage(1); setQ(search.trim()); }}>
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder='جست‌وجو در رسانه‌ها…' />
          <Button type='submit' variant='outline' size='sm'>جست‌وجو</Button>
        </form>
        {error && <p className='text-destructive text-xs'>{error}</p>}
        <div className='grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6'>
          {items.map((it) => (
            <button key={it.id} type='button' onClick={() => onPick(it)} title={it.title || it.alt || `#${it.id}`} className='bg-muted focus:ring-primary group relative aspect-square overflow-hidden rounded-md border focus:ring-2 focus:outline-none'>
              <img src={it.thumbnail || it.url} alt={it.alt} loading='lazy' className='h-full w-full object-cover transition-transform duration-200 group-hover:scale-105' />
              <span className='absolute inset-x-0 bottom-0 truncate bg-black/60 px-1 py-0.5 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100'>{it.title || it.alt || `#${it.id}`}</span>
            </button>
          ))}
          {!loading && items.length === 0 && !error && <p className='text-muted-foreground col-span-full py-6 text-center text-xs'>تصویری پیدا نشد.</p>}
        </div>
        <div className='flex items-center justify-between text-xs'>
          <span className='text-muted-foreground'>{loading ? 'در حال بارگذاری…' : `${fa.format(total)} تصویر · صفحهٔ ${fa.format(page)} از ${fa.format(pages)}`}</span>
          <span className='flex gap-1'>
            <Button size='sm' variant='outline' disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>قبلی</Button>
            <Button size='sm' variant='outline' disabled={page >= pages || loading} onClick={() => setPage((p) => p + 1)}>بعدی</Button>
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
