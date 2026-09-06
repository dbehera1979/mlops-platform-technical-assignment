// Mirrors the envelope produced by app/core/exceptions.py — every error
// response has this shape, so the UI branches on `code`, not on parsing
// prose out of `message`.
export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly httpStatus: number;

  constructor(httpStatus: number, envelope: ApiErrorEnvelope) {
    super(envelope.error.message);
    this.httpStatus = httpStatus;
    this.code = envelope.error.code;
    this.details = envelope.error.details ?? {};
  }
}
