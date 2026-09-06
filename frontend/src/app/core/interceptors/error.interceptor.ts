import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { ApiError, ApiErrorEnvelope } from '../models/api-error.model';

/** Normalizes every failed response into an ApiError with `.code`, so
 * feature components branch on `error.code` (e.g. 'PROMOTION_GATE_VIOLATION')
 * instead of parsing prose — matches the envelope in
 * backend/app/core/exceptions.py exactly. */
export const errorInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.error && typeof err.error === 'object' && 'error' in err.error) {
        return throwError(() => new ApiError(err.status, err.error as ApiErrorEnvelope));
      }
      return throwError(
        () =>
          new ApiError(err.status, {
            error: { code: 'UNKNOWN_ERROR', message: err.message || 'Request failed' },
          })
      );
    })
  );
