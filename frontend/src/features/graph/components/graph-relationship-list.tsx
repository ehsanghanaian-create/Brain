'use client';

import type { GraphView } from '@/lib/api/client';
import { NODE_STYLE, RELATION_FA } from '../constants';

/** The same sampled evidence as the map, with explicit direction and keyboard access. */
export function GraphRelationshipList({ view, query, hiddenTypes, hiddenRelations, onSelect }: {
  view: GraphView; query: string; hiddenTypes: Set<string>; hiddenRelations: Set<string>;
  onSelect: (id: string) => void;
}) {
  const nodes = new Map(view.nodes.filter((n) => !hiddenTypes.has(n.type)).map((n) => [n.id, n]));
  const q = query.trim().toLocaleLowerCase();
  const label = (id: string) => String(nodes.get(id)?.metadata.label || id);
  const relations = view.edges.filter((e) => nodes.has(e.source) && nodes.has(e.target) && !hiddenRelations.has(e.relation_type) && (!q || `${label(e.source)} ${label(e.target)}`.toLocaleLowerCase().includes(q)));
  return <section aria-label='فهرست ارتباط‌های گراف' className='graph-panel min-w-0 rounded-2xl p-4'>
    <h2 className='text-base font-semibold'>ارتباط‌ها به زبان ساده</h2>
    <p className='mt-1 text-xs leading-6 text-muted-foreground'>هر ردیف از مبدأ به مقصد خوانده می‌شود. روی نام کلیک کنید تا شواهد و اقدام آن همین‌جا باز شود. این فهرست از نمونهٔ بارگذاری‌شده است، نه همهٔ روابط سایت.</p>
    <p role='status' className='my-3 text-xs text-muted-foreground'>{relations.length.toLocaleString('fa-IR')} رابطه مطابق فیلترها{relations.length > 80 ? '؛ ۸۰ مورد نخست نمایش داده می‌شود.' : ''}</p>
    <ol className='max-h-[560px] space-y-2 overflow-y-auto'>
      {relations.slice(0, 80).map((edge, i) => <li key={`${edge.source}-${edge.target}-${edge.relation_type}-${i}`} className='grid gap-2 rounded-xl border border-border p-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center'>
        <div className='min-w-0'><span className='block text-xs text-muted-foreground'>مبدأ · {NODE_STYLE[nodes.get(edge.source)!.type]?.fa ?? nodes.get(edge.source)!.type}</span><button type='button' onClick={() => onSelect(edge.source)} className='min-h-11 w-full break-words text-start font-medium text-primary underline-offset-4 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'>{label(edge.source)}</button></div>
        <span className='rounded-md bg-muted px-2 py-1 text-xs'>{RELATION_FA[edge.relation_type] ?? edge.relation_type}</span>
        <div className='min-w-0'><span className='block text-xs text-muted-foreground'>مقصد · {NODE_STYLE[nodes.get(edge.target)!.type]?.fa ?? nodes.get(edge.target)!.type}</span><button type='button' onClick={() => onSelect(edge.target)} className='min-h-11 w-full break-words text-start font-medium text-primary underline-offset-4 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'>{label(edge.target)}</button></div>
      </li>)}
    </ol>
    {!relations.length && <p className='rounded-lg bg-muted p-4 text-sm'>رابطه‌ای مطابق این فیلترها نیست. عبارت جست‌وجو یا فیلتر نوع رابطه را تغییر دهید.</p>}
  </section>;
}
