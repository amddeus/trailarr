import {ChangeDetectionStrategy, Component} from '@angular/core';
import {RouterOutlet} from '@angular/router';

@Component({
  selector: 'app-mediaservers',
  imports: [RouterOutlet],
  templateUrl: './mediaservers.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MediaServersComponent {}
