import { describe, expect, it } from 'vitest';
import { parseArticleMarkdown } from '../components/article-preview';

describe('parseArticleMarkdown', () => {
  it('turns a Persian article into readable semantic blocks', () => {
    const blocks = parseArticleMarkdown(`# عنوان مقاله

پاراگراف اول
در همان بند.

## خدمات

- باتری
- خودروبر

> زمان رسیدن تضمینی نیست.

---`);

    expect(blocks).toEqual([
      { type: 'heading', level: 1, text: 'عنوان مقاله' },
      { type: 'paragraph', text: 'پاراگراف اول در همان بند.' },
      { type: 'heading', level: 2, text: 'خدمات' },
      { type: 'list', ordered: false, items: ['باتری', 'خودروبر'] },
      { type: 'quote', text: 'زمان رسیدن تضمینی نیست.' },
      { type: 'rule' }
    ]);
  });

  it('keeps ordered steps together', () => {
    expect(parseArticleMarkdown('1. ثبت درخواست\n2. بررسی موقعیت')).toEqual([
      { type: 'list', ordered: true, items: ['ثبت درخواست', 'بررسی موقعیت'] }
    ]);
  });
});
