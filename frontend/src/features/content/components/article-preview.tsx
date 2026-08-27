'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ContentDraft } from '@/lib/api/client';
import { IconCheck, IconCode, IconCopy, IconEye, IconFileText } from '@tabler/icons-react';
import { useMemo, useState } from 'react';

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'rule' };

export function parseArticleMarkdown(source: string): Block[] {
  const lines = source.replace(/\r/g, '').split('\n');
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: Extract<Block, { type: 'list' }> | null = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push({ type: 'paragraph', text: paragraph.join(' ').trim() });
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    blocks.push(list);
    list = null;
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    if (/^---+$/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'rule' });
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'quote', text: quote[1] });
      continue;
    }
    const unordered = line.match(/^[-*+]\s+(.+)$/);
    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const isOrdered = !!ordered;
      if (!list || list.ordered !== isOrdered) flushList();
      if (!list) list = { type: 'list', ordered: isOrdered, items: [] };
      list.items.push((ordered ?? unordered)![1]);
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return blocks;
}

function InlineText({ text }: { text: string }) {
  const chunks = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g).filter(Boolean);
  return <>{chunks.map((chunk, index) => {
    if (chunk.startsWith('**') && chunk.endsWith('**')) return <strong key={index}>{chunk.slice(2, -2)}</strong>;
    if (chunk.startsWith('`') && chunk.endsWith('`')) return <code key={index} className='bg-muted rounded px-1 py-0.5 text-[0.9em]' dir='ltr'>{chunk.slice(1, -1)}</code>;
    const link = chunk.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) return <a key={index} href={link[2]} target='_blank' rel='noreferrer' className='text-primary underline underline-offset-4'>{link[1]}</a>;
    return <span key={index}>{chunk}</span>;
  })}</>;
}

export function ArticlePreview({ draft }: { draft: ContentDraft }) {
  const [mode, setMode] = useState<'reader' | 'source'>('reader');
  const [copied, setCopied] = useState(false);
  const blocks = useMemo(() => parseArticleMarkdown(draft.body ?? ''), [draft.body]);
  const readingMinutes = Math.max(1, Math.ceil(draft.word_count / 220));

  async function copyArticle() {
    await navigator.clipboard.writeText(draft.body ?? '');
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <section className='overflow-hidden rounded-xl border bg-background shadow-sm'>
      <header className='border-b bg-muted/25 p-4 sm:p-5'>
        <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
          <div className='min-w-0 space-y-2'>
            <div className='flex flex-wrap items-center gap-1.5'>
              <Badge variant='secondary'><IconFileText className='size-3.5' /> پیش‌نویس نسخه {draft.version}</Badge>
              <Badge variant='outline'>{draft.word_count.toLocaleString('fa-IR')} کلمه</Badge>
              <Badge variant='outline'>حدود {readingMinutes.toLocaleString('fa-IR')} دقیقه مطالعه</Badge>
              <Badge variant={draft.review_status === 'ready' ? 'default' : 'outline'}>{draft.review_status === 'ready' ? 'آماده بررسی' : 'نیازمند بازبینی'}</Badge>
            </div>
            <h2 className='text-balance text-xl font-bold leading-8 sm:text-2xl'>{draft.title || draft.structure.h1[0] || 'پیش‌نویس بدون عنوان'}</h2>
            {draft.meta_description && <p className='text-muted-foreground max-w-3xl text-sm leading-6'>{draft.meta_description}</p>}
          </div>
          <div className='flex shrink-0 items-center gap-1 rounded-lg border bg-background p-1'>
            <Button size='sm' variant={mode === 'reader' ? 'secondary' : 'ghost'} onClick={() => setMode('reader')}><IconEye /> نمای مقاله</Button>
            <Button size='sm' variant={mode === 'source' ? 'secondary' : 'ghost'} onClick={() => setMode('source')}><IconCode /> Markdown</Button>
            <Button size='sm' variant='ghost' onClick={copyArticle}>{copied ? <IconCheck /> : <IconCopy />}{copied ? 'کپی شد' : 'کپی'}</Button>
          </div>
        </div>
      </header>

      {mode === 'source' ? (
        <pre className='max-h-[65vh] overflow-auto p-4 text-xs leading-6 whitespace-pre-wrap sm:p-6' dir='auto'>{draft.body}</pre>
      ) : (
        <article className='mx-auto max-h-[65vh] max-w-4xl overflow-y-auto px-5 py-7 text-[15px] leading-8 sm:px-10 sm:py-9 sm:text-base' dir='rtl'>
          {blocks.map((block, index) => {
            if (block.type === 'rule') return <hr key={index} className='my-7' />;
            if (block.type === 'heading') {
              const cls = block.level === 1 ? 'mt-2 mb-5 text-2xl font-extrabold leading-10' : block.level === 2 ? 'mt-9 mb-3 border-r-4 border-primary pr-3 text-xl font-bold leading-8' : 'mt-6 mb-2 text-lg font-semibold';
              return <div key={index} role='heading' aria-level={Math.min(block.level, 6)} className={cls}><InlineText text={block.text} /></div>;
            }
            if (block.type === 'quote') return <blockquote key={index} className='my-5 rounded-lg border-r-4 border-sky-500 bg-sky-500/5 px-4 py-3 text-sm leading-7'><InlineText text={block.text} /></blockquote>;
            if (block.type === 'list') {
              const Tag = block.ordered ? 'ol' : 'ul';
              return <Tag key={index} className={`my-4 space-y-2 pr-6 ${block.ordered ? 'list-decimal' : 'list-disc'}`}>{block.items.map((item, itemIndex) => <li key={itemIndex}><InlineText text={item} /></li>)}</Tag>;
            }
            return <p key={index} className='my-4 text-pretty text-foreground/90'><InlineText text={block.text} /></p>;
          })}
        </article>
      )}
    </section>
  );
}
