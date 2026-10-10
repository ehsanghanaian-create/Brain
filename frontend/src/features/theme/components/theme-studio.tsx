'use client';

import { useTheme } from 'next-themes';
import { motion, useReducedMotion } from 'motion/react';
import { useEffect, useState } from 'react';
import { useThemeConfig } from '@/components/themes/active-theme';
import { THEMES } from '@/components/themes/theme.config';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Icons } from '@/components/icons';

const accents = [
  { name: 'سبز اصلی', hex: '#1abb9c' },
  { name: 'آبی', hex: '#066fd1' },
  { name: 'بنفش', hex: '#7856d8' },
  { name: 'کهربایی', hex: '#d88816' },
  { name: 'مرجانی', hex: '#dc6258' }
];

export function applyGentelellaAccent(hex: string | null) {
  const root = document.documentElement;
  const valid = hex && /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : null;
  for (const token of ['--primary', '--ring', '--chart-1', '--sidebar-primary']) {
    if (valid && root.dataset.theme === 'gentelella') root.style.setProperty(token, valid);
    else root.style.removeProperty(token);
  }
}

export function ThemeStudio() {
  const { activeTheme, setActiveTheme } = useThemeConfig();
  const { theme, setTheme } = useTheme();
  const reduced = useReducedMotion();
  const [accent, setAccent] = useState('#1abb9c');

  useEffect(() => {
    const saved = localStorage.getItem('seo-brain-accent');
    if (saved && /^#[0-9a-fA-F]{6}$/.test(saved)) setAccent(saved);
  }, []);
  useEffect(() => {
    applyGentelellaAccent(accent);
  }, [accent, activeTheme]);

  function changeAccent(hex: string) {
    setAccent(hex);
    localStorage.setItem('seo-brain-accent', hex);
  }

  return (
    <div className='grid gap-5 xl:grid-cols-[1.25fr_1fr]'>
      <Card className='overflow-hidden'>
        <CardHeader>
          <CardTitle>ظاهر داشبورد</CardTitle>
          <CardDescription>
            قالب Gentelella با قلم فارسی و چیدمان راست‌به‌چپ برای SEO Brain تنظیم شده است.
          </CardDescription>
        </CardHeader>
        <CardContent className='grid gap-3 sm:grid-cols-3'>
          {THEMES.map((item, index) => (
            <motion.button
              key={item.value}
              type='button'
              initial={reduced ? false : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.07 }}
              whileHover={reduced ? undefined : { y: -4 }}
              whileTap={reduced ? undefined : { scale: 0.98 }}
              onClick={() => {
                setActiveTheme(item.value);
                if (item.value !== 'gentelella') applyGentelellaAccent(null);
              }}
              aria-pressed={activeTheme === item.value}
              className={`overflow-hidden rounded-xl border text-start transition-shadow hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${activeTheme === item.value ? 'border-primary ring-2 ring-primary/25' : 'border-border'}`}
            >
              <span
                className={`flex h-28 gap-2 p-3 ${item.value === 'gentelella' ? 'bg-[#f5f7fb]' : item.value === 'neon' ? 'bg-[#151827]' : 'bg-[#f8f8f8]'}`}
              >
                <span
                  className={`w-1/4 rounded-md ${item.value === 'gentelella' ? 'bg-[#1a2332]' : item.value === 'neon' ? 'bg-[#272849]' : 'bg-[#202020]'}`}
                />
                <span className='flex flex-1 flex-col gap-2'>
                  <span className='h-4 rounded bg-white/70' />
                  <span className='flex gap-2'>
                    <span className='h-12 flex-1 rounded bg-white/90 shadow-sm' />
                    <span className='h-12 flex-1 rounded bg-white/90 shadow-sm' />
                  </span>
                  <span
                    className='h-2 w-2/3 rounded'
                    style={{
                      background:
                        item.value === 'gentelella'
                          ? accent
                          : item.value === 'neon'
                            ? '#8375ea'
                            : '#222'
                    }}
                  />
                </span>
              </span>
              <span className='flex items-center justify-between p-3 text-sm font-semibold'>
                <span>{item.name}</span>
                {activeTheme === item.value && <Icons.check className='size-4 text-primary' />}
              </span>
            </motion.button>
          ))}
        </CardContent>
      </Card>
      <div className='space-y-5'>
        <Card>
          <CardHeader>
            <CardTitle>حالت نمایش</CardTitle>
            <CardDescription>
              تغییر روشنایی با انیمیشن کوتاه و حفظ انتخاب در مرورگر.
            </CardDescription>
          </CardHeader>
          <CardContent className='flex flex-wrap gap-2'>
            {(['light', 'dark', 'system'] as const).map((mode) => (
              <Button
                key={mode}
                type='button'
                variant={theme === mode ? 'default' : 'outline'}
                onClick={() => setTheme(mode)}
              >
                {mode === 'light' ? 'روشن' : mode === 'dark' ? 'تیره' : 'سیستم'}
              </Button>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>رنگ شاخص Gentelella</CardTitle>
            <CardDescription>
              این رنگ روی دکمه‌ها، لینک‌های فعال و نمودارها اعمال می‌شود.
            </CardDescription>
          </CardHeader>
          <CardContent className='flex flex-wrap items-center gap-3'>
            {accents.map((item) => (
              <button
                key={item.hex}
                type='button'
                aria-label={item.name}
                title={item.name}
                aria-pressed={accent === item.hex}
                onClick={() => changeAccent(item.hex)}
                className={`size-9 rounded-full border-2 border-background shadow-md transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${accent === item.hex ? 'ring-2 ring-foreground/50' : ''}`}
                style={{ backgroundColor: item.hex }}
              />
            ))}
            <label className='text-muted-foreground flex items-center gap-2 text-xs'>
              رنگ دلخواه{' '}
              <input
                type='color'
                value={accent}
                onChange={(e) => changeAccent(e.target.value)}
                aria-label='رنگ دلخواه'
                className='size-8 cursor-pointer rounded border-0 bg-transparent'
              />
            </label>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
