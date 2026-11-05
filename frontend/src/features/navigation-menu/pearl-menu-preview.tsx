'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import Link from 'next/link';
import {
  IconX,
  IconArrowUpLeft,
  IconDeviceLaptop,
  IconDeviceIpad,
  IconDeviceMobile,
  IconSun,
  IconMoon,
  IconSearch,
  IconSitemap
} from '@tabler/icons-react';
import { PearlMenu, type PearlSite } from './pearl-menu';
import { pearlNavigation } from './navigation-model';
import { parseSiteDraft, siteDraftHref } from '@/features/sites/site-draft';
import styles from './pearl-menu.module.css';
import { MENU_BENCHMARKS, benchmarkScale } from './benchmarks';

type Panel = 'site' | 'task' | 'settings' | 'notifications' | 'help' | 'search';
const titles: Record<Panel, string> = {
  site: 'افزودن سایت',
  task: 'کار جدید',
  settings: 'تنظیمات نمایش',
  notifications: 'اعلان‌ها',
  help: 'راهنمای منو',
  search: 'جست‌وجوی بخش‌ها'
};
const deviceIcons = {
  laptop: IconDeviceLaptop,
  ipad: IconDeviceIpad,
  portrait: IconDeviceIpad,
  mobile: IconDeviceMobile
};
const benchmarks = MENU_BENCHMARKS;
const allEntries = pearlNavigation.flatMap((group) => group.entries);
const sites: PearlSite[] = [{ id: 'salimore', name: 'سالیمور', domain: 'salimore.com' }];

