/** Display only. Authentication stays exclusively in the existing nginx/gateway.
 * Never authorize a request or grant a role from this projection of a cookie.
 * The signed cookie reaches production Next only after gateway verification.
 */
export function sessionDisplayName(cookie?: string): string | null {
  if (!cookie || cookie.length > 2048 || cookie.split('.').length !== 2) return null;
  try {
    const [name, expiry] = Buffer.from(cookie.split('.')[0], 'base64url')
      .toString('utf8')
      .split('\n');
    if (
      !name ||
      name.length > 80 ||
      Array.from(name).some(
        (character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127
      ) ||
      !/^\d+$/.test(expiry) ||
      Number(expiry) <= Date.now() / 1000
    )
      return null;
    return name;
  } catch {
    return null;
  }
}
