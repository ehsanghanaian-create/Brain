import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'دربارهٔ SEO Brain',
  description: 'معرفی پنل چندسایتهٔ SEO Brain و اتصال اختیاری آن به سرویس‌های گوگل.',
  robots: { index: true, follow: true }
};

export default function OAuthInfoPage() {
  return (
    <main className='mx-auto max-w-3xl space-y-6 px-6 py-12 leading-8'>
      <h1 className='text-3xl font-bold'>SEO Brain</h1>
      <p>
        SEO Brain یک پنل خصوصی برای مدیریت سئو و تحلیل چند وب‌سایت است. مدیر سایت می‌تواند داده‌های خزش،
        مشکلات فنی و محتوایی، و گزارش‌های سرچ کنسول و گوگل آنالیتیکس سایت‌های دارای دسترسی را در یک پنل بررسی کند.
      </p>
      <p>
        اتصال حساب گوگل اختیاری است. پس از تأیید صاحب حساب، SEO Brain فقط داده‌های مربوط به دارایی‌هایی را می‌خواند
        که همان حساب اجازهٔ دسترسی به آن‌ها دارد. این اتصال فقط برای خواندن گزارش‌های Search Console و Google
        Analytics است و اجازهٔ تغییر در حساب گوگل را درخواست نمی‌کند.
      </p>
      <nav aria-label='پیوندهای اطلاعاتی' className='flex flex-wrap gap-5 text-primary underline'>
        <a href='/privacy'>حریم خصوصی</a>
        <a href='/terms'>شرایط استفاده</a>
        <a href='/dashboard/overview'>ورود به پنل</a>
      </nav>
      <p className='text-sm text-muted-foreground'>پشتیبانی: ehsanghanaian@gmail.com</p>
    </main>
  );
}
