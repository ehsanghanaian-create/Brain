import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div className='space-y-4'>
      <div className='flex gap-2'>
        <Skeleton className='h-9 w-52' />
        <Skeleton className='h-9 w-64' />
      </div>
      <Skeleton className='h-40 w-full' />
      <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className='h-24 w-full' />)}
      </div>
      <Skeleton className='h-64 w-full' />
    </div>
  );
}
