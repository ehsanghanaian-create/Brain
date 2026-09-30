import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'حریم خصوصی SEO Brain',
  description: 'نحوهٔ دسترسی، استفاده و نگهداری داده‌های حساب گوگل در SEO Brain.',
  robots: { index: true, follow: true }
};

export default function PrivacyPage() {
  return (
    <main className='mx-auto max-w-3xl space-y-6 px-6 py-12 leading-8'>
      <h1 className='text-3xl font-bold'>حریم خصوصی SEO Brain</h1>
      <p>آخرین به‌روزرسانی: ۳۰ سپتامبر ۲۰۲۶</p>
      <section>
        <h2 className='text-xl font-semibold'>داده‌هایی که با اتصال گوگل دریافت می‌شود</h2>
        <p>
          با رضایت صاحب حساب، نشانی ایمیل حساب متصل، شناسهٔ دارایی‌های مجاز، داده‌های عملکرد جستجو از Google Search
          Console و گزارش‌های ترافیک Google Analytics دریافت می‌شود. در صورت استفاده از قابلیت Google Ads، شناسهٔ
          حساب و داده‌های لازم برای بررسی و اعمال محدودیت IP نیز پردازش می‌شود.
        </p>
      </section>
      <section>
        <h2 className='text-xl font-semibold'>هدف استفاده و اشتراک‌گذاری</h2>
        <p>
          این داده‌ها برای نمایش گزارش، شناسایی مشکلات و پیشنهاد اقدام برای همان سایت‌های متصل استفاده می‌شود. اعمال
          تغییر در Google Ads نیازمند اقدام صریح مدیر است. در صورت استفاده از قابلیت‌های هوش مصنوعی، داده‌های مرتبط
          با درخواست تحلیل ممکن است به ارائه‌دهندهٔ مدل انتخاب‌شده در تنظیمات ارسال شود. داده‌های حساب گوگل برای
          تبلیغات شخصی‌سازی‌شده فروخته یا استفاده نمی‌شود.
        </p>
      </section>
      <section>
        <h2 className='text-xl font-semibold'>نگهداری، امنیت و حذف</h2>
        <p>
          توکن اتصال گوگل در فضای رمزگذاری‌شدهٔ سرور نگهداری می‌شود و دسترسی به گزارش‌ها به پنل خصوصی محدود است.
          قطع اتصال، توکن ذخیره‌شده را حذف می‌کند و درخواست لغو مجوز را به گوگل می‌فرستد. گزارش‌های تاریخی می‌توانند
          پس از قطع اتصال باقی بمانند تا زمانی که مدیر داده‌های سایت را حذف کند یا درخواست حذف بدهد.
        </p>
      </section>
      <section>
        <h2 className='text-xl font-semibold'>کنترل و تماس</h2>
        <p>
          مدیر می‌تواند از بخش اتصال‌های پنل، حساب گوگل را قطع کند و برای حذف داده‌های سایت از گزینهٔ حذف سایت
          استفاده کند. برای پرسش دربارهٔ داده‌ها یا درخواست حذف، به{' '}
          <a className='text-primary underline' href='mailto:ehsanghanaian@gmail.com'>ehsanghanaian@gmail.com</a>{' '}
          پیام بدهید.
        </p>
      </section>
      <a className='text-primary underline' href='/oauth-info'>دربارهٔ SEO Brain</a>
    </main>
  );
}
