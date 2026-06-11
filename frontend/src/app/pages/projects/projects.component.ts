import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, computed, signal } from '@angular/core';
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
  hasMore = signal(false);
  loadingMore = signal(false);
  error = signal('');

  search = '';
  newProjectName = '';
  newProjectDescription = '';
  editingId?: number;
  editName = '';
  editDescription = '';

  totalProjects = computed(() => this.projects().length);
  totalChatbots = computed(() => this.projects().reduce((sum, project) => sum + this.count(project, 'chatbot_count'), 0));
  publishedChatbots = computed(() => this.projects().reduce((sum, project) => sum + this.count(project, 'published_version_count'), 0));
  totalConversations = computed(() => this.projects().reduce((sum, project) => sum + this.count(project, 'conversation_count'), 0));
  draftProjects = computed(() => this.projects().filter(project => this.count(project, 'published_version_count') === 0).length);
  activeProjects = computed(() => this.projects().filter(project => this.count(project, 'chatbot_count') > 0).length);

  private isBrowser: boolean;
  private searchTimer?: ReturnType<typeof setTimeout>;
  private readonly pageSize = 50;
  private offset = 0;

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

  loadProjects(force = false, append = false) {
    if (!this.isBrowser) return;

    if (!append) {
      this.offset = 0;
      this.loading.set(true);
    } else {
      this.loadingMore.set(true);
    }
    this.error.set('');

    this.api.getProjects(this.search, force, this.pageSize, this.offset).subscribe({
      next: projects => {
        this.projects.set(append ? [...this.projects(), ...projects] : projects);
        this.hasMore.set(projects.length === this.pageSize);
        this.offset += projects.length;
        this.loading.set(false);
        this.loadingMore.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load projects');
        this.loading.set(false);
        this.loadingMore.set(false);
      }
    });
  }

  loadMore() {
    if (!this.hasMore() || this.loadingMore()) return;
    this.loadProjects(false, true);
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
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.loadProjects(true), 250);
  }

  resetSearch() {
    this.search = '';
    this.loadProjects();
  }

  projectStatus(project: any) {
    if (this.count(project, 'published_version_count') > 0) return 'Published';
    if (this.count(project, 'chatbot_count') > 0) return 'Draft';
    return 'Empty';
  }

  resultLabel() {
    const total = this.projects().length;
    if (!this.search.trim()) return `${total} project${total === 1 ? '' : 's'}`;
    return `${total} result${total === 1 ? '' : 's'} for "${this.search.trim()}"`;
  }

  trend(...keys: string[]) {
    for (const project of this.projects()) {
      for (const key of keys) {
        if (project?.[key] !== undefined && project?.[key] !== null) return Number(project[key]);
      }
    }
    return undefined;
  }

  scrollToCreate() {
    if (!this.isBrowser) return;
    document.querySelector('.create-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  private count(project: any, key: string) {
    return Number(project?.[key] || 0);
  }
}
