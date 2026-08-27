'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { GraphMode, GraphView, Site } from '@/lib/api/client';
import {
  IconAdjustmentsHorizontal, IconArrowsMaximize, IconFocusCentered, IconLayoutBoard,
  IconRefresh, IconSearch, IconX
} from '@tabler/icons-react';
import { NODE_STYLE, RELATION_FA, TYPE_FAMILIES } from '../constants';
import type { Direction, Grouping } from '../layout';

export type ToolbarState = {
  siteId: string;
  mode: 'seo' | 'content' | 'links' | 'planner';
  query: string;
  familyOff: Set<string>;
  relationOff: Set<string>;
  grouping: Grouping;
  direction: Direction;
  hideIsolated: boolean;
  focusNeighbors: boolean;
  limit: number;
};

export function GraphToolbar({
  sites, modes, view, state, onChange, onFit, onRelayout, onSearchSubmit, onResetFilters,
  loading, matches, selectedLabel, neighborCount
}: {
  sites: Site[];
  modes: GraphMode[];
  view: GraphView | null;
  state: ToolbarState;
  onChange: (patch: Partial<ToolbarState>) => void;
  onFit: () => void;
  onRelayout: () => void;
  onSearchSubmit: () => void;
  onResetFilters: () => void;
  loading: boolean;
  matches: number;
  selectedLabel: string | null;
  neighborCount: number;
}) {
  const modeTypes = new Set(view?.mode.node_types ?? []);
  const familiesInMode = TYPE_FAMILIES.filter((family) => family.types.some((type) => modeTypes.has(type)));
  const relationsInMode = view?.mode.relation_types ?? [];
  const activeFilters = state.familyOff.size + state.relationOff.size;
  const toggle = (set: Set<string>, key: string) => {
    const next = new Set(set);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  };

  return (
    <section className='bg-card overflow-hidden rounded-xl border shadow-sm'>
      <div className='flex flex-col gap-3 p-3'>
        <div className='flex flex-col gap-3 xl:flex-row xl:items-center'>
          <div className='flex min-w-0 flex-wrap items-center gap-2'>
            <NativeSelect value={state.siteId} onChange={(event) => onChange({ siteId: event.target.value })} className='w-48' aria-label='سایت'>
              {sites.map((site) => <NativeSelectOption key={site.site_id} value={site.site_id}>{site.name}</NativeSelectOption>)}
            </NativeSelect>
            <div className='flex overflow-x-auto rounded-lg border bg-muted/20 p-1' role='tablist' aria-label='نوع نقشه'>
              {modes.map((mode) => (
                <button key={mode.key} role='tab' aria-selected={state.mode === mode.key} title={mode.description_fa}
                  onClick={() => onChange({ mode: mode.key })}
                  className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${state.mode === mode.key ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
                  {mode.title_fa}
                </button>
              ))}
            </div>
          </div>

          <form className='relative flex min-w-0 flex-1 items-center gap-1' onSubmit={(event) => { event.preventDefault(); onSearchSubmit(); }}>
            <IconSearch className='text-muted-foreground pointer-events-none absolute right-3 size-4' aria-hidden='true' />
            <Input value={state.query} onChange={(event) => onChange({ query: event.target.value })} placeholder='عنوان صفحه، URL، کلمه کلیدی یا موجودیت…' className='min-w-0 pr-9 pl-20' />
            {state.query && <Button type='button' size='icon-sm' variant='ghost' className='absolute left-12' onClick={() => onChange({ query: '' })} aria-label='پاک کردن جست‌وجو'><IconX /></Button>}
            <Button type='submit' size='sm' variant='secondary' className='absolute left-1'>{matches ? `${matches.toLocaleString('fa-IR')} نتیجه` : 'یافتن'}</Button>
          </form>
        </div>

        <div className='flex flex-wrap items-center gap-2 border-t pt-3'>
          <div className='text-muted-foreground min-w-0 flex-1 text-xs leading-5'>
            <span className='font-semibold text-foreground'>{view?.mode.title_fa ?? 'گراف دانش'}:</span>{' '}
            {view?.mode.description_fa || 'برای بررسی جزئیات، یک گره را انتخاب کنید. گره‌های نامرتبط کم‌رنگ می‌شوند.'}
          </div>
          {selectedLabel && (
            <Button size='sm' variant={state.focusNeighbors ? 'default' : 'outline'} onClick={() => onChange({ focusNeighbors: !state.focusNeighbors })}>
              <IconFocusCentered /> {state.focusNeighbors ? 'نمایش کل گراف' : `فقط ارتباط‌های مستقیم (${neighborCount.toLocaleString('fa-IR')})`}
            </Button>
          )}
          <Button size='sm' variant='outline' onClick={onFit}><IconArrowsMaximize /> جا دادن در صفحه</Button>
          <Button size='sm' variant='outline' onClick={onRelayout}><IconRefresh /> چیدمان دوباره</Button>
          <Badge variant='secondary' className='h-8 px-3 tabular-nums'>
            {loading ? 'در حال بارگذاری…' : view ? `${view.nodes.length.toLocaleString('fa-IR')} گره · ${view.edges.length.toLocaleString('fa-IR')} رابطه${view.truncated ? ` از ${view.total_nodes.toLocaleString('fa-IR')}` : ''}` : 'بدون داده'}
          </Badge>
        </div>
      </div>

      <details className='group border-t'>
        <summary className='hover:bg-muted/40 flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium'>
          <IconAdjustmentsHorizontal className='size-4' /> فیلتر و چیدمان پیشرفته
          {activeFilters > 0 && <Badge variant='destructive'>{activeFilters.toLocaleString('fa-IR')} فیلتر فعال</Badge>}
          <span className='text-muted-foreground ms-auto'>برای نمای ساده نیازی به باز کردن این بخش نیست</span>
        </summary>
        <div className='space-y-3 border-t bg-muted/15 p-3'>
          <div className='flex flex-wrap items-center gap-2'>
            <IconLayoutBoard className='text-muted-foreground size-4' />
            <NativeSelect value={state.grouping} onChange={(event) => onChange({ grouping: event.target.value as Grouping })} className='w-40' aria-label='گروه‌بندی'>
              <NativeSelectOption value='none'>چیدمان ارتباطی</NativeSelectOption>
              <NativeSelectOption value='type'>گروه‌بندی بر اساس نوع</NativeSelectOption>
              <NativeSelectOption value='community'>گروه‌بندی بر اساس خوشه</NativeSelectOption>
            </NativeSelect>
            {state.grouping === 'none' && (
              <NativeSelect value={state.direction} onChange={(event) => onChange({ direction: event.target.value as Direction })} className='w-36' aria-label='جهت چیدمان'>
                <NativeSelectOption value='TB'>بالا به پایین</NativeSelectOption>
                <NativeSelectOption value='LR'>چپ به راست</NativeSelectOption>
                <NativeSelectOption value='RL'>راست به چپ</NativeSelectOption>
              </NativeSelect>
            )}
            <NativeSelect value={String(state.limit)} onChange={(event) => onChange({ limit: Number(event.target.value) })} className='w-36' aria-label='حداکثر گره'>
              <NativeSelectOption value='80'>سبک · ۸۰ گره</NativeSelectOption>
              <NativeSelectOption value='160'>متعادل · ۱۶۰ گره</NativeSelectOption>
              <NativeSelectOption value='300'>گسترده · ۳۰۰ گره</NativeSelectOption>
              <NativeSelectOption value='600'>سنگین · ۶۰۰ گره</NativeSelectOption>
            </NativeSelect>
            {state.mode === 'links' && <label className='flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs'><input type='checkbox' checked={state.hideIsolated} onChange={(event) => onChange({ hideIsolated: event.target.checked })} /> پنهان‌کردن صفحات بدون لینک</label>}
            {activeFilters > 0 && <Button size='sm' variant='ghost' onClick={onResetFilters}><IconX /> حذف همه فیلترها</Button>}
          </div>

          <div className='flex flex-wrap items-center gap-1.5'>
            <span className='text-muted-foreground w-20 text-xs'>نوع گره</span>
            {familiesInMode.map((family) => {
              const count = family.types.reduce((total, type) => total + (view?.stats.by_type[type] ?? 0), 0);
              const off = state.familyOff.has(family.key);
              const color = NODE_STYLE[family.types[0]]?.color;
              return <button key={family.key} onClick={() => onChange({ familyOff: toggle(state.familyOff, family.key) })} aria-pressed={!off}>
                <Badge variant={off ? 'outline' : 'default'} style={off ? {} : { background: color, borderColor: color }} className='cursor-pointer gap-1'>{family.fa}<span className='opacity-75'>{count.toLocaleString('fa-IR')}</span></Badge>
              </button>;
            })}
          </div>

          <div className='flex flex-wrap items-center gap-1.5'>
            <span className='text-muted-foreground w-20 text-xs'>نوع رابطه</span>
            {relationsInMode.map((relation) => {
              const off = state.relationOff.has(relation);
              const count = view?.stats.by_relation[relation] ?? 0;
              if (!count) return null;
              return <button key={relation} onClick={() => onChange({ relationOff: toggle(state.relationOff, relation) })} aria-pressed={!off}>
                <Badge variant={off ? 'outline' : 'secondary'} className='cursor-pointer gap-1'>{RELATION_FA[relation] ?? relation}<span className='opacity-70'>{count.toLocaleString('fa-IR')}</span></Badge>
              </button>;
            })}
          </div>
        </div>
      </details>
    </section>
  );
}
