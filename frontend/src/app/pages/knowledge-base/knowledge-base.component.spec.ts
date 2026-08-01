import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PLATFORM_ID } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of, Subject } from 'rxjs';
import { describe, expect, it, beforeEach, vi } from 'vitest';

import { KnowledgeBaseComponent } from './knowledge-base.component';
import { ApiService } from '../../services/api';
import { ToastService } from '../../services/toast.service';

describe('KnowledgeBaseComponent', () => {
  let component: KnowledgeBaseComponent;
  let fixture: ComponentFixture<KnowledgeBaseComponent>;
  let api: any;
  let toast: ToastService;

  const readyDocument = {
    id: 1,
    filename: 'ready.txt',
    status: 'ready',
    chunks_count: 4,
    embeddings_count: 4,
    failed_embeddings_count: 0,
    pending_embeddings_count: 0,
    processed_at: '2026-07-29T10:00:00Z'
  };

  const partialDocument = {
    id: 2,
    filename: 'partial.txt',
    status: 'partially_ready',
    chunks_count: 19,
    embeddings_count: 17,
    failed_embeddings_count: 2,
    pending_embeddings_count: 0,
    processed_at: '2026-07-29T10:00:00Z'
  };

  beforeEach(async () => {
    api = {
      getChatbot: vi.fn().mockReturnValue(of({ versions: [] })),
      getDocuments: vi.fn().mockReturnValue(of([])),
      getDocumentChunks: vi.fn().mockReturnValue(of([])),
      reprocessDocumentEmbeddings: vi.fn().mockReturnValue(of({ total_chunks: 1, ready_chunks: 1, failed_chunks: 0 })),
      reprocessDocumentChunks: vi.fn().mockReturnValue(of({ total_chunks: 1, ready_chunks: 1, failed_chunks: 0 })),
      deleteDocument: vi.fn().mockReturnValue(of({})),
      updateDocument: vi.fn().mockReturnValue(of({})),
      updateChatbotRagSettings: vi.fn().mockReturnValue(of({})),
      testRagRetrieval: vi.fn().mockReturnValue(of({ chunks: [] }))
    };

    await TestBed.configureTestingModule({
      imports: [KnowledgeBaseComponent],
      providers: [
        provideRouter([]),
        ToastService,
        { provide: ApiService, useValue: api },
        { provide: PLATFORM_ID, useValue: 'server' },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ projectId: '1', chatbotId: '2' }),
              queryParamMap: convertToParamMap({})
            }
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(KnowledgeBaseComponent);
    component = fixture.componentInstance;
    toast = TestBed.inject(ToastService);
    component.projectId = 1;
    component.chatbotId = 2;
    await fixture.whenStable();
  });

  it('renders a ready document with friendly status and progress counts', () => {
    component.documents.set([readyDocument]);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('ready.txt');
    expect(text).toContain('Ready');
    expect(text).toContain('4 chunks');
    expect(text).toContain('4/4 embedded');
    expect(text).toContain('RAG Ready');
  });

  it('renders partially ready documents with warning and retry action', () => {
    component.documents.set([partialDocument]);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Partially Ready');
    expect(text).toContain('2 chunks could not be indexed');
    expect(text).toContain('Retry failed chunks');
  });

  it('retries failed chunks through the existing embeddings endpoint', () => {
    const response = new Subject<any>();
    api.reprocessDocumentEmbeddings.mockReturnValue(response.asObservable());
    component.documents.set([partialDocument]);

    component.reprocessEmbeddings(partialDocument);

    expect(api.reprocessDocumentEmbeddings).toHaveBeenCalledWith(2);
    expect(component.reprocessId()).toBe(2);

    response.next({ total_chunks: 19, ready_chunks: 19, failed_chunks: 0 });
    response.complete();

    expect(component.reprocessId()).toBeUndefined();
  });

  it('shows duplicate document modal without technical hash details', () => {
    component.duplicateDocument.set({ filename: 'presentation.txt' });
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Document already indexed');
    expect(text).toContain('An identical copy of this document already exists');
    expect(text).not.toContain('SHA');
  });

  it('opens a reprocess confirmation before calling the endpoint', () => {
    component.reprocessChunks(partialDocument);
    fixture.detectChanges();

    expect(api.reprocessDocumentChunks).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Reprocess document?');

    component.confirmPendingAction();

    expect(api.reprocessDocumentChunks).toHaveBeenCalledWith(2);
  });

  it('prevents repeated reprocess requests while one is already running', () => {
    const response = new Subject<any>();
    api.reprocessDocumentChunks.mockReturnValue(response.asObservable());

    component.reprocessChunks(partialDocument);
    component.confirmPendingAction();
    component.confirmPendingAction();

    expect(api.reprocessDocumentChunks).toHaveBeenCalledTimes(1);
  });

  it('disables retry/reprocess actions while document is processing', () => {
    const processingDocument = {
      ...partialDocument,
      status: 'processing',
      pending_embeddings_count: 2
    };
    component.documents.set([processingDocument]);
    fixture.detectChanges();

    component.openDocumentMenuId.set(processingDocument.id);
    fixture.detectChanges();

    const disabledButtons = Array.from(fixture.nativeElement.querySelectorAll('button:disabled'))
      .map((button: any) => button.textContent.trim());
    expect(disabledButtons).toContain('Retry failed chunks');
    expect(disabledButtons).toContain('Reprocess');
  });

  it('shows success toast when failed chunks recover', () => {
    const toastSpy = vi.spyOn(toast, 'success');
    api.reprocessDocumentEmbeddings.mockReturnValue(of({ total_chunks: 19, ready_chunks: 19, failed_chunks: 0 }));

    component.reprocessEmbeddings(partialDocument);

    expect(toastSpy).toHaveBeenCalledWith('Document indexed successfully');
  });

  it('opens the compact document action menu', () => {
    component.documents.set([readyDocument]);
    fixture.detectChanges();

    const menuButton = fixture.nativeElement.querySelector('.icon-button');
    menuButton.click();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('View details');
    expect(text).toContain('Rename');
    expect(text).toContain('Reprocess');
    expect(text).toContain('Delete');
  });

  it('toggles retrieval configuration', () => {
    component.documents.set([readyDocument]);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Minimum score');
    component.toggleSettings();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Minimum score');
    expect(fixture.nativeElement.textContent).toContain('Answer only from documents');
  });

  it('toggles retrieval playground', () => {
    component.documents.set([readyDocument]);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('Ask a question to test retrieval');
    component.togglePlayground();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.playground-body input')?.getAttribute('placeholder'))
      .toBe('Ask a question to test retrieval');
  });

  it('filters and expands chunks in the chunk explorer', () => {
    component.selectedDocument.set(readyDocument);
    component.documents.set([readyDocument]);
    component.chunks.set([
      { id: 1, order: 0, title: 'Admissions', text: 'Enrollment requirements', embedding_status: 'ready' },
      { id: 2, order: 1, title: 'Finance', text: 'Tuition details', embedding_status: 'ready' }
    ]);
    component.chunkSearch.set('enrollment');
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Admissions');
    expect(fixture.nativeElement.textContent).not.toContain('Finance');

    component.toggleChunk({ id: 1, order: 0 });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Enrollment requirements');
  });
});
