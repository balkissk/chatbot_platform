import { CommonModule, DOCUMENT } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';

@Component({
  selector: 'app-documentation',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './documentation.component.html',
  styleUrl: './documentation.component.css'
})
export class DocumentationComponent implements OnInit {
  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    @Inject(DOCUMENT) private readonly document: Document
  ) {}

  activeSectionId = '';

  readonly sections = [
    {
      id: 'getting-started',
      title: 'Getting Started',
      items: ['Create a project', 'Create an assistant', 'Start from Scratch', 'Use a Template', 'Build with AI']
    },
    {
      id: 'flow-builder',
      title: 'Flow Builder',
      items: [
        'Add and configure blocks',
        'Message',
        'Question',
        'Buttons',
        'Collect Name',
        'Collect Email',
        'Collect Phone',
        'Condition',
        'Set Variable',
        'Meeting Preference',
        'Knowledge Search',
        'AI Answer',
        'End',
        'Connect blocks and validate flows'
      ]
    },
    {
      id: 'knowledge-base-rag',
      title: 'Knowledge Base & RAG',
      items: [
        'Upload supported documents',
        'Document processing',
        'Chunking and embeddings',
        'Knowledge Search',
        'RAG answers',
        'Source references',
        'Fallback behavior'
      ]
    },
    {
      id: 'testing-quality',
      title: 'Testing & Quality',
      items: [
        'Test Flow',
        'Restart test sessions',
        'Runtime Trace',
        'Saved Variables',
        'QA Mode',
        'Evaluation Center',
        'Datasets and evaluation cases',
        'Flow coverage',
        'Release policy'
      ]
    },
    {
      id: 'versions-publishing',
      title: 'Versions & Publishing',
      items: [
        'Create versions',
        'Duplicate versions',
        'Archive and Restore versions',
        'AI Instructions',
        'Publication readiness',
        'Smoke test',
        'Publish an assistant'
      ]
    },
    {
      id: 'deployment',
      title: 'Deployment',
      items: ['Public Chat', 'Web Widget', 'Embed script', 'REST Public API', 'API keys']
    },
    {
      id: 'conversations-analytics',
      title: 'Conversations & Analytics',
      items: [
        'Conversation history',
        'Collected data',
        'Follow-up status',
        'Manager notes',
        'Analytics metrics',
        'RAG / Knowledge usage'
      ]
    },
    {
      id: 'roles-permissions',
      title: 'Roles & Permissions',
      items: [
        'Manager workspace responsibilities',
        'Admin read-only workspace behavior',
        'Restricted admin areas'
      ]
    },
    {
      id: 'troubleshooting',
      title: 'Troubleshooting',
      items: [
        'Invalid flow configuration',
        'Missing Knowledge Base results',
        'CORS/widget issues',
        'Publishing blocked',
        'Evaluation failures'
      ]
    }
  ];

  ngOnInit() {
    this.route.fragment.subscribe(fragment => {
      if (!fragment) {
        this.activeSectionId = '';
        return;
      }
      this.activeSectionId = fragment;
      globalThis.setTimeout(() => this.scrollToSection(fragment));
    });
  }

  navigateToSection(event: MouseEvent, sectionId: string) {
    event.preventDefault();

    if (this.activeSectionId === sectionId) {
      this.scrollToSection(sectionId);
      return;
    }

    this.router.navigate([], {
      relativeTo: this.route,
      fragment: sectionId,
      queryParamsHandling: 'preserve'
    });
  }

  scrollToSection(sectionId: string) {
    if (typeof window === 'undefined') return;
    const target = this.document.getElementById(sectionId);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  }
}
