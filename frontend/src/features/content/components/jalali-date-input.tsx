'use client';

import { Input } from '@/components/ui/input';
import { jalaliNumeric, parseJalali } from '@/features/content/constants';
import { useEffect, useState } from 'react';

/** ورودی تاریخ شمسی (۱۴۰۵/۰۶/۰۵) — مقدار API همان ISO میلادی می‌ماند؛ فقط نمایش/تایپ شمسی است.
 * ارقام فارسی/لاتین و جداکننده / - . پذیرفته می‌شود؛ تاریخ نامعتبر قرمز می‌شود و ذخیره نمی‌شود. */
export function JalaliDateInput({ value, onChange, className, placeholder = '۱۴۰۵/۰۶/۰۵', clearable = true, ...rest }:
  { value: string | null | undefined; onChange: (iso: string | null) => void; className?: string; placeholder?: string; clearable?: boolean } & Record<string, unknown>) {
  const [text, setText] = useState(jalaliNumeric(value));
  const [bad, setBad] = useState(false);
  useEffect(() => { setText(jalaliNumeric(value)); setBad(false); }, [value]);
  function commit() {
    const t = text.trim();
    if (!t) { setBad(false); if (clearable && value) onChange(null); return; }
    const isoDay = parseJalali(t);
    if (isoDay) { setBad(false); setText(jalaliNumeric(isoDay)); if (isoDay !== value) onChange(isoDay); }
    else setBad(true);
  }
  return (
    <Input value={text} dir='ltr' inputMode='numeric' placeholder={placeholder} title='تاریخ شمسی: سال/ماه/روز'
      aria-invalid={bad || undefined} className={`${className ?? ''} ${bad ? 'border-destructive' : ''}`.trim()}
      onChange={(e) => setText(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.currentTarget as HTMLInputElement).blur(); }} {...rest} />
  );
}
