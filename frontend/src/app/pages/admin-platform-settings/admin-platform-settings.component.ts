import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api';

type PlatformSettingsForm = {
  platform_name: string;
  support_email: string;
  default_page_size: number;
};

@Component({
  selector: 'app-admin-platform-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-platform-settings.component.html',
  styleUrls: ['./admin-platform-settings.component.css']
})
export class AdminPlatformSettingsComponent implements OnInit {
  form: PlatformSettingsForm = {
    platform_name: '',
    support_email: '',
    default_page_size: 10
  };
  original: PlatformSettingsForm | null = null;
  metadata = signal<any | null>(null);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  success = signal('');
  private isBrowser: boolean;
  private emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  constructor(
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.load();
  }

  load() {
    if (!this.isBrowser) return;
    this.loading.set(true);
    this.error.set('');
    this.success.set('');

    this.api.getPlatformSettings().subscribe({
      next: settings => {
        this.applySettings(settings);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load platform settings');
        this.loading.set(false);
      }
    });
  }

  save() {
    if (this.saving() || !this.isValid() || !this.hasChanges()) return;
    this.saving.set(true);
    this.error.set('');
    this.success.set('');

    this.api.updatePlatformSettings({
      platform_name: this.form.platform_name.trim(),
      support_email: this.form.support_email.trim().toLowerCase(),
      default_page_size: Number(this.form.default_page_size)
    }).subscribe({
      next: settings => {
        this.applySettings(settings);
        this.success.set('Platform settings saved.');
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save platform settings');
        this.saving.set(false);
      }
    });
  }

  reset() {
    if (!this.original || this.saving()) return;
    this.form = { ...this.original };
    this.error.set('');
    this.success.set('');
  }

  applySettings(settings: any) {
    this.form = {
      platform_name: settings.platform_name || '',
      support_email: settings.support_email || '',
      default_page_size: Number(settings.default_page_size || 10)
    };
    this.original = { ...this.form };
    this.metadata.set({
      updated_at: settings.updated_at,
      updated_by_name: settings.updated_by_name,
      updated_by_email: settings.updated_by_email
    });
  }

  isValid() {
    const name = this.form.platform_name.trim();
    const email = this.form.support_email.trim();
    const pageSize = Number(this.form.default_page_size);
    return Boolean(
      name &&
      name.length <= 80 &&
      this.emailPattern.test(email) &&
      Number.isInteger(pageSize) &&
      pageSize >= 10 &&
      pageSize <= 100
    );
  }

  hasChanges() {
    if (!this.original) return false;
    return (
      this.form.platform_name.trim() !== this.original.platform_name ||
      this.form.support_email.trim().toLowerCase() !== this.original.support_email ||
      Number(this.form.default_page_size) !== Number(this.original.default_page_size)
    );
  }

  platformNameError() {
    const value = this.form.platform_name;
    if (!value.trim()) return 'Platform name is required.';
    if (value.trim().length > 80) return 'Platform name must be 80 characters or fewer.';
    return '';
  }

  supportEmailError() {
    const value = this.form.support_email.trim();
    if (!value) return 'Support email is required.';
    if (!this.emailPattern.test(value)) return 'Enter a valid support email address.';
    return '';
  }

  pageSizeError() {
    const value = Number(this.form.default_page_size);
    if (!Number.isInteger(value) || value < 10 || value > 100) {
      return 'Default page size must be between 10 and 100.';
    }
    return '';
  }
}
