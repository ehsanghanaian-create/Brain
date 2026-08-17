import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const fa = new Intl.NumberFormat('fa-IR');

export function KpiCard({ label, value, hint }: { label: string; value: number | string | null | undefined; hint?: string }) {
  const display = value === null || value === undefined ? '—' : typeof value === 'number' ? fa.format(value) : value;
  return (
    <Card className='@container/card'>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className='text-2xl font-semibold tabular-nums @[250px]/card:text-3xl'>{display}</CardTitle>
        {hint && <p className='text-muted-foreground text-xs'>{hint}</p>}
      </CardHeader>
    </Card>
  );
}