export function PearlMenuPreview({ canvas = false }: { canvas?: boolean }) {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
    if (!canvas)
      setDevice(
        window.innerWidth < 600 ? 'mobile' : window.innerWidth < 1100 ? 'portrait' : 'laptop'
      );
  }, [canvas]);
  const [selected, setSelected] = useState('salimore');
  const [selectedPage, setSelectedPage] = useState(allEntries.find((item) => item.id === 'graph')!);
  const [device, setDevice] = useState<(typeof benchmarks)[number]['id']>('laptop');
  const [viewportWidth, setViewportWidth] = useState<number | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [notice, setNotice] = useState('');
  const [formError, setFormError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [tasks, setTasks] = useState<string[]>([]);
  const dialog = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const [calendar, setCalendar] = useState('persian');
  const benchmark = benchmarks.find((item) => item.id === device)!;
  const normalizedQuery = searchQuery.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک');

  useEffect(() => {
    const observer = new ResizeObserver((entries) =>
      setViewportWidth(Math.round(entries[0].contentRect.width))
    );
    if (viewport.current) observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (panel) {
      returnFocus.current = document.activeElement as HTMLElement;
      setFormError('');
      dialog.current?.showModal();
      dialog.current?.querySelector<HTMLInputElement>('input')?.focus();
    }
  }, [panel]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  function closePanel() {
    dialog.current?.close();
    setPanel(null);
    returnFocus.current?.focus();
  }
  function navigate(href: string, label: string) {
    const entry = allEntries.find((item) => item.href === href);
    if (entry) setSelectedPage(entry);
    window.history.replaceState(null, '', `#${href.replace('/dashboard/', '')}`);
    setNotice(`بخش انتخاب‌شده: ${label}`);
  }
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (panel === 'site') {
      const draft = parseSiteDraft({ name: data.get('name'), domain: data.get('domain') });
      if (draft.name.length < 2 || !draft.domain) {
        setFormError('نام سایت و یک دامنهٔ معتبر مانند example.com وارد کن.');
        return;
      }
      const href = siteDraftHref(draft);
      if (canvas && window.parent !== window) window.parent.location.assign(href);
      else router.push(href);
    }
    if (panel === 'task') {
      const title = String(data.get('title') ?? '').trim();
      if (!title) return;
      setTasks((current) => [...current, title]);
      setNotice('کار در همین پیش‌نمایش ثبت شد.');
    }
    closePanel();
  }

  if (!canvas) {
    const scale = benchmarkScale(viewportWidth ?? 960, benchmark.width);
    return (
      <main className={styles.stage}>
        <header className={styles.previewToolbar}>
          <div className={styles.previewIdentity}>
            <strong>سالیمور / ناوبری</strong>
            <span>پیش‌نمایش چیدمان</span>
          </div>
          <div className={styles.benchmarks} role='group' aria-label='اندازهٔ پیش‌نمایش'>
            {benchmarks.map((item) => {
              const Icon = deviceIcons[item.id];
              return (
                <button
                  key={item.id}
                  type='button'
                  aria-pressed={device === item.id}
                  onClick={() => setDevice(item.id)}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                  <small dir='ltr'>
                    {item.width} × {item.height}
                  </small>
                </button>
              );
            })}
          </div>
          <div className={styles.themeSwitch} role='group' aria-label='حالت رنگ'>
            <button
              type='button'
              aria-label='نمایش حالت روشن'
              aria-pressed={mounted && resolvedTheme === 'light'}
              onClick={() => setTheme('light')}
            >
              <IconSun size={18} />
              <span>روشن</span>
            </button>
            <button
              type='button'
              aria-label='نمایش حالت تیره'
              aria-pressed={mounted && resolvedTheme === 'dark'}
              onClick={() => setTheme('dark')}
            >
              <IconMoon size={18} />
              <span>تیره</span>
            </button>
          </div>
        </header>
        <div ref={viewport} className={styles.frameHost}>
          <div
            className={styles.frameClip}
            style={{ width: benchmark.width * scale, height: benchmark.height * scale }}
          >
            {/* oxlint-disable-next-line react/iframe-missing-sandbox -- This trusted same-origin Next.js preview needs its scripts and shared theme storage. */}
            <iframe
              className={styles.deviceFrame}
              title={`پیش‌نمایش ${benchmark.label} ${benchmark.width} در ${benchmark.height}`}
              src='/design/menu?canvas=1'
              width={benchmark.width}
              height={benchmark.height}
              style={{
                width: benchmark.width,
                height: benchmark.height,
                transform: `scale(${scale})`
              }}
            />
          </div>
        </div>
        <p className={styles.stageNote}>
          Graphite / Ember · {benchmark.width} × {benchmark.height} CSS px · مقیاس نمایش{' '}
          {Math.round(scale * 100).toLocaleString('fa-IR')}٪
        </p>
      </main>
    );
  }

  return (
    <main className={`${styles.stage} ${styles.canvas}`}>
      <div className={styles.deviceViewport} ref={viewport} data-benchmark={device}>
        <div className={styles.workspaceShell}>
          <section className={styles.workspaceContent} aria-label='فضای کاری دسکتاپ'>
            <div className={styles.workspaceTop}>
              <span>
                سالیمور <span aria-hidden='true'>/</span> {selectedPage.label}
              </span>
              <span className={styles.designTag}>نمای چیدمان</span>
            </div>
            <div className={styles.workspaceBody}>
              <div className={styles.sectionEyebrow}>SEO BRAIN / WORKSPACE</div>
              <IconSitemap size={42} stroke={1.2} className={styles.contextIcon} />
              <h1>{selectedPage.label}</h1>
              <p>{selectedPage.description}</p>
              <Link href={selectedPage.href} className={styles.openPage} target='_top'>
                باز کردن صفحهٔ اصلی این بخش
                <IconArrowUpLeft size={19} />
              </Link>
              <div className={styles.inventoryHeader}>
                <h2>همهٔ بخش‌های سالیمور</h2>
                <span>{allEntries.length.toLocaleString('fa-IR')} مسیر حفظ شده</span>
              </div>
              <div className={styles.inventory}>
                {pearlNavigation.map((group) => (
                  <section key={group.id}>
                    <h3>{group.label}</h3>
                    {group.entries.map((entry) => (
                      <button
                        key={entry.href}
                        type='button'
                        aria-current={selectedPage.id === entry.id ? 'page' : undefined}
                        onClick={() => navigate(entry.href, entry.label)}
                      >
                        {entry.label}
                        <IconArrowUpLeft size={14} />
                      </button>
                    ))}
                  </section>
                ))}
              </div>
            </div>
            <footer className={styles.workspaceFoot}>
              <span>نمایش منو در فضای واقعی صفحه</span>
              <span>
                {viewportWidth ? `${viewportWidth.toLocaleString('fa-IR')} px` : 'اندازهٔ خودکار'}
              </span>
            </footer>
          </section>
          <PearlMenu
            sites={sites}
            selectedSiteId={selected}
            onSiteChange={setSelected}
            user={{ name: 'صالح', role: 'مدیر · نمونه', initial: 'ص' }}
            activeId={selectedPage.id}
            onNavigate={navigate}
            onAddSite={() => setPanel('site')}
            onOpenSearch={(query = '') => {
              setSearchQuery(query);
              setPanel('search');
            }}
            onCreateTask={() => setPanel('task')}
            onSettings={() => setPanel('settings')}
            onNotifications={() => setPanel('notifications')}
            onHelp={() => setPanel('help')}
            openActions={tasks.length}
            lastSync='دادهٔ نمونه'
            activity={tasks.map((task) => `کار نمونه: ${task}`)}
          />
        </div>
      </div>
      <p className={styles.stageNote}>Graphite / Ember · پیش‌نمایش منوی کامل</p>
      <div role='status' aria-live='polite' className={notice ? styles.previewNotice : undefined}>
        {notice}
      </div>
      {panel && (
        <dialog
          ref={dialog}
          className={`${styles.dialog} ${panel === 'search' ? styles.searchDialog : ''}`}
          dir='rtl'
          aria-labelledby='pearl-dialog-title'
          onCancel={(event) => {
            event.preventDefault();
            closePanel();
          }}
        >
          <header>
            <h2 id='pearl-dialog-title'>{titles[panel]}</h2>
            <button type='button' aria-label='بستن پنجره' onClick={closePanel}>
              <IconX size={20} />
            </button>
          </header>
          {panel === 'site' && (
            <form onSubmit={submit}>
              <p>نام و دامنه را وارد کن؛ تنظیم اتصال‌ها در مرحلهٔ بعد است.</p>
              <label>
                نام سایت
                <input
                  name='name'
                  required
                  minLength={2}
                  maxLength={80}
                  autoComplete='organization'
                />
              </label>
              <label>
                دامنه
                <input
                  name='domain'
                  required
                  dir='ltr'
                  inputMode='url'
                  placeholder='example.com'
                  maxLength={253}
                  aria-invalid={!!formError}
                  aria-describedby={formError ? 'site-quick-add-error' : undefined}
                />
              </label>
              {formError && (
                <p id='site-quick-add-error' role='alert' className={styles.formError}>
                  {formError}
                </p>
              )}
              <button type='submit' className={styles.createButton}>
                ادامهٔ مراحل افزودن سایت
                <IconArrowUpLeft size={19} />
              </button>
            </form>
          )}
          {panel === 'search' && (
            <>
              <label className={styles.commandSearch}>
                <IconSearch size={20} />
                <input
                  aria-label='جست‌وجو در همهٔ بخش‌ها'
                  placeholder='نام بخش یا کاری که می‌خواهی انجام دهی…'
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
              </label>
              <div className={styles.commandResults}>
                {pearlNavigation.map((group) => {
                  const entries = group.entries.filter((item) =>
                    `${item.label} ${item.description ?? ''}`.includes(normalizedQuery)
                  );
                  return entries.length ? (
                    <section key={group.id}>
                      <h3>{group.label}</h3>
                      {entries.map((entry) => (
                        <button
                          key={entry.href}
                          type='button'
                          onClick={() => {
                            navigate(entry.href, entry.label);
                            closePanel();
                          }}
                        >
                          <span>
                            <strong>{entry.label}</strong>
                            <small>{entry.description}</small>
                          </span>
                          <IconArrowUpLeft size={19} />
                        </button>
                      ))}
                    </section>
                  ) : null;
                })}
                {!allEntries.some((item) =>
                  `${item.label} ${item.description ?? ''}`.includes(normalizedQuery)
                ) && <p>بخشی با این عبارت پیدا نشد.</p>}
              </div>
            </>
          )}
          {panel === 'task' && (
            <form onSubmit={submit}>
              <p>ثبت کار در این صفحه صرفاً برای تست منو است.</p>
              <label>
                عنوان کار
                <input name='title' required maxLength={160} />
              </label>
              <button type='submit' className={styles.createButton}>
                ثبت کار نمونه
              </button>
            </form>
          )}
          {panel === 'notifications' &&
            (tasks.length ? (
              <ul>
                {tasks.map((task, i) => (
                  <li key={i}>{task}</li>
                ))}
              </ul>
            ) : (
              <p>اعلانی وجود ندارد.</p>
            ))}
          {panel === 'settings' && (
            <>
              <p>حالت روشن و تیره با تنظیمات نمایش برنامه هماهنگ است.</p>
              <label>
                تقویم پیش‌نمایش
                <select value={calendar} onChange={(event) => setCalendar(event.target.value)}>
                  <option value='persian'>شمسی</option>
                  <option value='gregory'>میلادی</option>
                </select>
              </label>
              <p>
                امروز:{' '}
                {new Intl.DateTimeFormat(`fa-IR-u-ca-${calendar}`, { dateStyle: 'long' }).format(
                  new Date()
                )}
              </p>
            </>
          )}
          {panel === 'help' && (
            <>
              <p>
                گروه‌ها با Enter باز می‌شوند. با دکمهٔ ذره‌بین کنار کادر یا Ctrl / ⌘ + K همهٔ بخش‌ها را
                جست‌وجو کن. Escape پنجره را می‌بندد.
              </p>
              <p>
                برای افزودن سایت، اطلاعات اولیه در فرم اصلی حفظ می‌شوند؛ ثبت سایت پس از تأیید خودت در
                همان فرم انجام می‌شود.
              </p>
            </>
          )}
        </dialog>
      )}
    </main>
  );
}
