'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { api } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

type Profile = { username: string; full_name: string; email: string | null; role: string };

export function ProfileEditor() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { void api<Profile>('/auth/me').then(setProfile).catch(() => toast.error('پروفایل دریافت نشد')); }, []);
  async function save() {
    if (!profile || !password) { toast.error('رمز فعلی را وارد کنید'); return; }
    setBusy(true);
    try {
      const updated = await api<Profile>('/auth/me', { method: 'PATCH', json: {
        username: profile.username, full_name: profile.full_name, email: profile.email,
        current_password: password, ...(newPassword ? { new_password: newPassword } : {})
      } });
      setProfile(updated); setPassword(''); setNewPassword(''); toast.success('پروفایل ذخیره شد');
    } catch (error) { toast.error(error instanceof Error ? error.message : 'ذخیره انجام نشد'); }
    finally { setBusy(false); }
  }
  return <Card className='mx-auto max-w-xl' dir='rtl'><CardHeader><CardTitle>پروفایل من</CardTitle></CardHeader><CardContent className='space-y-4'>
    {profile && <>
      <label className='block space-y-1 text-sm'>نام نمایشی<Input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} /></label>
      <label className='block space-y-1 text-sm'>نام کاربری<Input dir='ltr' value={profile.username} onChange={(e) => setProfile({ ...profile, username: e.target.value })} /></label>
      <label className='block space-y-1 text-sm'>ایمیل<Input dir='ltr' type='email' value={profile.email || ''} onChange={(e) => setProfile({ ...profile, email: e.target.value || null })} /></label>
      <label className='block space-y-1 text-sm'>رمز فعلی<Input type='password' autoComplete='current-password' value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <label className='block space-y-1 text-sm'>رمز جدید (اختیاری)<Input type='password' autoComplete='new-password' value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label>
      <Button disabled={busy || !password} onClick={() => void save()}>{busy ? 'در حال ذخیره…' : 'ذخیرهٔ تغییرات'}</Button>
    </>}
  </CardContent></Card>;
}
