export function formatDateTime(value: string | null | undefined, language: string): string {
  if (!value) {
    return '—';
  }
  return new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  );
}

export function displayName(user: { username: string; display_name: string | null }): string {
  return user.display_name || user.username;
}

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];

export function formatBytes(value: number | null | undefined, language: string): string {
  if (value === null || value === undefined) {
    return '—';
  }
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < BYTE_UNITS.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || size >= 100 ? 0 : 1;
  return `${new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(size)} ${BYTE_UNITS[unit]}`;
}
