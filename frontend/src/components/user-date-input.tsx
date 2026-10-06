'use client';

import { Input } from '@/components/ui/input';
import { JalaliDateInput } from '@/features/content/components/jalali-date-input';
import { useDatePreference } from '@/lib/date-preference';

export function UserDateInput({ value, onChange, mode = 'date', disabled = false, label }: {
  value: string; onChange: (value: string) => void; mode?: 'date' | 'datetime-local';
  disabled?: boolean; label: string;
}) {
  const { calendar } = useDatePreference();
  if (calendar === 'gregorian') return <Input aria-label={label} type={mode} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />;
  const day = value.slice(0, 10);
  return <div className='flex gap-2'>
    <JalaliDateInput aria-label={label} disabled={disabled} value={day || null}
      onChange={(iso) => onChange(iso ? mode === 'datetime-local' ? `${iso}T${value.slice(11, 16) || '12:00'}` : iso : '')} />
    {mode === 'datetime-local' && <Input aria-label={`${label}، ساعت`} type='time' disabled={disabled} className='w-28 shrink-0' value={value.slice(11, 16) || '12:00'} onChange={(event) => onChange(`${day || new Date().toISOString().slice(0, 10)}T${event.target.value}`)} />}
  </div>;
}
