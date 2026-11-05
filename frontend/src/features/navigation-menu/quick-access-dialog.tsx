'use client';

import { useEffect, useState } from 'react';
import { IconArrowDown, IconArrowUp, IconX } from '@tabler/icons-react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogHeader
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { pearlNavigation } from './navigation-model';
import { DEFAULT_QUICK_ACCESS, MAX_QUICK_ACCESS } from './quick-access';
import styles from './quick-access-dialog.module.css';

export function QuickAccessDialog({
  open,
  onOpenChange,
  selectedIds,
  onSave
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedIds: string[];
  onSave: (ids: string[]) => void;
}) {
  const [draft, setDraft] = useState(selectedIds);
  const [error, setError] = useState('');
  useEffect(() => {
    if (open) {
      setDraft(selectedIds);
      setError('');
    }
  }, [open, selectedIds]);
  const entries = pearlNavigation.flatMap((group) => group.entries);
  const move = (index: number, offset: number) =>
    setDraft((current) => {
      const result = [...current];
      [result[index], result[index + offset]] = [result[index + offset], result[index]];
      return result;
    });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={styles.dialog} dir='rtl' showCloseButton={false}>
        <DialogHeader className={styles.header}>
          <div>
            <DialogTitle>تنظیمات دسترسی سریع</DialogTitle>
            <DialogDescription>
              تا ۵ بخش پرکاربرد را انتخاب و مرتب کنید. این انتخاب برای حساب شما در همین مرورگر ذخیره
              می‌شود.
            </DialogDescription>
          </div>
          <Button
            variant='ghost'
            size='icon'
            aria-label='بستن تنظیمات دسترسی سریع'
            onClick={() => onOpenChange(false)}
          >
            <IconX />
          </Button>
        </DialogHeader>
        <div className={styles.body}>
          <section aria-label='ترتیب دسترسی‌های سریع'>
            <h3>
              ترتیب نمایش <span>{draft.length.toLocaleString('fa-IR')} از ۵</span>
            </h3>
            {draft.length === 0 && (
              <p className='text-muted-foreground text-sm'>
                از فهرست پایین، بخش‌های دلخواهتان را انتخاب کنید.
              </p>
            )}
            <ol className={styles.order}>
              {draft.map((id, index) => {
                const title = entries.find((entry) => entry.id === id)?.label ?? id;
                return (
                  <li key={id}>
                    <span>{title}</span>
                    <div>
                      <button
                        type='button'
                        aria-label={`بالاتر: ${title}`}
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                      >
                        <IconArrowUp size={17} />
                      </button>
                      <button
                        type='button'
                        aria-label={`پایین‌تر: ${title}`}
                        disabled={index === draft.length - 1}
                        onClick={() => move(index, 1)}
                      >
                        <IconArrowDown size={17} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
          <div className={styles.groups}>
            {pearlNavigation.map((group) => (
              <section key={group.id}>
                <h3>{group.label}</h3>
                {group.entries.map((entry) => {
                  const checked = draft.includes(entry.id);
                  return (
                    <label key={entry.id} className={styles.option}>
                      <input
                        type='checkbox'
                        checked={checked}
                        disabled={!checked && draft.length >= MAX_QUICK_ACCESS}
                        onChange={() =>
                          setDraft((current) =>
                            checked
                              ? current.filter((id) => id !== entry.id)
                              : [...current, entry.id]
                          )
                        }
                      />
                      <span>{entry.label}</span>
                    </label>
                  );
                })}
              </section>
            ))}
          </div>
          {error && (
            <p role='alert' className='text-destructive text-sm'>
              {error}
            </p>
          )}
        </div>
        <footer className={styles.footer}>
          <Button variant='ghost' onClick={() => setDraft([...DEFAULT_QUICK_ACCESS])}>
            بازگشت به پیش‌فرض
          </Button>
          <Button
            onClick={() => {
              try {
                onSave(draft);
                onOpenChange(false);
              } catch {
                setError('ذخیره در مرورگر انجام نشد. تنظیمات ذخیره‌سازی مرورگر را بررسی کنید.');
              }
            }}
          >
            ذخیرهٔ دسترسی سریع
          </Button>
        </footer>
      </DialogContent>
    </Dialog>
  );
}
