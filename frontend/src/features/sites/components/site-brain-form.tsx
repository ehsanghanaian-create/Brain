'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, endpoints, type SiteMemory } from '@/lib/api/client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

const toLines = (a: unknown): string => (Array.isArray(a) ? a.map(String).join('\n') : '');
const fromLines = (s: string): string[] => s.split('\n').map((l) => l.trim()).filter(Boolean);

/**
 * Site Brain configuration — everything the AI orchestrator injects as site memory:
 * business rules · tone · audience · CTA rules · content rules · forbidden claims · successful patterns (read-only, learned).
 * Lists are edited one item per line; saved via PUT /sites/{id}/memory (partial update).
 */
export function SiteBrainForm({ siteId, initial }: { siteId: string; initial: SiteMemory }) {
  const router = useRouter();
  const tone = (initial.tone ?? {}) as Record<string, string>;
  const audience = (initial.audience ?? {}) as { segments?: string[]; pains?: string[]; intent_notes?: string };
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({
    business_rules: toLines(initial.business_rules),
    voice: tone.voice ?? 'formal',
    formality: tone.formality ?? 'respectful',
    person: tone.person ?? 'second-plural',
    language_notes: tone.language_notes ?? '',
    segments: toLines(audience.segments),
    pains: toLines(audience.pains),
    intent_notes: audience.intent_notes ?? '',
    cta_rules: toLines(initial.cta_rules),
    content_rules: toLines(initial.content_rules),
    forbidden_claims: toLines(initial.forbidden_claims)
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));

  async function save() {
    setBusy(true);
    try {
      await endpoints.putMemory(siteId, {
        business_rules: fromLines(f.business_rules),
        tone: { voice: f.voice, formality: f.formality, person: f.person, language_notes: f.language_notes, language: tone.language ?? 'fa-IR' },
        audience: { segments: fromLines(f.segments), pains: fromLines(f.pains), intent_notes: f.intent_notes },
        cta_rules: fromLines(f.cta_rules),
        content_rules: fromLines(f.content_rules),
        forbidden_claims: fromLines(f.forbidden_claims)
      });
      toast.success('مغز سایت ذخیره شد');
      router.refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? `${e.message} (${e.code})` : String(e));
    } finally {
      setBusy(false);
    }
  }

  const patterns = (initial.successful_patterns ?? []) as { pattern?: string; evidence?: string; source?: string; created_at?: string }[];

  return (
    <div className='grid gap-4 lg:grid-cols-2'>
      <Card>
        <CardHeader>
          <CardTitle>قواعد کسب‌وکار</CardTitle>
          <CardDescription>هر خط یک قاعده. مثال: «فقط خدمات امداد خودرو در تهران و حومه»</CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea rows={6} value={f.business_rules} onChange={set('business_rules')} placeholder={'فقط خدمات امداد خودرو ارائه می‌دهیم\nقیمت‌ها اعلام نمی‌شوند؛ تماس بگیرید'} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>لحن</CardTitle>
          <CardDescription>صدا و رسمیت متن‌هایی که هوش مصنوعی برای این سایت تولید می‌کند</CardDescription>
        </CardHeader>
        <CardContent className='grid gap-3'>
          <div className='grid grid-cols-3 gap-2'>
            <div className='grid gap-1.5'>
              <Label>صدا</Label>
              <NativeSelect value={f.voice} onChange={set('voice')}>
                <NativeSelectOption value='formal'>رسمی</NativeSelectOption>
                <NativeSelectOption value='friendly'>صمیمی</NativeSelectOption>
                <NativeSelectOption value='expert'>کارشناسی</NativeSelectOption>
                <NativeSelectOption value='urgent'>فوری / اضطراری</NativeSelectOption>
              </NativeSelect>
            </div>
            <div className='grid gap-1.5'>
              <Label>رسمیت</Label>
              <NativeSelect value={f.formality} onChange={set('formality')}>
                <NativeSelectOption value='respectful'>محترمانه</NativeSelectOption>
                <NativeSelectOption value='neutral'>خنثی</NativeSelectOption>
                <NativeSelectOption value='casual'>خودمانی</NativeSelectOption>
              </NativeSelect>
            </div>
            <div className='grid gap-1.5'>
              <Label>مخاطب‌قراردادن</Label>
              <NativeSelect value={f.person} onChange={set('person')}>
                <NativeSelectOption value='second-plural'>شما</NativeSelectOption>
                <NativeSelectOption value='second-singular'>تو</NativeSelectOption>
                <NativeSelectOption value='third'>سوم‌شخص</NativeSelectOption>
              </NativeSelect>
            </div>
          </div>
          <div className='grid gap-1.5'>
            <Label>یادداشت‌های زبانی</Label>
            <Input value={f.language_notes} onChange={set('language_notes')} placeholder='نیم‌فاصله رعایت شود؛ از واژه‌های انگلیسی مدل خودرو استفاده شود' />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>مخاطب</CardTitle>
          <CardDescription>بخش‌های مخاطب و دردهای اصلی آن‌ها (هر خط یک مورد)</CardDescription>
        </CardHeader>
        <CardContent className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label>بخش‌های مخاطب</Label>
            <Textarea rows={3} value={f.segments} onChange={set('segments')} placeholder={'مالکان خودروهای MVM و چری\nرانندگان در جاده‌های اطراف تهران'} />
          </div>
          <div className='grid gap-1.5'>
            <Label>دردها / نیازها</Label>
            <Textarea rows={3} value={f.pains} onChange={set('pains')} placeholder={'خرابی ناگهانی در جاده\nنبود قطعه اصلی'} />
          </div>
          <div className='grid gap-1.5'>
            <Label>یادداشت اینتنت</Label>
            <Input value={f.intent_notes} onChange={set('intent_notes')} placeholder='بیشتر جست‌وجوها فوری و موبایلی هستند' />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>قواعد CTA</CardTitle>
          <CardDescription>چطور و کجا دعوت به اقدام بیاید</CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea rows={5} value={f.cta_rules} onChange={set('cta_rules')} placeholder={'شماره تماس در پاراگراف اول\nدکمه تماس در پایان هر بخش'} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>قواعد محتوا</CardTitle>
          <CardDescription>ساختار، طول، سرفصل‌ها، اسکیما…</CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea rows={5} value={f.content_rules} onChange={set('content_rules')} placeholder={'یک H1 در هر صفحه\nحداقل ۷۰۰ کلمه برای مقالات خدماتی\nFAQ با اسکیما FAQPage'} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>ادعاهای ممنوع</CardTitle>
          <CardDescription>مواردی که هرگز نباید در محتوا بیاید (اعتبارسنجی خروجی AI را رد می‌کند)</CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea rows={5} value={f.forbidden_claims} onChange={set('forbidden_claims')} placeholder={'ارزان‌ترین\nتضمین ۱۰۰٪\nنمایندگی رسمی (مگر واقعاً باشیم)'} />
        </CardContent>
      </Card>

      <Card className='lg:col-span-2'>
        <CardHeader>
          <CardTitle>الگوهای موفق (یادگرفته‌شده)</CardTitle>
          <CardDescription>فقط پس از اعتبارسنجی نتایج توسط ارکستریتور ثبت می‌شوند؛ ویرایش دستی نمی‌شوند.</CardDescription>
        </CardHeader>
        <CardContent>
          {patterns.length === 0 ? (
            <p className='text-muted-foreground text-sm'>هنوز الگویی ثبت نشده است.</p>
          ) : (
            <ul className='space-y-1 text-sm'>
              {patterns.slice(-10).reverse().map((p, i) => (
                <li key={i} className='rounded border p-2'>
                  <div>{p.pattern}</div>
                  <div className='text-muted-foreground text-xs' dir='ltr'>
                    {p.source} · {p.created_at} {p.evidence ? `· ${p.evidence}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className='lg:col-span-2 flex items-center justify-between'>
        <p className='text-muted-foreground text-xs'>آخرین ذخیره: {initial.updated_at ?? '—'}</p>
        <Button onClick={save} disabled={busy}>{busy ? 'در حال ذخیره…' : 'ذخیره مغز سایت'}</Button>
      </div>
    </div>
  );
}
