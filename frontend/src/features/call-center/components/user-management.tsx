'use client';

import { useCallback, useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Icons } from '@/components/icons';
import { callCenterApi, roleLabel, type PanelUser, type UserRole } from '../api';

export function UserManagement() {
  const [users, setUsers] = useState<PanelUser[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<UserRole>('call_center');
  const reduced = useReducedMotion();
  const load = useCallback(
    () =>
      callCenterApi
        .users()
        .then(setUsers)
        .catch((e) => setError(e instanceof Error ? e.message : String(e))),
    []
  );
  useEffect(() => {
    load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await callCenterApi.addUser({
        full_name: name.trim(),
        email: email.trim(),
        role,
        active: true
      });
      setName('');
      setEmail('');
      await load();
      toast.success('عضو تیم ثبت شد');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function patch(id: number, data: Partial<PanelUser>) {
    try {
      await callCenterApi.patchUser(id, data);
      await load();
      toast.success('تغییر ذخیره شد');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className='space-y-4'>
      <p className='rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs leading-6 text-foreground'>
        این صفحه دفتر اعضای تیم و نقش کاری آن‌هاست. در نسخهٔ فعلی SEO Brain ورود فردی و محدودسازی
        دسترسی بر اساس این نقش‌ها هنوز فعال نیست.
      </p>
      <div className='grid gap-5 xl:grid-cols-[1fr_2fr]'>
        <Card className='h-fit'>
          <CardHeader>
            <CardTitle>افزودن عضو تیم</CardTitle>
            <CardDescription>نقش‌ها برای ثبت و دسته‌بندی فعالیت تیم استفاده می‌شوند.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={add} className='space-y-4'>
              <label htmlFor='team-name' className='block space-y-1.5 text-sm font-medium'>
                نام و نام خانوادگی
                <Input
                  id='team-name'
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  minLength={2}
                  placeholder='نام عضو تیم'
                />
              </label>
              <label htmlFor='team-email' className='block space-y-1.5 text-sm font-medium'>
                ایمیل
                <Input
                  id='team-email'
                  type='email'
                  dir='ltr'
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder='name@example.com'
                />
              </label>
              <label htmlFor='team-role' className='block space-y-1.5 text-sm font-medium'>
                نقش
                <NativeSelect
                  id='team-role'
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                >
                  {Object.entries(roleLabel).map(([key, label]) => (
                    <NativeSelectOption key={key} value={key}>
                      {label}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
              {error && (
                <p role='alert' className='text-destructive text-sm'>
                  {error}
                </p>
              )}
              <Button type='submit' disabled={busy} className='w-full'>
                <Icons.add className='size-4' /> {busy ? 'در حال ثبت…' : 'افزودن کاربر'}
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>اعضای تیم</CardTitle>
            <CardDescription>
              {users.length} نفر · نقش و وضعیت هر فرد را از همین‌جا ویرایش کنید.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-2'>
            {users.map((user, i) => (
              <motion.div
                key={user.id}
                initial={reduced ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.035 }}
                className='flex flex-wrap items-center gap-3 rounded-xl border border-border/70 p-3 transition-colors hover:bg-muted/50'
              >
                <span className='bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl font-bold'>
                  {user.full_name.slice(0, 1)}
                </span>
                <span className='min-w-36 flex-1'>
                  <strong className='block text-sm'>{user.full_name}</strong>
                  <span className='text-muted-foreground block text-xs' dir='ltr'>
                    {user.email}
                  </span>
                </span>
                <NativeSelect
                  value={user.role}
                  onChange={(e) => patch(user.id, { role: e.target.value as UserRole })}
                  aria-label={`نقش ${user.full_name}`}
                  className='w-42'
                >
                  {Object.entries(roleLabel).map(([key, label]) => (
                    <NativeSelectOption key={key} value={key}>
                      {label}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                <Button
                  variant={user.active ? 'outline' : 'secondary'}
                  size='sm'
                  onClick={() => patch(user.id, { active: !user.active })}
                >
                  {user.active ? 'فعال' : 'غیرفعال'}
                </Button>
              </motion.div>
            ))}
            {!users.length && !error && (
              <p className='text-muted-foreground py-14 text-center text-sm'>
                هنوز عضوی ثبت نشده است.
              </p>
            )}
            {error && (
              <p role='alert' className='text-destructive py-4 text-sm'>
                {error}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
