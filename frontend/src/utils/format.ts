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
