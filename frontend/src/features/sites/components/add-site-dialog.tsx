'use client';

import { useState } from 'react';
import { IconX } from '@tabler/icons-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { SiteWizard } from './site-wizard';
import styles from './add-site-dialog.module.css';

export function AddSiteDialog({
  open,
  onOpenChange
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent
        data-add-site-dialog
        initialFocus={() =>
          document.querySelector<HTMLInputElement>(
            '[data-add-site-dialog] [data-site-initial-field]'
          )
        }
        className={styles.dialog}
        showCloseButton={false}
        dir='rtl'
      >
        <DialogHeader className={styles.header}>
          <div>
            <DialogTitle>افزودن سایت</DialogTitle>
            <DialogDescription>
              اطلاعات سایت را کامل کنید؛ اتصال حساب‌ها و راه‌اندازی هم در همین پنجره ادامه پیدا می‌کند.
            </DialogDescription>
          </div>
          <Button
            variant='ghost'
            size='icon'
            aria-label='بستن افزودن سایت'
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            <IconX size={20} />
          </Button>
        </DialogHeader>
        <div className={styles.body}>
          <SiteWizard embedded onBusyChange={setBusy} onFinish={() => onOpenChange(false)} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
