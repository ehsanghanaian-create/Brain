'use client';

import { useEffect, useId, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { IconArrowRight, IconHeadset, IconPlus, IconX } from '@tabler/icons-react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogHeader
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ApiError } from '@/lib/api/client';
import { supportApi, type SupportDetail, type SupportStatus } from './support-api';
import panel from './quick-access-dialog.module.css';
import styles from './support-dialog.module.css';

const statusFa: Record<SupportStatus, string> = {
  open: 'در انتظار رسیدگی',
  waiting: 'پاسخ داده شده',
  closed: 'بسته‌شده'
};
const date = (value: string) =>
  new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'Asia/Tehran'
  }).format(new Date(value));

export function SupportDialog({
  open,
  onOpenChange,
  accountName,
  siteId,
  sites,
  pathname
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  accountName: string | null;
  siteId: string;
  sites: { site_id: string; name: string }[];
  pathname: string;
}) {
  const fieldId = useId();
  const queryClient = useQueryClient();
  const [view, setView] = useState<'list' | 'new' | 'thread'>('list');
  const [filter, setFilter] = useState('all');
  const [offset, setOffset] = useState(0);
  const [id, setId] = useState<number | null>(null);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [category, setCategory] = useState('problem');
  const [relatedSite, setRelatedSite] = useState(siteId);
  const [asSupport, setAsSupport] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['support-tickets', accountName, filter, offset],
    queryFn: () => supportApi.list(filter, offset),
    enabled: open,
    refetchInterval: open ? 15000 : false
  });
  const detail = useQuery({
    queryKey: ['support-ticket', accountName, id],
    queryFn: () => supportApi.detail(id!),
    enabled: open && view === 'thread' && id !== null,
    refetchInterval: open && view === 'thread' ? 15000 : false
  });
  useEffect(() => {
    if (open) {
      setView('list');
      setMessage('');
      setError('');
    }
  }, [open]);
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'ثبت درخواست انجام نشد؛ دوباره تلاش کنید.');
  const updated = (ticket: SupportDetail) => {
    queryClient.setQueryData(['support-ticket', accountName, ticket.id], ticket);
    void queryClient.invalidateQueries({ queryKey: ['support-tickets', accountName] });
  };
  const toList = () => {
    setView('list');
    setError('');
    setMessage('');
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent
        data-support-dialog
        className={`${panel.dialog} ${styles.dialog}`}
        showCloseButton={false}
        dir='rtl'
      >
        <DialogHeader className={panel.header}>
          <div>
            <DialogTitle>{view === 'new' ? 'ثبت درخواست پشتیبانی' : 'پشتیبانی'}</DialogTitle>
            <DialogDescription>
              درخواست، پاسخ‌ها و وضعیت رسیدگی را از همین بخش پیگیری کنید.
            </DialogDescription>
          </div>
          <Button
            variant='ghost'
            size='icon'
            aria-label='بستن پشتیبانی'
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            <IconX />
          </Button>
        </DialogHeader>
        <div className={panel.body}>
          {error && (
            <p role='alert' className={styles.error}>
              {error}
            </p>
          )}
          {view === 'list' && (
            <>
              <div className={styles.toolbar}>
                <h3>{list.data?.is_staff ? 'درخواست‌های تیم' : 'درخواست‌های من'}</h3>
                <Button
                  onClick={() => {
                    setView('new');
                    setSubject('');
                    setMessage('');
                    setRelatedSite(siteId);
                    setError('');
                  }}
                >
                  <IconPlus size={17} />
                  ثبت درخواست
                </Button>
              </div>
              <NativeSelect
                aria-label='فیلتر وضعیت درخواست‌ها'
                value={filter}
                onChange={(event) => {
                  setFilter(event.target.value);
                  setOffset(0);
                }}
                className='mb-4 w-full'
              >
                <NativeSelectOption value='all'>همهٔ درخواست‌ها</NativeSelectOption>
                {Object.entries(statusFa).map(([value, label]) => (
                  <NativeSelectOption key={value} value={value}>
                    {label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              {list.isLoading && <p role='status'>در حال دریافت درخواست‌ها…</p>}
              {list.isError && (
                <div role='alert' className={styles.error}>
                  <p>
                    {list.error instanceof ApiError
                      ? list.error.message
                      : 'دریافت درخواست‌ها انجام نشد.'}
                  </p>
                  <Button variant='outline' onClick={() => void list.refetch()}>
                    تلاش دوباره
                  </Button>
                </div>
              )}
              {list.isSuccess && list.data.items.length === 0 && (
                <div className={styles.empty}>
                  <IconHeadset size={32} />
                  <p>درخواستی در این وضعیت ثبت نشده است.</p>
                </div>
              )}
              <div className={styles.tickets}>
                {list.data?.items.map((ticket) => (
                  <button
                    type='button'
                    key={ticket.id}
                    onClick={() => {
                      setId(ticket.id);
                      setView('thread');
                      setError('');
                      setMessage('');
                      setAsSupport(!!list.data?.is_staff && ticket.owner !== accountName);
                    }}
                  >
                    <div>
                      <strong>{ticket.subject}</strong>
                      <span>{statusFa[ticket.status]}</span>
                    </div>
                    <small>
                      <b dir='ltr'>{ticket.reference}</b> · {date(ticket.updated_at)}
                      {list.data.is_staff ? ` · ${ticket.owner}` : ''}
                    </small>
                  </button>
                ))}
              </div>
              {list.data && list.data.total > 50 && (
                <nav className={styles.actions} aria-label='صفحه‌های درخواست‌های پشتیبانی'>
                  <Button
                    variant='outline'
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - 50))}
                  >
                    قبلی
                  </Button>
                  <span className='text-muted-foreground text-xs'>
                    صفحهٔ {(offset / 50 + 1).toLocaleString('fa-IR')} از{' '}
                    {Math.ceil(list.data.total / 50).toLocaleString('fa-IR')}
                  </span>
                  <Button
                    variant='outline'
                    disabled={offset + 50 >= list.data.total}
                    onClick={() => setOffset(offset + 50)}
                  >
                    بعدی
                  </Button>
                </nav>
              )}
            </>
          )}
          {view === 'new' && (
            <form
              className={styles.form}
              aria-busy={busy}
              onSubmit={async (event) => {
                event.preventDefault();
                setBusy(true);
                setError('');
                try {
                  const ticket = await supportApi.create({
                    subject: subject.trim(),
                    message: message.trim(),
                    category,
                    site_id: relatedSite || null,
                    context_path: pathname
                  });
                  updated(ticket);
                  setId(ticket.id);
                  setView('thread');
                  setMessage('');
                  setSubject('');
                  setAsSupport(false);
                } catch (e) {
                  fail(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label htmlFor={`${fieldId}-subject`}>
                عنوان درخواست
                <Input
                  id={`${fieldId}-subject`}
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  required
                  minLength={3}
                  maxLength={160}
                  disabled={busy}
                  className='h-11'
                />
              </label>
              <div className={styles.fields}>
                <label htmlFor={`${fieldId}-category`}>
                  موضوع
                  <NativeSelect
                    id={`${fieldId}-category`}
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    disabled={busy}
                    className='w-full'
                  >
                    <NativeSelectOption value='problem'>گزارش مشکل</NativeSelectOption>
                    <NativeSelectOption value='question'>پرسش</NativeSelectOption>
                    <NativeSelectOption value='idea'>پیشنهاد بهبود</NativeSelectOption>
                  </NativeSelect>
                </label>
                <label htmlFor={`${fieldId}-site`}>
                  سایت مرتبط
                  <NativeSelect
                    id={`${fieldId}-site`}
                    value={relatedSite}
                    onChange={(e) => setRelatedSite(e.target.value)}
                    disabled={busy}
                    className='w-full'
                  >
                    <NativeSelectOption value=''>خود داشبورد</NativeSelectOption>
                    {sites.map((site) => (
                      <NativeSelectOption key={site.site_id} value={site.site_id}>
                        {site.name}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </label>
              </div>
              <label htmlFor={`${fieldId}-description`}>
                توضیحات درخواست
                <Textarea
                  id={`${fieldId}-description`}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  required
                  minLength={5}
                  maxLength={5000}
                  rows={5}
                  disabled={busy}
                  placeholder='چه کاری انجام دادید و چه مشکلی پیش آمد؟'
                />
              </label>
              <div className={styles.actions}>
                <Button type='button' variant='ghost' disabled={busy} onClick={toList}>
                  <IconArrowRight size={16} />
                  بازگشت
                </Button>
                <Button type='submit' disabled={busy}>
                  {busy ? 'در حال ثبت…' : 'ثبت درخواست پشتیبانی'}
                </Button>
              </div>
            </form>
          )}
          {view === 'thread' && (
            <>
              <Button variant='ghost' onClick={toList} className='mb-3'>
                <IconArrowRight size={16} />
                فهرست درخواست‌ها
              </Button>
              {detail.isLoading && <p role='status'>در حال دریافت گفتگو…</p>}
              {detail.isError && (
                <div role='alert' className={styles.error}>
                  <p>گفتگو دریافت نشد.</p>
                  <Button variant='outline' onClick={() => void detail.refetch()}>
                    تلاش دوباره
                  </Button>
                </div>
              )}
              {detail.data && (
                <>
                  <div className={styles.ticketHead}>
                    <div>
                      <strong>{detail.data.subject}</strong>
                      <small dir='ltr'>{detail.data.reference}</small>
                    </div>
                    <span>{statusFa[detail.data.status]}</span>
                  </div>
                  <div
                    className={styles.messages}
                    role='log'
                    aria-label='گفتگوی درخواست'
                    aria-live='polite'
                  >
                    {detail.data.messages.map((msg) => (
                      <article key={msg.id} data-staff={!!msg.is_staff}>
                        <header>
                          <strong>{msg.is_staff ? 'پشتیبانی' : msg.author}</strong>
                          <time>{date(msg.created_at)}</time>
                        </header>
                        <p dir='auto'>{msg.body}</p>
                      </article>
                    ))}
                  </div>
                  <form
                    className={styles.form}
                    aria-busy={busy}
                    onSubmit={async (event) => {
                      event.preventDefault();
                      if (id === null) return;
                      setBusy(true);
                      setError('');
                      try {
                        updated(
                          await supportApi.reply(
                            id,
                            message.trim(),
                            !!list.data?.is_staff && asSupport
                          )
                        );
                        setMessage('');
                      } catch (e) {
                        fail(e);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <label htmlFor={`${fieldId}-reply`}>
                      پیام تازه
                      <Textarea
                        id={`${fieldId}-reply`}
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        required
                        minLength={2}
                        maxLength={5000}
                        rows={3}
                        disabled={busy}
                      />
                    </label>
                    {list.data?.is_staff && (
                      <label className={styles.staffOption}>
                        <input
                          type='checkbox'
                          checked={asSupport}
                          onChange={(e) => setAsSupport(e.target.checked)}
                          disabled={busy}
                        />
                        پاسخ به عنوان پشتیبانی
                      </label>
                    )}
                    <div className={styles.actions}>
                      <Button
                        type='button'
                        variant='outline'
                        disabled={busy}
                        onClick={async () => {
                          if (!detail.data) return;
                          setBusy(true);
                          setError('');
                          try {
                            updated(
                              await supportApi.status(
                                detail.data.id,
                                detail.data.status === 'closed' ? 'open' : 'closed'
                              )
                            );
                          } catch (e) {
                            fail(e);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        {detail.data.status === 'closed' ? 'باز کردن دوباره' : 'بستن درخواست'}
                      </Button>
                      <Button type='submit' disabled={busy || message.trim().length < 2}>
                        {busy ? 'در حال ثبت…' : 'ارسال پیام'}
                      </Button>
                    </div>
                  </form>
                </>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
