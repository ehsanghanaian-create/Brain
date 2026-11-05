import { describe, expect, it } from 'vitest';
import { solidColorForeground } from '../solid-color-foreground';

describe('status text independent of the primary button theme', () => {
  it('keeps the existing calendar slate status readable after the orange theme change', () => {
    expect(solidColorForeground('#64748b')).toBe('#ffffff');
    expect(solidColorForeground('#a855f7')).toBe('#000000');
    expect(solidColorForeground('#0369a1')).toBe('#ffffff');
  });
  it('chooses dark text on orange and light text on ink', () => {
    expect(solidColorForeground('#EB5E28')).toBe('#000000');
    expect(solidColorForeground('#252422')).toBe('#ffffff');
    expect(solidColorForeground('#fff')).toBe('#000000');
  });
  it('does not guess colors behind gradients or transparency', () => {
    expect(solidColorForeground('var(--primary)')).toBeUndefined();
    expect(solidColorForeground('#ffffff80')).toBeUndefined();
    expect(solidColorForeground(undefined)).toBeUndefined();
  });
});
