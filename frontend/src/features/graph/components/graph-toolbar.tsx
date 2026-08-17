'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { GraphMode, GraphView, Site } from '@/lib/api/client';
import { NODE_STYLE, RELATION_FA, TYPE_FAMILIES } from '../constants';
import type { Direction, Grouping } from '../layout';

export type ToolbarState = {
  siteId: string;
  mode: 'seo' | 'content' | 'links';
  query: string;
  familyOff: Set<string>;         // hidden type families
  relationOff: Set<string>;       // hidden relations
  grouping: Grouping;
  direction: Direction;
  hideIsolated: boolean;
  limit: number;
};

export function GraphToolbar({
  sites,
  modes,
  view,
  state,
  onChange,
  onFit,
  onRelayout,
  onSearchSubmit,
  loading,
  matches
}: {
  sites: Site[];
  modes: GraphMode[];
  view: GraphView | null;
  state: ToolbarState;
  onChange: (patch: Partial<ToolbarState>) => void;
  onFit: () => void;
  onRelayout: () => void;
  onSearchSubmit: () => void;
  loading: boolean;
  matches: number;
}) {
  const modeTypes = new Set(view?.mode.node_types ?? []);
  const familiesInMode = TYPE_FAMILIES.filter((f) => f.types.some((t) => modeTypes.has(t)));
  const relationsInMode = view?.mode.relation_types ?? [];
  const toggle = (set: Set<string>, key: string) => {
    const s = new Set(set);
    s.has(key) ? s.delete(key) : s.add(key);
    return s;
  };
  return (
    <div className='bg-card flex flex-col gap-2 rounded-lg border p-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect value={state.siteId} onChange={(e) => onChange({ siteId: e.target.value })} className='w-44' aria-label='سایت'>
          {sites.map((s) => (
            <NativeSelectOption key={s.site_id} value={s.site_id}>{s.name}</NativeSelectOption>
          ))}
        </NativeSelect>
        <div className='flex overflow-hidden rounded-md border' role='tablist' aria-label='حالت گراف'>
          {modes.map((m) => (
            <button
              key={m.key}
              role='tab'
              aria-selected={state.mode === m.key}
              title={m.description_fa}
              onClick={() => onChange({ mode: m.key })}
              className={`px-3 py-1.5 text-xs ${state.mode === m.key ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
            >
              {m.title_fa}
            </button>
          ))}
        </div>
        <form
          className='flex items-center gap-1'
          onSubmit={(e) => {
            e.preventDefault();
            onSearchSubmit();
          }}
        >
          <Input value={state.query} onChange={(e) => onChange({ query: e.target.value })} placeholder='جست‌وجوی گره (عنوان، URL، کوئری)…' className='w-64' />
          <Button type='submit' size='sm' variant='secondary'>{matches ? `${matches} مورد` : 'یافتن'}</Button>
        </form>
        <NativeSelect value={state.grouping} onChange={(e) => onChange({ grouping: e.target.value as Grouping })} className='w-36' aria-label='گروه‌بندی'>
          <NativeSelectOption value='none'>بدون گروه‌بندی</NativeSelectOption>
          <NativeSelectOption value='type'>گروه‌بندی: نوع</NativeSelectOption>
          <NativeSelectOption value='community'>گروه‌بندی: خوشه</NativeSelectOption>
        </NativeSelect>
        {state.grouping === 'none' && (
          <NativeSelect value={state.direction} onChange={(e) => onChange({ direction: e.target.value as Direction })} className='w-32' aria-label='جهت چیدمان'>
            <NativeSelectOption value='TB'>بالا → پایین</NativeSelectOption>
            <NativeSelectOption value='LR'>چپ → راست</NativeSelectOption>
            <NativeSelectOption value='RL'>راست → چپ</NativeSelectOption>
          </NativeSelect>
        )}
        {state.mode === 'links' && (
          <label className='flex items-center gap-1 text-xs'>
            <input type='checkbox' checked={state.hideIsolated} onChange={(e) => onChange({ hideIsolated: e.target.checked })} /> پنهان‌کردن گره‌های بدون لینک
          </label>
        )}
        <Button size='sm' variant='outline' onClick={onFit}>نمایش کامل</Button>
        <Button size='sm' variant='outline' onClick={onRelayout}>چیدمان مجدد</Button>
        <span className='text-muted-foreground ms-auto text-xs'>
          {loading ? 'در حال بارگذاری…' : view ? `${view.nodes.length} گره · ${view.edges.length} یال${view.truncated ? ` (از ${view.total_nodes})` : ''}` : ''}
        </span>
      </div>
      <div className='flex flex-wrap items-center gap-1'>
        <span className='text-muted-foreground text-xs'>نوع گره:</span>
        {familiesInMode.map((f) => {
          const count = f.types.reduce((a, t) => a + (view?.stats.by_type[t] ?? 0), 0);
          const off = state.familyOff.has(f.key);
          const color = NODE_STYLE[f.types[0]]?.color;
          return (
            <button key={f.key} onClick={() => onChange({ familyOff: toggle(state.familyOff, f.key) })} className='focus:outline-none' aria-pressed={!off}>
              <Badge variant={off ? 'outline' : 'default'} style={off ? {} : { background: color, borderColor: color }} className='cursor-pointer gap-1'>
                {f.fa} <span className='opacity-80'>{count}</span>
              </Badge>
            </button>
          );
        })}
        <span className='text-muted-foreground ms-3 text-xs'>رابطه:</span>
        {relationsInMode.map((r) => {
          const off = state.relationOff.has(r);
          const count = view?.stats.by_relation[r] ?? 0;
          if (!count && off) return null;
          return (
            <button key={r} onClick={() => onChange({ relationOff: toggle(state.relationOff, r) })} className='focus:outline-none' aria-pressed={!off}>
              <Badge variant={off ? 'outline' : 'secondary'} className='cursor-pointer gap-1'>
                {RELATION_FA[r] ?? r} <span className='opacity-70'>{count}</span>
              </Badge>
            </button>
          );
        })}
      </div>
    </div>
  );
}
