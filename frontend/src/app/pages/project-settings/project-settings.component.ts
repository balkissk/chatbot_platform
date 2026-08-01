import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-project-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './project-settings.component.html',
  styleUrls: ['./project-settings.component.css']
})
export class ProjectSettingsComponent implements OnInit {
  projectId = 0;
  project = signal<any | null>(null);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  message = signal('');

  name = '';
  description = '';

  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.loadProject();
  }

  loadProject() {
    this.loading.set(true);
    this.error.set('');
    this.api.getProject(this.projectId, true).subscribe({
      next: project => {
        this.project.set(project);
        this.name = project.name || '';
        this.description = project.description || '';
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load project settings');
        this.loading.set(false);
      }
    });
  }

  canSave() {
    const project = this.project();
    const name = this.name.trim();
    const description = this.description.trim() || 'No description';
    return Boolean(project && name) && (
      name !== String(project.name || '').trim() ||
      description !== String(project.description || 'No description').trim()
    );
  }

  saveProject() {
    const name = this.name.trim();
    if (!name) {
      this.error.set('Project name is required');
      return;
    }

    this.saving.set(true);
    this.error.set('');
    this.message.set('');

    this.api.updateProject(this.projectId, {
      name,
      description: this.description.trim() || 'No description'
    }).subscribe({
      next: project => {
        this.project.set(project);
        this.name = project.name || '';
        this.description = project.description || '';
        this.message.set('Project settings saved');
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save project settings');
        this.saving.set(false);
      }
    });
  }
}
