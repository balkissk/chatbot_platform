import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, Inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';

@Component({
  selector: 'app-knowledge-base',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './knowledge-base.component.html',
  styleUrls: ['./knowledge-base.component.css']
})
export class KnowledgeBaseComponent implements OnInit {
  projectId!: number;
  chatbotId!: number;

  chatbot = signal<any | null>(null);
  versions = signal<any[]>([]);
  selectedVersionId = signal<number | undefined>(undefined);
  documents = signal<any[]>([]);
  selectedDocument = signal<any | null>(null);
  chunks = signal<any[]>([]);
  retrievalChunks = signal<any[]>([]);
  retrievalMode = signal('');
  ragSettings = signal<any>({
    retrieval_mode: 'auto',
    max_chunks: 3,
    min_score: 0.2,
    show_sources: true,
    strict_context: true,
    response_length: 'short'
  });

  selectedFileName = '';
  question = '';
  loading = signal(false);
  uploadLoading = signal(false);
  chunksLoading = signal(false);
  testLoading = signal(false);
  settingsLoading = signal(false);
  reprocessId = signal<number | undefined>(undefined);
  reprocessChunksId = signal<number | undefined>(undefined);
  editingDocumentId = signal<number | undefined>(undefined);
  savingDocumentId = signal<number | undefined>(undefined);
  error = signal('');
  message = signal('');
  documentEdit = {
    filename: '',
    content_type: ''
  };

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
    this.projectId = Number(this.route.snapshot.paramMap.get('projectId'));
    this.chatbotId = Number(this.route.snapshot.paramMap.get('chatbotId'));
    if (!this.isBrowser) return;
    this.loadChatbot();
  }

  loadChatbot() {
    this.loading.set(true);
    this.error.set('');
    this.api.getChatbot(this.chatbotId).subscribe({
      next: chatbot => {
        const versions = [...(chatbot.versions || [])].sort((a, b) => b.version_number - a.version_number);
        const preferred = versions.find(version => version.status === 'draft')
          || versions.find(version => version.is_active)
          || versions[0];
        this.chatbot.set(chatbot);
        this.ragSettings.set(chatbot.rag_settings || this.ragSettings());
        this.versions.set(versions);
        this.selectedVersionId.set(preferred?.id);
        this.loading.set(false);
        if (preferred?.id) this.loadDocuments();
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chatbot');
        this.loading.set(false);
      }
    });
  }

  saveRagSettings() {
    const settings = this.ragSettings();
    this.settingsLoading.set(true);
    this.error.set('');
    this.message.set('');

    this.api.updateChatbotRagSettings(this.chatbotId, {
      retrieval_mode: settings.retrieval_mode,
      max_chunks: Number(settings.max_chunks),
      min_score: Number(settings.min_score),
      show_sources: Boolean(settings.show_sources),
      strict_context: Boolean(settings.strict_context),
      response_length: settings.response_length
    }).subscribe({
      next: saved => {
        this.ragSettings.set(saved);
        this.settingsLoading.set(false);
        this.message.set('RAG settings saved');
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not save RAG settings');
        this.settingsLoading.set(false);
      }
    });
  }

  updateRagSetting(key: string, value: any) {
    this.ragSettings.update(settings => ({
      ...settings,
      [key]: value
    }));
  }

  selectVersion(versionId: number | string) {
    this.selectedVersionId.set(Number(versionId));
    this.selectedDocument.set(null);
    this.chunks.set([]);
    this.retrievalChunks.set([]);
    this.loadDocuments();
  }

  loadDocuments() {
    const versionId = this.selectedVersionId();
    if (!versionId) return;

    this.loading.set(true);
    this.error.set('');
    this.api.getDocuments(versionId).subscribe({
      next: documents => {
        this.documents.set(documents);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load documents');
        this.loading.set(false);
      }
    });
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    const versionId = this.selectedVersionId();

    this.error.set('');
    this.message.set('');
    this.selectedFileName = file?.name || '';

    if (!file || !versionId) return;

    this.uploadLoading.set(true);
    const reader = new FileReader();

    reader.onload = () => {
      this.api.uploadDocument(versionId, {
        filename: file.name,
        content_type: file.type || 'text/plain',
        content: String(reader.result || '')
      }).subscribe({
        next: () => {
          input.value = '';
          this.selectedFileName = '';
          this.uploadLoading.set(false);
          this.message.set('Document uploaded and chunked');
          this.loadDocuments();
        },
        error: err => {
          this.error.set(err.error?.detail || 'Upload failed');
          this.uploadLoading.set(false);
        }
      });
    };

    reader.onerror = () => {
      this.error.set('Could not read file');
      this.uploadLoading.set(false);
    };

    reader.readAsText(file);
  }

  openDocument(document: any) {
    this.selectedDocument.set(document);
    this.chunksLoading.set(true);
    this.error.set('');
    this.api.getDocumentChunks(document.id).subscribe({
      next: chunks => {
        this.chunks.set(chunks);
        this.chunksLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not load chunks');
        this.chunksLoading.set(false);
      }
    });
  }

  startDocumentEdit(document: any) {
    this.editingDocumentId.set(document.id);
    this.documentEdit = {
      filename: document.filename || '',
      content_type: document.content_type || ''
    };
    this.error.set('');
    this.message.set('');
  }

  cancelDocumentEdit() {
    this.editingDocumentId.set(undefined);
  }

  saveDocument(document: any) {
    const filename = this.documentEdit.filename.trim();
    if (!filename) {
      this.error.set('Document filename is required');
      return;
    }

    this.savingDocumentId.set(document.id);
    this.error.set('');
    this.message.set('');
    this.api.updateDocument(document.id, {
      filename,
      content_type: this.documentEdit.content_type.trim() || document.content_type
    }).subscribe({
      next: updated => {
        this.documents.update(documents => documents.map(item => item.id === updated.id ? updated : item));
        if (this.selectedDocument()?.id === updated.id) {
          this.selectedDocument.set(updated);
        }
        this.savingDocumentId.set(undefined);
        this.editingDocumentId.set(undefined);
        this.message.set('Document updated');
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not update document');
        this.savingDocumentId.set(undefined);
      }
    });
  }

  deleteDocument(document: any) {
    if (!confirm(`Delete document "${document.filename}"?`)) return;

    this.api.deleteDocument(document.id).subscribe({
      next: () => {
        this.message.set('Document deleted');
        this.documents.update(documents => documents.filter(item => item.id !== document.id));
        if (this.selectedDocument()?.id === document.id) {
          this.selectedDocument.set(null);
          this.chunks.set([]);
        }
      },
      error: err => this.error.set(err.error?.detail || 'Could not delete document')
    });
  }

  reprocessEmbeddings(document: any) {
    this.reprocessId.set(document.id);
    this.error.set('');
    this.message.set('');

    this.api.reprocessDocumentEmbeddings(document.id).subscribe({
      next: result => {
        this.reprocessId.set(undefined);
        this.message.set(`Embeddings reprocessed: ${result.ready_chunks}/${result.total_chunks} ready`);
        this.loadDocuments();
        if (this.selectedDocument()?.id === document.id) {
          this.openDocument(document);
        }
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not reprocess embeddings');
        this.reprocessId.set(undefined);
      }
    });
  }

  reprocessChunks(document: any) {
    if (!confirm(`Rebuild chunks for "${document.filename}"? This will replace old chunks and embeddings.`)) return;

    this.reprocessChunksId.set(document.id);
    this.error.set('');
    this.message.set('');

    this.api.reprocessDocumentChunks(document.id).subscribe({
      next: result => {
        this.reprocessChunksId.set(undefined);
        this.message.set(`Chunks rebuilt: ${result.total_chunks} chunks, ${result.ready_chunks} embeddings ready`);
        this.loadDocuments();
        if (this.selectedDocument()?.id === document.id) {
          this.openDocument(document);
        }
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not reprocess chunks');
        this.reprocessChunksId.set(undefined);
      }
    });
  }

  testRetrieval() {
    const versionId = this.selectedVersionId();
    const question = this.question.trim();
    if (!versionId || !question) return;

    this.testLoading.set(true);
    this.error.set('');
    this.retrievalChunks.set([]);
    this.retrievalMode.set('');
    this.api.testRagRetrieval(versionId, { question, limit: this.ragSettings().max_chunks }).subscribe({
      next: result => {
        this.retrievalChunks.set(result.chunks || []);
        this.retrievalMode.set(result.retrieval_mode || '');
        this.testLoading.set(false);
      },
      error: err => {
        this.error.set(err.error?.detail || 'Could not test retrieval');
        this.testLoading.set(false);
      }
    });
  }

  goBack() {
    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
