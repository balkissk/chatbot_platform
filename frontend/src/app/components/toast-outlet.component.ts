import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { ToastService } from '../services/toast.service';

@Component({
  selector: 'app-toast-outlet',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="toast-stack" role="status" aria-live="polite" aria-atomic="true">
      <button
        *ngFor="let toast of toastService.toasts()"
        type="button"
        class="toast-item"
        [class.success]="toast.tone === 'success'"
        [class.error]="toast.tone === 'error'"
        [class.warning]="toast.tone === 'warning'"
        (click)="toastService.dismiss(toast.id)">
        {{ toast.message }}
      </button>
    </div>
  `,
  styles: [`
    .toast-stack{display:grid;gap:8px;inset:auto 18px 18px auto;max-width:min(360px,calc(100vw - 36px));position:fixed;z-index:2400}
    .toast-item{background:rgba(255,255,255,.96);border:1px solid var(--ds-border);border-radius:12px;box-shadow:0 18px 44px rgba(24,59,74,.16);color:var(--ds-text);font:700 13px/1.35 Inter,Arial,sans-serif;min-height:0;padding:10px 12px;text-align:left}
    .toast-item.success{border-color:rgba(34,197,94,.35)}
    .toast-item.error{border-color:rgba(239,68,68,.38);color:var(--danger)}
    .toast-item.warning{border-color:rgba(245,158,11,.38)}
  `]
})
export class ToastOutletComponent {
  constructor(public toastService: ToastService) {}
}
