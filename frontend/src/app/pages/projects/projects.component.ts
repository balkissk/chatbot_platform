import { Component, OnInit } from '@angular/core';
import { ApiService } from '../../services/api';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './projects.component.html',
  styleUrls: ['./projects.component.css']
})
export class ProjectsComponent implements OnInit {

  projects: any[] = [];
  newProjectName: string = '';

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadProjects();
  }

  loadProjects() {
    this.api.getProjects().subscribe((res: any) => {
      this.projects = res;
    });
  }

  createProject() {
    if (!this.newProjectName) return;

    this.api.createProject({
      name: this.newProjectName,
      description: "demo",
      user_id: 1
    }).subscribe(() => {
      this.newProjectName = '';
      this.loadProjects();
    });
  }
}
