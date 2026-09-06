import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { AuthService } from '../../core/services/auth.service';
import { ApiError } from '../../core/models/api-error.model';
import { Deployment, TERMINAL_STATUSES } from '../../core/models/deployment.model';
import { RemoteData } from '../../core/models/remote-data.model';
import { DeploymentFilters, DeploymentService } from '../../core/services/deployment.service';
import { StateMessageComponent } from '../../shared/components/state-message/state-message.component';
import { StatusChipComponent } from '../../shared/components/status-chip/status-chip.component';

const ENVIRONMENT_OPTIONS = ['', 'DEV', 'STAGING', 'PRODUCTION'];
const STATUS_OPTIONS = ['', 'REQUESTED', 'VALIDATING', 'DEPLOYING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK'];
const POLL_INTERVAL_MS = 2500;

/** Deployment view: list + filters + retry/rollback actions. Because
 * execution is asynchronous on the backend (ADR-001), this component
 * polls in-flight deployments on an interval rather than expecting a
 * request to hand back a finished result — the same pattern a real
 * dashboard would use before adding a push channel (websocket/SSE). */
@Component({
  selector: 'app-deployment-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTooltipModule,
    StateMessageComponent,
    StatusChipComponent,
  ],
  templateUrl: './deployment-list.component.html',
  styleUrl: './deployment-list.component.scss',
})
export class DeploymentListComponent implements OnInit, OnDestroy {
  readonly environmentOptions = ENVIRONMENT_OPTIONS;
  readonly statusOptions = STATUS_OPTIONS;
  readonly state$: DeploymentService['list$'];

  filters: DeploymentFilters = {};
  actingOn: string | null = null;
  private latest: RemoteData<Deployment[]> = { status: 'idle' };
  private pollHandle: ReturnType<typeof setInterval> | null = null;
  private sub?: Subscription;

  constructor(
    private readonly deployments: DeploymentService,
    private readonly snackBar: MatSnackBar,
    readonly auth: AuthService
  ) {
    this.state$ = this.deployments.list$;
  }

  ngOnInit(): void {
    this.sub = this.state$.subscribe((state) => (this.latest = state));
    this.refresh();
    // Light polling so in-flight (non-terminal) deployments visibly move
    // through their state machine without a manual refresh.
    this.pollHandle = setInterval(() => this.refreshIfHasInFlight(), POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.sub?.unsubscribe();
  }

  refresh(): void {
    this.deployments.loadDeployments(this.filters);
  }

  private refreshIfHasInFlight(): void {
    if (this.latest.status === 'success' && this.latest.data.some((d) => !TERMINAL_STATUSES.includes(d.status))) {
      this.deployments.loadDeployments(this.filters);
    }
  }

  isEmpty(state: RemoteData<Deployment[]>): boolean {
    return state.status === 'success' && state.data.length === 0;
  }

  isTerminal(status: string): boolean {
    return TERMINAL_STATUSES.includes(status as Deployment['status']);
  }

  async retry(deployment: Deployment): Promise<void> {
    this.actingOn = deployment.id;
    try {
      await this.deployments.retry(deployment.id);
      this.snackBar.open('Retry requested', undefined, { duration: 2500 });
      this.refresh();
    } catch (err) {
      this.snackBar.open((err as ApiError).message || 'Retry failed', undefined, { duration: 3500 });
    } finally {
      this.actingOn = null;
    }
  }

  async rollback(deployment: Deployment): Promise<void> {
    this.actingOn = deployment.id;
    try {
      await this.deployments.rollback(deployment.id);
      this.snackBar.open('Rollback requested', undefined, { duration: 2500 });
      this.refresh();
    } catch (err) {
      this.snackBar.open((err as ApiError).message || 'Rollback failed', undefined, { duration: 3500 });
    } finally {
      this.actingOn = null;
    }
  }
}
