// Mirrors backend rules (repoman.auth.security, repoman.users.names).
export const PASSWORD_MIN_LENGTH = 8;
export const LOCAL_USERNAME_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/;
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
