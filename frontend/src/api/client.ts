import createClient, { type Middleware } from 'openapi-fetch';

import type { components, paths } from './schema';

export type Schemas = components['schemas'];
export type User = Schemas['UserOut'];
export type Me = Schemas['MeOut'];
export type Token = Schemas['TokenOut'];
export type CreatedToken = Schemas['TokenCreatedOut'];
export type Role = Schemas['RoleOut'];

const CSRF_COOKIE = 'repoman_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

function readCookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

// Double-submit CSRF protection for cookie-session requests.
const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method)) {
      const csrf = readCookie(CSRF_COOKIE);
      if (csrf) {
        request.headers.set(CSRF_HEADER, decodeURIComponent(csrf));
      }
    }
    return request;
  },
};

// Same origin: the reverse proxy routes /api/ to the backend.
export const api = createClient<paths>({ baseUrl: window.location.origin });
api.use(csrfMiddleware);
