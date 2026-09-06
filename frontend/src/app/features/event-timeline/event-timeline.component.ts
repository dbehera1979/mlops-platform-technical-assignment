import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { BehaviorSubject, combineLatest, map } from 'rxjs';
import { Deployment } from '../../core/models/deployment.model';
import { RemoteData } from '../../core/models/remote-data.model';
import { DeploymentService } from '../../core/services/deployment.service';
import { StateMessageComponent } from '../../shared/components/state-message/state-message.component';
import { StatusChipComponent } from '../../shared/components/status-chip/status-chip.component';

interface TimelineEntry {
  deploymentId: string;
  environment: string;
  modelVersionId: string;
  from_status: string | null;
  to_status: string;
  message: string | null;
  correlation_id: string | null;
  reconciled: boolean;
  created_at: string;
}

const ENVIRONMENT_OPTIONS = ['', 'DEV', 'STAGING', 'PRODUCTION'];

/** Event Timeline: a global, filterable feed of every deployment
 * transition across the platform — flattened client-side from
 * GET /deployments (each deployment already carries its own event
 * trail), rather than a dedicated backend endpoint. Reasonable for this
 * take-home's volume; architecture.md Q6 covers what changes once event
 * volume actually requires server-side pagination/partitioning. */
@Component({
  selector: 'app-event-timeline',
  standalone: true,
  imports: [CommonModule, FormsModule, MatFormFieldModule, MatSelectModule, MatIconModule, StateMessageComponent, StatusChipComponent],
  templateUrl: './event-timeline.component.html',
  styleUrl: './event-timeline.component.scss',
})
export class EventTimelineComponent implements OnInit {
  readonly environmentOptions = ENVIRONMENT_OPTIONS;
  private readonly environmentFilterSubject = new BehaviorSubject<string>('');
  readonly entriesState$;

  get environmentFilter(): string {
    return this.environmentFilterSubject.value;
  }
  set environmentFilter(value: string) {
    this.environmentFilterSubject.next(value);
  }

  constructor(private readonly deployments: DeploymentService) {
    this.entriesState$ = combineLatest([this.deployments.list$, this.environmentFilterSubject]).pipe(
      map(([state, environmentFilter]): RemoteData<TimelineEntry[]> => {
        if (state.status !== 'success') return state as RemoteData<TimelineEntry[]>;
        const entries = this.flatten(state.data).filter(
          (e) => !environmentFilter || e.environment === environmentFilter
        );
        return { status: 'success', data: entries };
      })
    );
  }

  ngOnInit(): void {
    this.deployments.loadDeployments();
  }

  refresh(): void {
    this.deployments.loadDeployments();
  }

  isEmpty(state: RemoteData<TimelineEntry[]>): boolean {
    return state.status === 'success' && state.data.length === 0;
  }

  private flatten(deployments: Deployment[]): TimelineEntry[] {
    const entries: TimelineEntry[] = [];
    for (const deployment of deployments) {
      for (const event of deployment.events) {
        entries.push({
          deploymentId: deployment.id,
          environment: deployment.environment,
          modelVersionId: deployment.model_version_id,
          from_status: event.from_status ?? null,
          to_status: event.to_status,
          message: event.message ?? null,
          correlation_id: event.correlation_id ?? null,
          reconciled: event.reconciled,
          created_at: event.created_at,
        });
      }
    }
    return entries.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }
}
