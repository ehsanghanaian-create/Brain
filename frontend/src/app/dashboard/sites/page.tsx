import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { BackendError } from '@/components/seo-brain/backend-error';
import { Button } from '@/components/ui/button';
import { endpoints, settle } from '@/lib/api/client';
import Link from 'next/link';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'سایت‌ها' };

const MODE_FA = { manual: 'دستی', assisted: 'نیمه‌خودکار', autopilot: 'خودکار' } as const;

export default async function SitesPage() {
  const sites = await settle(endpoints.sites());
  return (
    <PageContainer
      pageTitle='سایت‌ها'
      pageDescription='هر سایت یک فضای کاری مستقل دارد (داده، گراف، حافظه، اتصال‌ها، حالت انتشار).'
      pageHeaderAction={
        <div className='flex gap-2'>
          <Button variant='secondary' nativeButton={false} render={<Link href='/dashboard/onboarding' />}>✨ راه‌اندازی سریع</Button>
          <Button nativeButton={false} render={<Link href='/dashboard/sites/new' />}>افزودن سایت</Button>
        </div>
      }
    >
      {sites.error ? (
        <BackendError error={sites.error} />
      ) : (
        <div className='rounded-md border'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>نام</TableHead>
                <TableHead>دامنه</TableHead>
                <TableHead>زبان / کشور</TableHead>
                <TableHead>Search Console</TableHead>
                <TableHead>حالت انتشار</TableHead>
                <TableHead>فضای کاری</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sites.data!.map((s) => (
                <TableRow key={s.site_id}>
                  <TableCell className='font-medium'>
                    <Link href={`/dashboard/sites/${s.site_id}`} className='hover:underline'>
                      {s.name}
                    </Link>
                    <div className='text-muted-foreground text-xs' dir='ltr'>
                      {s.site_id}
                    </div>
                  </TableCell>
                  <TableCell dir='ltr'>{s.canonical_url}</TableCell>
                  <TableCell dir='ltr'>
                    {s.language ?? '—'} / {s.country ?? '—'}
                  </TableCell>
                  <TableCell dir='ltr'>{s.gsc_property ?? <span className='text-muted-foreground'>متصل نیست</span>}</TableCell>
                  <TableCell>
                    <Badge variant={s.mode === 'manual' ? 'secondary' : 'default'}>{MODE_FA[s.mode]}</Badge>
                  </TableCell>
                  <TableCell dir='ltr' className='text-muted-foreground text-xs'>
                    {s.workspace_path ?? '—'}
                  </TableCell>
                </TableRow>
              ))}
              {sites.data!.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className='text-muted-foreground text-center'>
                    سایتی ثبت نشده است.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </PageContainer>
  );
}
