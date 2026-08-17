import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import type { ApiError } from '@/lib/api/client';

export function BackendError({ error, title = 'خطا در ارتباط با بک‌اند' }: { error: ApiError; title?: string }) {
  const unreachable = error.status === 0 || error.status === 503;
  return (
    <Alert variant='destructive'>
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <div>{error.message}</div>
        <div className='text-xs opacity-80' dir='ltr'>
          {error.code} · HTTP {error.status || '—'} · request_id {error.requestId}
        </div>
        {unreachable && (
          <div className='mt-1 text-xs'>
            بک‌اند را اجرا کنید: <code dir='ltr'>python backend\cli\api.py</code>
          </div>
        )}
      </AlertDescription>
    </Alert>
  );
}
