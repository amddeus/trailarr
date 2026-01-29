import {UpperCasePipe} from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  effect,
  ElementRef,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import {Field, form, maxLength, minLength, pattern, required} from '@angular/forms/signals';
import {Router} from '@angular/router';
import {MediaServerCreate, MediaServerType} from 'src/app/models/mediaserver';
import {MediaServerService} from 'src/app/services/mediaserver.service';
import {LoadIndicatorComponent} from 'src/app/shared/load-indicator';

@Component({
  selector: 'app-edit-mediaserver',
  imports: [Field, LoadIndicatorComponent, UpperCasePipe],
  templateUrl: './edit-mediaserver.component.html',
  styleUrl: './edit-mediaserver.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EditMediaServerComponent {
  private readonly changeDetectorRef = inject(ChangeDetectorRef);
  private readonly router = inject(Router);
  private readonly mediaServerService = inject(MediaServerService);

  mediaServerId = input(0, {
    transform: (value: unknown) => {
      const num = Number(value);
      return isNaN(num) ? -1 : num;
    },
  });

  readonly serverTypeOptions: MediaServerType[] = [MediaServerType.Emby, MediaServerType.Jellyfin, MediaServerType.Plex];

  mediaServerCreate = signal<MediaServerCreate>({
    api_key: '',
    enabled: true,
    name: '',
    server_type: MediaServerType.Emby,
    url: '',
  });

  isCreate = signal(false);
  isConnectionTested = signal(false);
  isReadyToSubmit = signal(false);
  isSubmitting = signal(false);
  submitResult = signal<string>('');

  mediaServerForm = form(this.mediaServerCreate, (schema) => {
    required(schema.api_key, {message: 'API Key is required.'});
    minLength(schema.api_key, 10, {message: 'API Key must be at least 10 characters long.'});
    maxLength(schema.api_key, 200, {message: 'API Key cannot be longer than 200 characters.'});
    required(schema.name, {message: 'Name is required.'});
    minLength(schema.name, 3, {message: 'Name must be at least 3 characters long.'});
    required(schema.url, {message: 'URL is required.'});
    minLength(schema.url, 5, {message: 'URL must be at least 5 characters long.'});
    pattern(schema.url, /^https?:\/\/.*/, {message: 'URL must start with http:// or https://.'});
  });

  mediaServer = this.mediaServerService.selectedMediaServer;
  isLoading = this.mediaServerService.mediaServersResource.isLoading;

  mediaServerIDeffect = effect(() => {
    const id = this.mediaServerId();
    if (this.isLoading()) {
      return;
    }
    if (id == -1) {
      this.isCreate.set(true);
    } else if (!this.mediaServerService.mediaServerExists(id)) {
      this.router.navigate(['/settings/mediaservers']);
      return;
    }
    this.mediaServerService.mediaServerID.set(id);
  });

  mediaServerEffect = effect(() => {
    if (this.isSubmitting()) return;
    const server = this.mediaServer();
    if (server && !this.isSubmitting()) {
      this.mediaServerCreate.set(server);
      this.isCreate.set(server.id === -1);
      this.isConnectionTested.set(false);
      this.isReadyToSubmit.set(false);
      this.submitResult.set('');
      this.changeDetectorRef.markForCheck();
    }
  });

  private readonly cancelDialog = viewChild<ElementRef<HTMLDialogElement>>('cancelDialog');
  private readonly deleteDialog = viewChild<ElementRef<HTMLDialogElement>>('deleteMediaServerDialog');
  protected closeDeleteDialog = () => this.deleteDialog()?.nativeElement.close();
  protected showDeleteDialog = () => this.deleteDialog()?.nativeElement.showModal();
  protected closeCancelDialog = () => this.cancelDialog()?.nativeElement.close();
  protected showCancelDialog = () => this.cancelDialog()?.nativeElement.showModal();

  checkFormValidity() {
    if (!this.mediaServerForm().valid()) {
      this.submitResult.set('Form is invalid, please correct the errors and try again.');
      return false;
    }
    return true;
  }

  onCancel() {
    if (this.mediaServerForm().dirty()) {
      this.showCancelDialog();
    } else {
      this.router.navigate(['/settings/mediaservers']);
    }
  }

  onConfirmCancel() {
    this.closeCancelDialog();
    this.router.navigate(['/settings/mediaservers']);
  }

  onConfirmDelete() {
    this.closeDeleteDialog();
    this.deleteMediaServer();
  }

  onSubmit($event: Event) {
    $event.preventDefault();
    if (!this.checkFormValidity()) return;

    if (!this.isConnectionTested()) {
      this.testConnection();
      return;
    }

    if (this.isCreate()) {
      this.createMediaServer();
    } else {
      this.updateMediaServer();
    }
  }

  createMediaServer() {
    if (!this.checkFormValidity()) return;
    if (this.isSubmitting()) return;
    this.isSubmitting.set(true);
    this.submitResult.set('Creating media server, please wait...');
    const data = this.mediaServerCreate();
    this.mediaServerService.addMediaServer(data).subscribe({
      next: () => {
        this.submitResult.set('Media server created successfully!');
        setTimeout(() => {
          this.router.navigate(['/settings/mediaservers']).then(() => {
            this.mediaServerService.mediaServersResource.reload();
          });
        }, 2000);
      },
      error: (error) => {
        this.isSubmitting.set(false);
        this.submitResult.set(`Error creating media server: ${error.message || error}`);
      },
    });
  }

  deleteMediaServer() {
    if (!this.mediaServerService.mediaServerExists(this.mediaServerId())) return;
    this.mediaServerService.deleteMediaServer(this.mediaServerId()).subscribe({
      next: () => {
        this.submitResult.set('Media server deleted successfully!');
        this.mediaServerService.mediaServersResource.reload();
        setTimeout(() => {
          this.router.navigate(['/settings/mediaservers']).then(() => {
            this.mediaServerService.mediaServersResource.reload();
          });
        }, 2000);
      },
      error: (error) => {
        this.submitResult.set(`Error deleting media server: ${error.message || error}`);
      },
    });
  }

  testConnection() {
    if (!this.checkFormValidity()) return;
    const data = this.mediaServerCreate();
    this.submitResult.set('Testing connection...');
    this.mediaServerService.testMediaServer(data).subscribe({
      next: (result) => {
        this.submitResult.set(result);
        if (result.toLowerCase().includes('success')) {
          this.isConnectionTested.set(true);
          this.isReadyToSubmit.set(true);
          this.submitResult.update((val) => `${val}\nConnection tested successfully. You can now submit.`);
        }
      },
      error: (error) => {
        this.submitResult.set(`Connection failed: ${error.message || error}`);
      },
    });
  }

  updateMediaServer() {
    if (!this.checkFormValidity()) return;
    if (this.isSubmitting()) return;
    this.isSubmitting.set(true);
    this.submitResult.set('Updating media server, please wait...');
    const data = this.mediaServerCreate();
    this.mediaServerService.updateMediaServer(this.mediaServerId(), data).subscribe({
      next: () => {
        this.submitResult.set('Media server updated successfully!');
        setTimeout(() => {
          this.router.navigate(['/settings/mediaservers']).then(() => {
            this.mediaServerService.mediaServersResource.reload();
          });
        }, 2000);
      },
      error: (error) => {
        this.isSubmitting.set(false);
        this.submitResult.set(`Error updating media server: ${error.message || error}`);
      },
    });
  }
}
