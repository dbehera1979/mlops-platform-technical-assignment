import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ApiError } from '../../core/models/api-error.model';
import { AuthService } from '../../core/services/auth.service';
import { DeploymentService } from '../../core/services/deployment.service';

const ENVIRONMENTS = ['STAGING', 'PRODUCTION', 'DEV'];

@Component({
  selector: 'app-request-deployment-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './request-deployment-dialog.component.html',
})
export class RequestDeploymentDialogComponent {
  readonly environments = ENVIRONMENTS;
  readonly form;
  submitting = false;
  errorMessage: string | null = null;

  constructor(
    private readonly fb: FormBuilder,
    private readonly deployments: DeploymentService,
    private readonly auth: AuthService,
    private readonly ref: MatDialogRef<RequestDeploymentDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { modelVersionId: string; versionLabel: string }
  ) {
    this.form = this.fb.group({
      environment: ['STAGING', Validators.required],
      simulate_failure: [false],
    });
  }

  async submit(): Promise<void> {
    if (this.form.invalid) return;
    this.submitting = true;
    this.errorMessage = null;
    try {
      const v = this.form.getRawValue();
      const deployment = await this.deployments.requestDeployment({
        model_version_id: this.data.modelVersionId,
        environment: v.environment!,
        idempotency_key: `${this.data.modelVersionId}:${v.environment}:${Date.now()}`,
        requested_by: this.auth.snapshot?.username,
        simulate_failure: v.simulate_failure,
      });
      this.ref.close(deployment);
    } catch (err) {
      const apiError = err as ApiError;
      this.errorMessage =
        apiError.code === 'VALIDATION_FAILED'
          ? apiError.message
          : apiError.code === 'CONFLICT'
          ? 'A deployment is already in progress for this model in that environment.'
          : apiError.message || 'Could not request the deployment.';
    } finally {
      this.submitting = false;
    }
  }
}
