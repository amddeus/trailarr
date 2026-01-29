export enum MediaServerType {
  Emby = 'emby',
  Jellyfin = 'jellyfin',
  Plex = 'plex',
}

export interface MediaServerCreate {
  name: string;
  server_type: MediaServerType;
  url: string;
  api_key: string;
  enabled: boolean;
}

export interface MediaServerRead {
  id: number;
  name: string;
  server_type: MediaServerType;
  url: string;
  api_key: string;
  enabled: boolean;
  added_at: string;
}

export interface MediaServerUpdate {
  name?: string;
  server_type?: MediaServerType;
  url?: string;
  api_key?: string;
  enabled?: boolean;
}
