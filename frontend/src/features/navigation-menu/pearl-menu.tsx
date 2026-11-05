'use client';

import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import {
  IconBell,
  IconChartBar,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconCircleCheck,
  IconFileAnalytics,
  IconGridDots,
  IconHelp,
  IconHome,
  IconLogout,
  IconMoon,
  IconPlus,
  IconSearch,
  IconSettings,
  IconSitemap,
  IconSparkles,
  IconSun,
  IconTrendingUp,
  IconWriting,
  IconX,
  IconHeartbeat,
  IconRefresh
} from '@tabler/icons-react';
import styles from './pearl-menu.module.css';
import { pearlNavigation } from './navigation-model';

type MenuIcon = typeof IconHome;
type Entry = { id: string; label: string; href: string; icon: MenuIcon; badge?: string };
export type PearlSite = { id: string; name: string; domain: string };
export type PearlMenuProps = {
  sites: PearlSite[];
  selectedSiteId: string;
  onSiteChange: (id: string) => void;
  user: { name: string; role: string; initial: string };
  onNavigate: (href: string, label: string) => void;
  onAddSite: () => void;
  onOpenSearch: (query?: string) => void;
  onCollapsedChange?: (collapsed: boolean) => void;
  collapsed?: boolean;
  manageSearchShortcut?: boolean;
  onCreateTask: () => void;
  primaryActionLabel?: string;
  notificationLabel?: string;
  statsMessage?: string;
  sitesStatus?: 'loading' | 'error';
  onRetrySites?: () => void;
  onSettings: () => void;
  onNotifications: () => void;
  onHelp: () => void;
  onSignOut?: () => void;
  openActions?: number;
  lastSync?: string;
  activity?: string[];
  initialActiveId?: string;
  activeId?: string;
};

const iconMap: Record<string, MenuIcon> = {
  dashboard: IconHome,
  sparkles: IconSparkles,
  sites: IconGridDots,
  trendingUp: IconTrendingUp,
  graph: IconSitemap,
  keywords: IconSearch,
  calendar: IconGridDots,
  planner: IconGridDots,
  content: IconWriting,
  flask: IconSparkles,
  ai: IconSparkles,
  linking: IconSitemap,
  opportunities: IconHeartbeat,
  reports: IconFileAnalytics,
  settings: IconSettings
};
const groupIcons: Record<string, MenuIcon> = {
  start: IconHome,
  seo: IconTrendingUp,
  content: IconWriting,
  opportunities: IconSparkles,
  measurement: IconChartBar
};
const groups = pearlNavigation.map((group) => ({
  ...group,
  icon: groupIcons[group.id] ?? IconGridDots,
  entries: group.entries.map((entry) => ({
    ...entry,
    icon: iconMap[entry.iconName] ?? IconGridDots
  }))
}));

export function RibbonMark({ small = false }: { small?: boolean }) {
  const gradientId = useId();
  return (
    <svg className={small ? styles.smallMark : styles.mark} viewBox='0 0 48 64' aria-hidden='true'>
      <defs>
        <linearGradient id={gradientId} x1='0' y1='0' x2='1' y2='1'>
          <stop stopColor='var(--primary)' />
          <stop offset='1' stopColor='var(--brand-edge, var(--primary))' />
        </linearGradient>
      </defs>
      <path
        d='M36 3 9 17C1 21 2 30 10 34l22 11L9 57c-5 3-3 9 3 7l27-14c8-4 8-13 0-17L17 22 40 10c5-3 2-10-4-7Z'
        fill={`url(#${gradientId})`}
      />
      <path d='m10 34 22 11 9-5-24-12Z' fill='currentColor' opacity='.3' />
      <path d='m9 17 27-14' stroke='var(--foreground)' strokeWidth='1.6' opacity='.85' />
    </svg>
  );
}

