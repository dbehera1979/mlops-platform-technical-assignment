import { ApiError } from './api-error.model';

/** Uniform loading/empty/success/error shape every list-consuming
 * component renders from — this is what the state-message shared
 * component switches on, so every feature gets the same four states
 * (mandatory Angular GUI scope) for free instead of reinventing it
 * per view. */
export type RemoteData<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'success'; data: T };

export const idle = <T>(): RemoteData<T> => ({ status: 'idle' });
export const loading = <T>(): RemoteData<T> => ({ status: 'loading' });
export const success = <T>(data: T): RemoteData<T> => ({ status: 'success', data });
export const failure = <T>(error: ApiError): RemoteData<T> => ({ status: 'error', error });
