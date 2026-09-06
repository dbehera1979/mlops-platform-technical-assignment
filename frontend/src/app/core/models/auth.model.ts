export type DemoRole = 'admin' | 'approver' | 'operator' | 'viewer';

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface CurrentUser {
  username: DemoRole;
  roles: DemoRole[];
}
