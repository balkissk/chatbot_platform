import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ProjectsComponent } from './projects.component';

describe('Projects', () => {
  let component: ProjectsComponent;
  let fixture: ComponentFixture<ProjectsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProjectsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ProjectsComponent);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('derives workspace insights only from loaded project data', () => {
    component.projects.set([
      { id: 1, name: 'Admissions', status: 'active', assistant_count: 0, published_assistant_count: 0, created_at: '2026-07-01T00:00:00Z' },
      { id: 2, name: 'Support', status: 'active', assistant_count: 2, published_assistant_count: 0, created_at: '2026-07-02T00:00:00Z' }
    ]);
    component.summary.set({ projects: 2, assistants: 2, published_assistants: 0, draft_only: 2 });

    const insights = component.workspaceInsights();

    expect(insights.map(insight => insight.title)).toContain('Assistant setup needed');
    expect(insights.map(insight => insight.title)).toContain('Publication blocker');
  });

  it('marks project readiness from real assistant and publication counts', () => {
    expect(component.projectReadiness({ status: 'archived', assistant_count: 2, published_assistant_count: 1 })).toBe('Archived');
    expect(component.projectReadiness({ status: 'active', assistant_count: 0, published_assistant_count: 0 })).toBe('Needs setup');
    expect(component.projectReadiness({ status: 'active', assistant_count: 1, published_assistant_count: 0 })).toBe('Draft only');
    expect(component.projectReadiness({ status: 'active', assistant_count: 1, published_assistant_count: 1 })).toBe('Ready');
  });
});
