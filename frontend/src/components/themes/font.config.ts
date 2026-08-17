import { Vazirmatn, Geist_Mono } from 'next/font/google';

import { cn } from '@/lib/utils';

// Persian-first UI: Vazirmatn covers Arabic-script + Latin glyphs; Geist Mono for code/ids.
const fontSans = Vazirmatn({
  subsets: ['arabic', 'latin'],
  variable: '--font-vazirmatn',
  display: 'swap'
});

const fontMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono'
});

export const fontVariables = cn(fontSans.variable, fontMono.variable);
