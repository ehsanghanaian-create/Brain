import { Skeleton } from '@/components/ui/skeleton';

export default function DashboardLoading() {
  return (
    <div className='flex flex-1 flex-col gap-4 px-4 py-5 md:px-6' role='status' aria-label='در حال بارگذاری'>
      <div className='space-y-2'><Skeleton className='h-8 w-48' /><Skeleton className='h-4 w-80 max-w-full' /></div>
      <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className='h-28 rounded-xl' />)}</div>
      <div className='grid gap-4 xl:grid-cols-[1.4fr_1fr]'><Skeleton className='h-72 rounded-xl' /><Skeleton className='h-72 rounded-xl' /></div>
    </div>
  );
}
