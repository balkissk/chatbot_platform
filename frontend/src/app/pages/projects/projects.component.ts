import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './projects.component.html',
  styleUrls: ['./projects.component.css']
})
export class ProjectsComponent implements OnInit {
  projects = signal<any[]>([]);
  loading = signal(false);
  creating = signal(false);
  savingId = signal<number | undefined>(undefined);
  deletingId = signal<number | undefined>(undefined);
  error = signal('');

  search = '';
  newProjectName = '';
  newProjectDescription = '';
  editingId?: number;
  editName = '';
  editDescription = '';

  private isBrowser: boolean;

  constructor(
    private api: ApiService,
    @Inject(PLATFORM_ID) platformId: object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit() {
    if (!this.isBrowser) return;
    this.loadProjects();
  }

  loadProjects() {
    if (!this.isBrowser) return;

    this.loading.set(true);
    this.error.set('');

    this.api.getProjects(this.search).subscribe({
      next: projects => {
        this.projects.set(projects);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load projects');
        this.loading.set(false);
      }
    });
  }

  createProject() {
    const name = this.newProjectName.trim();
    if (!name) return;

    this.creating.set(true);
    this.error.set('');

    this.api.createProject({
      name,
      description: this.newProjectDescription.trim() || 'No description'
    }).subscribe({
      next: () => {
        this.newProjectName = '';
        this.newProjectDescription = '';
        this.creating.set(false);
        this.loadProjects();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not create project');
        this.creating.set(false);
      }
    });
  }

  startEdit(project: any) {
    this.editingId = project.id;
    this.editName = project.name;
    this.editDescription = project.description || '';
  }

  cancelEdit() {
    this.editingId = undefined;
    this.editName = '';
    this.editDescription = '';
  }

  saveProject(project: any) {
    const name = this.editName.trim();
    if (!name) {
      this.error.set('Project name is required');
      return;
    }

    this.savingId.set(project.id);
    this.error.set('');

    this.api.updateProject(project.id, {
      name,
      description: this.editDescription.trim() || 'No description'
    }).subscribe({
      next: () => {
        this.savingId.set(undefined);
        this.cancelEdit();
        this.loadProjects();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update project');
        this.savingId.set(undefined);
      }
    });
  }

  deleteProject(project: any) {
    if (!confirm(`Delete project "${project.name}" and all its chatbots?`)) return;

    this.deletingId.set(project.id);
    this.error.set('');

    this.api.deleteProject(project.id).subscribe({
      next: () => {
        this.deletingId.set(undefined);
        this.loadProjects();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not delete project');
        this.deletingId.set(undefined);
      }
    });
  }

  updateSearch(value: string) {
    this.search = value;
    this.loadProjects();
  }

  resetSearch() {
    this.search = '';
    this.loadProjects();
  }
}
