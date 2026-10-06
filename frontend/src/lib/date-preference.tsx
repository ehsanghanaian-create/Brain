'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';

export type DateCalendar = 'jalali' | 'gregorian';
const DateContext = createContext<{ calendar: DateCalendar; setCalendar: (value: DateCalendar) => void }>({
  calendar: 'jalali', setCalendar: () => undefined
});

export function DatePreferenceProvider({ initialCalendar, children }: {
  initialCalendar: DateCalendar; children: ReactNode;
}) {
  const [calendar, setCalendar] = useState<DateCalendar>(initialCalendar);
  return <DateContext.Provider value={{ calendar, setCalendar }}>{children}</DateContext.Provider>;
}

export const useDatePreference = () => useContext(DateContext);

export function formatUserDate(value: string | Date | null | undefined, calendar: DateCalendar,
                               options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' }) {
  if (!value) return 'بدون تاریخ';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return 'تاریخ نامعتبر';
  return new Intl.DateTimeFormat(calendar === 'jalali' ? 'fa-IR-u-ca-persian' : 'fa-IR-u-ca-gregory', options).format(date);
}

export function formatUserDateTime(value: string | Date | null | undefined, calendar: DateCalendar) {
  return formatUserDate(value, calendar, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatUserDay(isoDay: string | null | undefined, calendar: DateCalendar,
                              style: 'short' | 'long' = 'short') {
  if (!isoDay) return '';
  return formatUserDate(`${isoDay.slice(0, 10)}T12:00:00Z`, calendar,
    style === 'short' ? { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC' } :
      { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' });
}
