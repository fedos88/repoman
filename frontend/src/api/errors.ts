import type { TFunction } from 'i18next';

import type { Schemas } from './client';

type ErrorResponse = Schemas['ErrorResponse'];

/** Error thrown by API hooks; carries the HTTP status and the stable error code. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export function toApiError(error: unknown, response: Response): ApiError {
  const body = (error ?? {}) as Partial<ErrorResponse>;
  return new ApiError(
    response.status,
    body.error?.code ?? 'unknown_error',
    body.error?.message ?? response.statusText,
  );
}

/** Unwraps an openapi-fetch result, throwing ApiError on failure. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw toApiError(result.error, result.response);
  }
  return result.data as T;
}

/** Localized message for an API error (translated by its code). */
export function errorMessage(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    return t(`errors.${error.code}`, { defaultValue: t('errors.unknown_error') });
  }
  return t('errors.network_error');
}
