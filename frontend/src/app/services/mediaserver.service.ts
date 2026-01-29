import {HttpClient, httpResource} from '@angular/common/http';
import {computed, inject, Injectable, signal} from '@angular/core';
import {catchError, Observable} from 'rxjs';
import {MediaServerCreate, MediaServerRead, MediaServerType, MediaServerUpdate} from 'src/app/models/mediaserver';
import {environment} from 'src/environment';
import {handleError} from './utils';
import {WebsocketService} from './websocket.service';

@Injectable({
  providedIn: 'root',
})
export class MediaServerService {
  private readonly http = inject(HttpClient);
  private readonly websocketService = inject(WebsocketService);

  private mediaServersUrl = environment.apiUrl + environment.mediaservers;

  readonly mediaServersResource = httpResource<MediaServerRead[]>(() => ({url: this.mediaServersUrl}), {
    defaultValue: [],
  });

  private readonly newMediaServer = {
    added_at: new Date().toISOString(),
    api_key: '',
    enabled: true,
    id: -1,
    name: '',
    server_type: MediaServerType.Emby,
    url: '',
  } as MediaServerRead;

  readonly mediaServerID = signal<number>(-1);

  readonly selectedMediaServer = computed(() => {
    const server = this.mediaServersResource.value().find((s) => s.id === this.mediaServerID());
    return server ? server : this.newMediaServer;
  });

  addMediaServer(mediaServer: MediaServerCreate): Observable<MediaServerRead> {
    return this.http.post<MediaServerRead>(this.mediaServersUrl, mediaServer).pipe(catchError(handleError()));
  }

  mediaServerExists(id: number): boolean {
    const exists = this.mediaServersResource.value().some((s) => s.id === id);
    if (exists) return true;
    if (id != -1) this.websocketService.showToast(`Media Server with ID '${id}' does not exist.`, 'error');
    return false;
  }

  deleteMediaServer(id: number): Observable<string> {
    const url = this.mediaServersUrl + id;
    return this.http.delete<string>(url).pipe(catchError(handleError()));
  }

  testMediaServer(mediaServer: MediaServerCreate): Observable<string> {
    const url = this.mediaServersUrl + 'test';
    return this.http.post<string>(url, mediaServer).pipe(catchError(handleError()));
  }

  updateMediaServer(id: number, mediaServer: MediaServerUpdate): Observable<MediaServerRead> {
    const url = this.mediaServersUrl + id;
    return this.http.put<MediaServerRead>(url, mediaServer).pipe(catchError(handleError()));
  }

  refreshLibrary(id: number, folderPath: string = ''): Observable<string> {
    let url = this.mediaServersUrl + id + '/refresh';
    if (folderPath) {
      url += '?folder_path=' + encodeURIComponent(folderPath);
    }
    return this.http.post<string>(url, {}).pipe(catchError(handleError()));
  }
}
