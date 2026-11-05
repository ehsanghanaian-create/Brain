/** Pick readable status-badge text for an explicitly supplied opaque hex fill.
 * Theme tokens, gradients and transparent fills keep their existing styling.
 */
export function solidColorForeground(color: unknown): string | undefined {
  if (typeof color !== 'string') return;
  const match = color.trim().match(/^#([\da-f]{3}|[\da-f]{6})$/i);
  if (!match) return;
  const hex =
    match[1].length === 3 ? [...match[1]].map((value) => value + value).join('') : match[1];
  const linear = [0, 2, 4].map((index) => {
    const value = parseInt(hex.slice(index, index + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  const luminance = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  return (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) ? '#000000' : '#ffffff';
}
