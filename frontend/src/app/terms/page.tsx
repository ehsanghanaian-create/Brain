import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'شرایط استفاده از SEO Brain',
  description: 'شرایط استفاده از پنل SEO Brain و اتصال حساب گوگل.',
  robots: { index: true, follow: true }
};

export default function TermsPage() {
  return (
    <main className='mx-auto max-w-3xl space-y-6 px-6 py-12 leading-8'>
      <h1 className='text-3xl font-bold'>شرایط استفاده از SEO Brain</h1>
      <p>آخرین به‌روزرسانی: ۳۰ سپتامبر ۲۰۲۶</p>
      <p>
        استفاده از پنل و اتصال حساب‌های Google Search Console، Google Analytics و Google Ads فقط برای سایت‌ها و
        حساب‌هایی مجاز است که کاربر اختیار مدیریت آن‌ها را دارد. اتصال حساب گوگل اختیاری است و از بخش اتصال‌ها قابل
        قطع کردن است.
      </p>
      <p>
        گزارش‌ها و پیشنهادهای SEO Brain ابزار تصمیم‌گیری هستند و رتبه یا نتیجهٔ مشخصی در موتور جستجو را تضمین
        نمی‌کنند. مدیر باید دامنهٔ اثر تغییرات پیشنهادی را پیش از اجرا بررسی کند. تغییرات Google Ads تنها پس از اقدام
        صریح مدیر اعمال می‌شود.
      </p>
      <p>
        برای پرسش دربارهٔ دسترسی یا داده‌های ذخیره‌شده، با{' '}
        <a className='text-primary underline' href='mailto:ehsanghanaian@gmail.com'>ehsanghanaian@gmail.com</a>{' '}
        تماس بگیرید.
      </p>
      <nav aria-label='پیوندهای اطلاعاتی' className='flex flex-wrap gap-5 text-primary underline'>
        <a href='/oauth-info'>دربارهٔ SEO Brain</a>
        <a href='/privacy'>حریم خصوصی</a>
      </nav>
    </main>
  );
}
