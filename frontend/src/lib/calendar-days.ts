import { addDays, jalaliMonthDays } from '@/features/content/constants';
import type { DateCalendar } from './date-preference';

export function userMonthDays(anchor: Date, calendar: DateCalendar): Date[] {
  if (calendar === 'jalali') return jalaliMonthDays(anchor).days;
  const start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), 1));
  const days: Date[] = [];
  for (let day = start; day.getUTCMonth() === start.getUTCMonth(); day = addDays(day, 1)) days.push(day);
  return days;
}
