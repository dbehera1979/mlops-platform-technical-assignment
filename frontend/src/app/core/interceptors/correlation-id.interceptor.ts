import { HttpInterceptorFn } from '@angular/common/http';

/** Generates a correlation id per outgoing request if one isn't already
 * set, and echoes it into the console in dev — this is what threads a
 * single UI action through every backend log line and deployment event
 * (architecture.md §9). The backend echoes it back on X-Correlation-Id;
 * a future iteration surfaces that in a "copy trace id" UI affordance. */
export const correlationIdInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.headers.has('X-Correlation-Id')) return next(req);
  const correlationId = crypto.randomUUID();
  return next(req.clone({ setHeaders: { 'X-Correlation-Id': correlationId } }));
};