export function PearlMenu(props: PearlMenuProps) {
  const { activeId, onOpenSearch, onCollapsedChange } = props;
  const [localCollapsed, setLocalCollapsed] = useState(false);
  const collapsed = props.collapsed ?? localCollapsed;
  const manageSearchShortcut = props.manageSearchShortcut ?? true;
  function setCollapsed(next: boolean) {
    setLocalCollapsed(next);
    onCollapsedChange?.(next);
  }
  const [expanded, setExpanded] = useState<string[]>(['seo']);
  const [localActive, setActive] = useState(props.initialActiveId ?? 'graph');
  const active = activeId ?? localActive;
  const [module, setModule] = useState('seo');
  const [query, setQuery] = useState('');
  const [siteOpen, setSiteOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const night = mounted && resolvedTheme === 'dark';
  const search = useRef<HTMLInputElement>(null);
  const menuElement = useRef<HTMLElement>(null);
  const navigationElement = useRef<HTMLElement>(null);
  const [selectionBridge, setSelectionBridge] = useState<{
    top: number;
    height: number;
    width: number;
  } | null>(null);

  useLayoutEffect(() => {
    const menu = menuElement.current;
    const nav = navigationElement.current;
    if (!menu || !nav || collapsed) {
      setSelectionBridge(null);
      return;
    }
    let frame = 0;
    function measure() {
      const entry = nav?.querySelector<HTMLElement>('[aria-current="page"]');
      if (!entry || !menu || !nav) {
        setSelectionBridge(null);
        return;
      }
      const itemRect = entry.getBoundingClientRect();
      const navRect = nav.getBoundingClientRect();
      const menuRect = menu.getBoundingClientRect();
      if (itemRect.top < navRect.top || itemRect.bottom > navRect.bottom) {
        setSelectionBridge(null);
        return;
      }
      setSelectionBridge({
        top: itemRect.top - menuRect.top - menu.clientTop,
        height: itemRect.height,
        width: itemRect.right - menuRect.left - menu.clientLeft - 3
      });
    }
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(menu);
    observer.observe(nav);
    nav.addEventListener('scroll', schedule, { passive: true });
    schedule();
    return () => {
      observer.disconnect();
      nav.removeEventListener('scroll', schedule);
      cancelAnimationFrame(frame);
    };
  }, [active, expanded, query, collapsed]);
  const siteBox = useRef<HTMLDivElement>(null);
  const profileBox = useRef<HTMLDivElement>(null);
  const site = props.sites.find((s) => s.id === props.selectedSiteId) ?? props.sites[0];
  const normalized = query.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک');
  const matches = (text: string) => text.replace(/ي/g, 'ی').replace(/ك/g, 'ک').includes(normalized);
  const results = groups.flatMap((group) => group.entries).filter((entry) => matches(entry.label));

  useEffect(() => {
    if (!activeId) return;
    const parent = groups.find((group) => group.entries.some((item) => item.id === activeId));
    if (parent) {
      setModule(parent.id === 'start' ? 'overview' : parent.id);
      setExpanded((current) => (current.includes(parent.id) ? current : [...current, parent.id]));
    }
  }, [activeId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (
        manageSearchShortcut &&
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === 'k'
      ) {
        event.preventDefault();
        onOpenSearch(query);
      }
      if (event.key === 'Escape') {
        setSiteOpen(false);
        setProfileOpen(false);
        setQuery('');
      }
    };
    const outside = (event: PointerEvent) => {
      if (!siteBox.current?.contains(event.target as Node)) setSiteOpen(false);
      if (!profileBox.current?.contains(event.target as Node)) setProfileOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', outside);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', outside);
    };
  }, [onOpenSearch, query, manageSearchShortcut]);

  function go(entry: Entry) {
    setActive(entry.id);
    const parent = groups.find((group) => group.entries.some((item) => item.id === entry.id));
    if (parent) setModule(parent.id === 'start' ? 'overview' : parent.id);
    props.onNavigate(entry.href, entry.label);
  }
  function chooseModule(id: string) {
    setModule(id);
    setCollapsed(false);
    setQuery('');
    if (id === 'overview')
      go({ id, label: 'نمای کلی', href: '/dashboard/overview', icon: IconHome });
    else setExpanded((current) => (current.includes(id) ? current : [...current, id]));
    requestAnimationFrame(() =>
      document.getElementById(`pearl-group-${id}`)?.scrollIntoView({
        block: 'nearest',
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth'
      })
    );
  }
  function renderEntry(entry: Entry) {
    const Icon = entry.icon;
    return (
      <button
        key={entry.id}
        type='button'
        className={`${styles.entry} ${active === entry.id ? styles.selected : ''}`}
        aria-current={active === entry.id ? 'page' : undefined}
        onClick={() => go(entry)}
      >
        <Icon size={21} stroke={1.65} />
        <span>{entry.label}</span>
        {entry.badge && <small className={styles.badge}>{entry.badge}</small>}
        {active === entry.id && <i className={styles.selectedDot} />}
      </button>
    );
  }

  return (
    <aside
      className={`${styles.menu} ${collapsed ? styles.collapsed : ''}`}
      ref={menuElement}
      aria-label='منوی سالیمور'
      dir='rtl'
    >
      <button
        type='button'
        className={styles.collapseToggle}
        aria-label={collapsed ? 'باز کردن منو' : 'جمع کردن منو'}
        aria-expanded={!collapsed}
        aria-controls='salimore-menu-context'
        onClick={() => setCollapsed(!collapsed)}
      >
        <IconChevronRight size={19} className={collapsed ? styles.flipChevron : undefined} />
      </button>
      {selectionBridge && (
        <div aria-hidden='true' className={styles.selectionBridge} style={selectionBridge} />
      )}
      <div
        id='salimore-menu-context'
        className={styles.context}
        aria-hidden={collapsed}
        inert={collapsed}
      >
        <div className={styles.brandRow}>
          <div className={styles.wordmark} dir='ltr'>
            <RibbonMark />
            <div>
              <strong>salimore</strong>
              <small>SEO BRAIN</small>
            </div>
          </div>
        </div>

        <div className={styles.siteBox} ref={siteBox}>
          <div className={styles.workspace}>
            <button
              type='button'
              className={styles.siteTrigger}
              aria-expanded={siteOpen}
              aria-controls='pearl-sites'
              onClick={() => setSiteOpen(!siteOpen)}
            >
              <span className={styles.siteLogo}>
                <RibbonMark small />
              </span>
              <span className={styles.siteName}>
                <strong>
                  {site?.name ??
                    (props.sitesStatus === 'loading'
                      ? 'دریافت سایت‌ها…'
                      : props.sitesStatus === 'error'
                        ? 'دریافت سایت‌ها ناموفق بود'
                        : 'انتخاب سایت')}
                </strong>
                <small dir='ltr'>
                  {site?.domain ??
                    (props.sitesStatus === 'error'
                      ? 'برای تلاش دوباره باز کن'
                      : props.sitesStatus === 'loading'
                        ? 'در حال دریافت اطلاعات'
                        : 'هنوز سایتی اضافه نشده')}
                </small>
              </span>
              <span className={styles.connectionDot} title='سایت انتخاب‌شده' />
              <IconChevronDown size={17} />
            </button>
            <button
              type='button'
              className={styles.addSite}
              aria-label='افزودن سایت'
              onClick={props.onAddSite}
            >
              <IconPlus size={22} />
            </button>
          </div>
          {siteOpen && (
            <div className={styles.popover} id='pearl-sites' aria-label='انتخاب سایت'>
              <small>فضای کاری</small>
              {props.sites.length ? (
                props.sites.map((item) => (
                  <button
                    key={item.id}
                    type='button'
                    onClick={() => {
                      props.onSiteChange(item.id);
                      setSiteOpen(false);
                    }}
                  >
                    <span>
                      <strong>{item.name}</strong>
                      <small dir='ltr'>{item.domain}</small>
                    </span>
                    {item.id === site?.id && <IconCheck size={18} />}
                  </button>
                ))
              ) : (
                <div>
                  <p>
                    {props.sitesStatus === 'error'
                      ? 'دریافت سایت‌ها ناموفق بود.'
                      : props.sitesStatus === 'loading'
                        ? 'در حال دریافت…'
                        : 'سایتی موجود نیست.'}
                  </p>
                  {props.sitesStatus === 'error' && props.onRetrySites && (
                    <button type='button' onClick={props.onRetrySites}>
                      تلاش دوباره
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className={styles.searchRow}>
          <div className={styles.search}>
            <input
              ref={search}
              aria-label='فیلتر بخش‌های منو'
              placeholder='جست‌وجو در منو'
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {query && (
              <button
                type='button'
                aria-label='پاک کردن جست‌وجو'
                onClick={() => {
                  setQuery('');
                  search.current?.focus();
                }}
              >
                <IconX size={16} />
              </button>
            )}
          </div>
          <button
            type='button'
            className={styles.searchLauncher}
            aria-label='باز کردن جست‌وجوی بخش‌ها'
            title='جست‌وجوی همهٔ بخش‌ها'
            aria-haspopup='dialog'
            onClick={() => onOpenSearch(query)}
          >
            <IconSearch size={21} stroke={1.7} />
          </button>
        </div>

        <nav ref={navigationElement} className={styles.navigation} aria-label='بخش‌های محصول'>
          {normalized ? (
            <div className={styles.searchResults}>
              <p className={styles.resultsLabel}>نتیجهٔ جست‌وجو</p>
              {results.length ? (
                results.map(renderEntry)
              ) : (
                <p className={styles.empty}>بخشی با این نام پیدا نشد.</p>
              )}
            </div>
          ) : (
            <>
              {groups.map((group) => {
                const Icon = group.icon;
                const open = expanded.includes(group.id);
                return (
                  <div key={group.id} className={styles.group} id={`pearl-group-${group.id}`}>
                    <button
                      type='button'
                      className={styles.groupButton}
                      aria-expanded={open}
                      aria-controls={`pearl-items-${group.id}`}
                      onClick={() =>
                        setExpanded((current) =>
                          open ? current.filter((id) => id !== group.id) : [...current, group.id]
                        )
                      }
                    >
                      <Icon size={22} stroke={1.6} />
                      <span>{group.label}</span>
                      <IconChevronDown className={open ? styles.chevronOpen : ''} size={17} />
                    </button>
                    <div id={`pearl-items-${group.id}`} className={styles.children} hidden={!open}>
                      {group.entries.map(renderEntry)}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </nav>

        <div className={styles.footer}>
          <section className={styles.statusDock} aria-label='وضعیت امروز'>
            <button
              type='button'
              className={styles.statusHeader}
              aria-expanded={activityOpen}
              aria-controls='pearl-activity'
              onClick={() => setActivityOpen(!activityOpen)}
            >
              <strong>وضعیت امروز</strong>
              <IconChevronDown className={activityOpen ? styles.chevronOpen : ''} size={17} />
            </button>
            <div className={styles.statusPills}>
              <span>
                <IconCircleCheck size={17} />
                {props.openActions === undefined
                  ? (props.statsMessage ?? 'آمار متصل نیست')
                  : `${props.openActions.toLocaleString('fa-IR')} اقدام باز`}
              </span>
              <span>
                <IconRefresh size={16} />
                {props.lastSync ?? 'همگام‌سازی نشده'}
              </span>
            </div>
            {activityOpen && (
              <ul className={styles.activity} id='pearl-activity'>
                {props.activity?.length ? (
                  props.activity.map((line, i) => <li key={i}>{line}</li>)
                ) : (
                  <li>فعالیتی برای نمایش وجود ندارد.</li>
                )}
              </ul>
            )}
          </section>
          <button type='button' className={styles.createButton} onClick={props.onCreateTask}>
            <IconPlus size={24} />
            <span>{props.primaryActionLabel ?? 'کار جدید'}</span>
          </button>
          <div className={styles.utilities}>
            <div className={styles.profileBox} ref={profileBox}>
              <button
                type='button'
                className={styles.profile}
                aria-label={`حساب ${props.user.name}`}
                aria-expanded={profileOpen}
                aria-controls='pearl-profile'
                onClick={() => setProfileOpen(!profileOpen)}
              >
                <span className={styles.avatar}>{props.user.initial}</span>
                <span>
                  <strong>{props.user.name}</strong>
                  <small>{props.user.role}</small>
                </span>
                <IconChevronDown size={15} />
              </button>
              {profileOpen && (
                <div id='pearl-profile' className={`${styles.popover} ${styles.profilePopover}`}>
                  <small>
                    {props.user.name} · {props.user.role}
                  </small>
                  <button
                    type='button'
                    onClick={() => {
                      setProfileOpen(false);
                      props.onSettings();
                    }}
                  >
                    <IconSettings size={18} />
                    تنظیمات حساب
                  </button>
                  {props.onSignOut && (
                    <button type='button' onClick={props.onSignOut}>
                      <IconLogout size={18} />
                      خروج از حساب
                    </button>
                  )}
                </div>
              )}
            </div>
            <button
              type='button'
              className={styles.themeButton}
              aria-label={night ? 'حالت روشن' : 'حالت تیره'}
              aria-pressed={night}
              onClick={() => setTheme(night ? 'light' : 'dark')}
            >
              {night ? <IconSun size={19} /> : <IconMoon size={19} />}
            </button>
            <button
              type='button'
              className={styles.settingsButton}
              aria-label='تنظیمات'
              onClick={props.onSettings}
            >
              <IconSettings size={20} />
            </button>
          </div>
        </div>
      </div>

      <div className={styles.rail}>
        <button
          type='button'
          className={styles.railBrand}
          aria-label='سالیمور، نمای کلی'
          onClick={() => chooseModule('overview')}
        >
          <RibbonMark small />
        </button>
        <div className={styles.modules}>
          {[
            { id: 'overview', label: 'نمای کلی', icon: IconGridDots },
            { id: 'seo', label: 'سئو و رشد', icon: IconSitemap },
            { id: 'content', label: 'برنامه و اجرا', icon: IconWriting },
            { id: 'opportunities', label: 'فرصت‌ها و مسائل', icon: IconSparkles },
            { id: 'measurement', label: 'سنجش و تنظیمات', icon: IconChartBar }
          ].map((item) => {
            const Icon = item.icon;
            return (
              <button
                type='button'
                key={item.id}
                title={item.label}
                aria-label={item.label}
                aria-pressed={module === item.id}
                className={`${styles.railButton} ${module === item.id ? styles.railSelected : ''}`}
                onClick={() => chooseModule(item.id)}
              >
                <Icon size={25} stroke={1.55} />
              </button>
            );
          })}
        </div>
        <div className={styles.railBottom}>
          <button
            type='button'
            className={styles.railButton}
            title={props.notificationLabel ?? 'اعلان‌ها'}
            aria-label={props.notificationLabel ?? 'اعلان‌ها'}
            onClick={props.onNotifications}
          >
            <IconBell size={23} stroke={1.55} />
          </button>
          <button
            type='button'
            className={styles.railButton}
            title='راهنما'
            aria-label='راهنما'
            onClick={props.onHelp}
          >
            <IconHelp size={23} stroke={1.55} />
          </button>
          <button
            type='button'
            className={`${styles.railButton} ${styles.railAvatar}`}
            aria-label={collapsed ? 'باز کردن حساب کاربری' : 'حساب کاربری'}
            onClick={() => {
              setCollapsed(false);
              setProfileOpen(!profileOpen);
            }}
          >
            {props.user.initial}
          </button>
        </div>
      </div>
    </aside>
  );
}
