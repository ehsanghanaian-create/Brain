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
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('call_center');
  const [resetId, setResetId] = useState<number | null>(null);
  const [resetUsername, setResetUsername] = useState('');
  const [resetPassword, setResetPassword] = useState('');
  const [audit, setAudit] = useState<Awaited<ReturnType<typeof callCenterApi.audit>> | null>(null);
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
        username: username.trim(),
        password,
        role,
        active: true
      });
      setName('');
      setEmail('');
      setUsername('');
      setPassword('');
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
  async function saveCredentials() {
    if (resetId === null) return;
    try {
      const passwordChanged = Boolean(resetPassword);
      await callCenterApi.patchUser(resetId, { username: resetUsername.trim(), ...(resetPassword ? { password: resetPassword } : {}) });
      setResetId(null);
      setResetPassword('');
      await load();
      toast.success(passwordChanged ? 'اطلاعات ورود ذخیره شد؛ نشست‌های قبلی کاربر بسته شدند' : 'نام کاربری ذخیره شد؛ نشست‌های قبلی کاربر بسته شدند');
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : String(cause)); }
  }

  return (
    <div className='space-y-4'>
      <p className='rounded-xl border border-primary/30 bg-primary/10 px-4 py-3 text-xs leading-6 text-foreground'>
        هر کاربر با نام کاربری و گذرواژهٔ اختصاصی وارد می‌شود. مدیر دسترسی کامل دارد؛ تحلیل‌گر فقط گزارش‌ها را می‌بیند و اپراتور کال‌سنتر فقط صفحهٔ تماس‌ها را.
      </p>
      <div className='grid gap-5 xl:grid-cols-[1fr_2fr]'>
        <Card className='h-fit'>
          <CardHeader>
            <CardTitle>افزودن عضو تیم</CardTitle>
            <CardDescription>نام کاربری، گذرواژه و سطح دسترسی را برای هر عضو مشخص کنید.</CardDescription>
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
              <label htmlFor='team-username' className='block space-y-1.5 text-sm font-medium'>
                نام کاربری
                <Input id='team-username' dir='ltr' autoComplete='off' minLength={3} required value={username} onChange={(e) => setUsername(e.target.value)} placeholder='username' />
              </label>
              <label htmlFor='team-password' className='block space-y-1.5 text-sm font-medium'>
                گذرواژه (حداقل ۱۲ نویسه)
                <Input id='team-password' type='password' dir='ltr' autoComplete='new-password' minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} />
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
                  <span className='text-muted-foreground block text-xs' dir='ltr'>@{user.username || 'بدون نام کاربری'}</span>
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
                <Button variant='outline' size='sm' onClick={() => { setResetId(resetId === user.id ? null : user.id); setResetUsername(user.username || ''); setResetPassword(''); }}>اطلاعات ورود</Button>
                {resetId === user.id && <div className='grid w-full gap-2 rounded-lg bg-muted p-3 sm:grid-cols-[1fr_1fr_auto]'>
                  <Input aria-label={`نام کاربری ${user.full_name}`} dir='ltr' value={resetUsername} onChange={(e) => setResetUsername(e.target.value)} />
                  <Input aria-label={`گذرواژه جدید ${user.full_name}`} type='password' dir='ltr' minLength={12} placeholder='گذرواژه جدید (اختیاری)' value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} />
                  <Button onClick={saveCredentials}>ذخیره</Button>
                </div>}
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
      <Card><CardHeader><CardTitle>گزارش فعالیت کاربران</CardTitle><CardDescription>زمان، کاربر، مسیر و فیلدهای تغییرکرده؛ گذرواژه در لاگ ذخیره نمی‌شود.</CardDescription></CardHeader>
        <CardContent className='space-y-3'><Button variant='outline' onClick={async () => { try { setAudit(await callCenterApi.audit()); } catch (cause) { toast.error(cause instanceof Error ? cause.message : String(cause)); } }}>نمایش آخرین فعالیت‌ها</Button>
          {audit && <div className='overflow-x-auto'><table className='w-full min-w-[700px] text-right text-xs'><thead><tr className='border-b'><th className='p-2'>زمان</th><th>کاربر</th><th>اقدام</th><th>مسیر</th><th>فیلدها</th></tr></thead><tbody>{audit.items.map((item) => <tr key={item.id} className='border-b'><td className='p-2'>{new Date(item.created_at).toLocaleString('fa-IR')}</td><td className='p-2'>{item.actor_username}</td><td className='p-2'>{item.method}</td><td className='p-2' dir='ltr'>{item.path}</td><td className='p-2'>{(JSON.parse(item.changed_fields) as string[]).join('، ') || '—'}</td></tr>)}</tbody></table></div>}
        </CardContent></Card>
    </div>
  );
}
