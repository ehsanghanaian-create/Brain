import { describe, expect, it } from 'vitest';
import { MENU_BENCHMARKS, benchmarkScale } from '../benchmarks';

describe('independent device viewports', () => {
  it('uses landscape desktop and portrait phone dimensions', () => {
    const desktop = MENU_BENCHMARKS.find((item) => item.id === 'laptop')!;
    const phone = MENU_BENCHMARKS.find((item) => item.id === 'mobile')!;
    expect(desktop.width / desktop.height).toBeGreaterThan(1.5);
    expect(phone.height / phone.width).toBeGreaterThan(2);
    expect(desktop.height).not.toBe(phone.height);
  });
  it('scales only presentation while preserving the iframe CSS viewport', () => {
    const target = MENU_BENCHMARKS[0];
    const scale = benchmarkScale(720, target.width);
    expect(scale).toBe(0.5);
    expect(target.width * scale).toBe(720);
    expect(target.height * scale).toBe(450);
    expect(benchmarkScale(2000, target.width)).toBe(1);
  });
});
