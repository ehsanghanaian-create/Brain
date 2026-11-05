// CSS viewport sizes, not physical dimensions of a device or a product claim.
export const MENU_BENCHMARKS = [
  { id: 'laptop', label: 'لپ‌تاپ', width: 1440, height: 900 },
  { id: 'ipad', label: 'آیپد افقی', width: 1024, height: 768 },
  { id: 'portrait', label: 'آیپد عمودی', width: 768, height: 1024 },
  { id: 'mobile', label: 'موبایل', width: 390, height: 844 }
] as const;

export function benchmarkScale(availableWidth: number, targetWidth: number) {
  return Math.min(1, Math.max(0, availableWidth) / targetWidth);
}
