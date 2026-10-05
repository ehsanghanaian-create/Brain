'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api/client';
import { homeFor, type PanelRole } from '@/lib/panel-access';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api<{ user: { role: PanelRole } }>('/auth/login', {
        method: 'POST', json: { username, password }
      });
      router.replace(homeFor(result.user.role));
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'ورود انجام نشد');
    } finally {
      setBusy(false);
    }
  }
  return <main className='flex min-h-screen items-center justify-center bg-background p-4' dir='rtl'>
    <Card className='w-full max-w-md'>
      <CardHeader><CardTitle>ورود به SEO Brain</CardTitle><CardDescription>با نام کاربری و گذرواژهٔ اختصاصی خود وارد شوید.</CardDescription></CardHeader>
      <CardContent><form className='space-y-4' onSubmit={submit}>
        <label className='block space-y-1 text-sm'>نام کاربری<Input autoComplete='username' dir='ltr' required value={username} onChange={(e) => setUsername(e.target.value)} /></label>
        <label className='block space-y-1 text-sm'>گذرواژه<Input type='password' autoComplete='current-password' dir='ltr' required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <p role='alert' className='text-sm text-destructive'>{error}</p>}
        <Button className='w-full' type='submit' disabled={busy}>{busy ? 'در حال ورود…' : 'ورود'}</Button>
      </form></CardContent>
    </Card>
  </main>;
}
