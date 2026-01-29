import {CommonModule} from '@angular/common';
import {ChangeDetectionStrategy, Component, inject, signal} from '@angular/core';
import {RouterLink} from '@angular/router';
import {MediaServerService} from 'src/app/services/mediaserver.service';
import {LoadIndicatorComponent} from 'src/app/shared/load-indicator';
import {RouteAdd, RouteMediaServers, RouteSettings} from 'src/routing';

@Component({
  selector: 'app-show-mediaservers',
  templateUrl: './show-mediaservers.component.html',
  styleUrl: './show-mediaservers.component.scss',
  imports: [CommonModule, LoadIndicatorComponent, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShowMediaServersComponent {
  private readonly mediaServerService = inject(MediaServerService);

  protected readonly mediaServersResource = this.mediaServerService.mediaServersResource;
  protected readonly isLoading = this.mediaServersResource.isLoading;

  resultMessage = signal<string>('');
  resultType = signal<string>('');
  selectedId = 0;

  protected readonly RouteAdd = RouteAdd;
  protected readonly RouteMediaServers = RouteMediaServers;
  protected readonly RouteSettings = RouteSettings;

  getServerTypeLogo(serverType: string): string {
    switch (serverType) {
      case 'emby':
        return 'assets/trailarr-64.png';
      case 'jellyfin':
        return 'assets/trailarr-64.png';
      case 'plex':
        return 'assets/trailarr-64.png';
      default:
        return 'assets/trailarr-64.png';
    }
  }
}
