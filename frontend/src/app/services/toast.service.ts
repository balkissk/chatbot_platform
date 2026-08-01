import { Injectable, signal } from '@angular/core';

export type ToastTone = 'success' | 'error' | 'warning' | 'info';

export type ToastMessage = {
  id: number;
  message: string;
  tone: ToastTone;
};

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<ToastMessage[]>([]);
  private nextId = 1;

  show(message: string, tone: ToastTone = 'info') {
    const toast = { id: this.nextId++, message, tone };
    this.toasts.update(items => [...items, toast]);
    setTimeout(() => this.dismiss(toast.id), 4200);
  }

  success(message: string) {
    this.show(message, 'success');
  }

  error(message: string) {
    this.show(message, 'error');
  }

  dismiss(id: number) {
    this.toasts.update(items => items.filter(item => item.id !== id));
  }
}
