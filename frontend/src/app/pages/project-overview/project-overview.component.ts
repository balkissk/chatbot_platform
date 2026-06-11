import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-project-overview',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './project-overview.component.html',
  styleUrls: ['./project-overview.component.css']
})
export class ProjectOverviewComponent implements OnInit {
  projectId!: number;
  project = signal<any | null>(null);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  message = signal('');

  editing = false;
  editName = '';
  editDescription = '';

  private isBrowser: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
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

    this.api.getProject(this.projectId).subscribe({
      next: project => {
        this.project.set(project);
        this.editName = project.name;
        this.editDescription = project.description || '';
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load project');
        this.loading.set(false);
      }
    });
  }

  startEdit() {
    const project = this.project();
    if (!project) return;

    this.editing = true;
    this.editName = project.name;
    this.editDescription = project.description || '';
    this.message.set('');
  }

  cancelEdit() {
    this.editing = false;
    this.message.set('');
  }

  saveProject() {
    const name = this.editName.trim();
    if (!name) {
      this.error.set('Project name is required');
      return;
    }

    this.saving.set(true);
    this.error.set('');
    this.message.set('');

    this.api.updateProject(this.projectId, {
      name,
      description: this.editDescription.trim() || 'No description'
    }).subscribe({
      next: project => {
        this.project.set(project);
        this.editName = project.name;
        this.editDescription = project.description || '';
        this.editing = false;
        this.message.set('Project updated');
        this.saving.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update project');
        this.saving.set(false);
      }
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/projects']);
  }
}
