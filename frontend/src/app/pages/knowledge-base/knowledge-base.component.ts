import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Component, HostListener, Inject, OnDestroy, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService } from '../../services/api';
import { ToastService } from '../../services/toast.service';

@Component({
  selector: 'app-knowledge-base',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './knowledge-base.component.html',
  styleUrls: ['./knowledge-base.component.css']
})
export class KnowledgeBaseComponent implements OnInit, OnDestroy {
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
  documentSearch = signal('');
  chunkSearch = signal('');
  chunkStatusFilter = signal<'all' | 'ready' | 'pending' | 'failed'>('all');
  chunkPage = signal(1);
  settingsExpanded = signal(false);
  playgroundExpanded = signal(false);
  openDocumentMenuId = signal<number | undefined>(undefined);
  expandedChunkIds = signal<number[]>([]);
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
  pendingConfirm = signal<{
    type: 'delete' | 'reprocess_chunks';
    document: any;
    title: string;
    message: string;
    actionLabel: string;
    destructive?: boolean;
  } | null>(null);
  duplicateDocument = signal<{
    filename: string;
  } | null>(null);
  error = signal('');
  message = signal('');
  documentEdit = {
    filename: '',
    content_type: ''
  };

  private isBrowser: boolean;
  private documentStatusPoll?: ReturnType<typeof setInterval>;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    private toast: ToastService,
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

  ngOnDestroy() {
    this.stopDocumentStatusPolling();
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

  updateMinimumScore(value: any) {
    const score = Number(value);
    this.updateRagSetting('min_score', Number.isFinite(score) ? score : 0);
  }

  selectVersion(versionId: number | string) {
    this.selectedVersionId.set(Number(versionId));
    this.selectedDocument.set(null);
    this.chunks.set([]);
    this.chunkPage.set(1);
    this.retrievalChunks.set([]);
    this.loadDocuments();
  }

  loadDocuments(background = false) {
    const versionId = this.selectedVersionId();
    if (!versionId) return;

    if (!background) {
      this.loading.set(true);
    }
    this.error.set('');
    this.api.getDocuments(versionId).subscribe({
      next: documents => {
        this.documents.set(documents);
        this.loading.set(false);
        this.syncSelectedDocument(documents);
        this.updateDocumentStatusPolling();
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

    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');

    reader.onload = () => {
      const result = String(reader.result || '');
      const content = isPdf && result.includes(',') ? result.split(',', 2)[1] : result;
      this.api.uploadDocument(versionId, {
        filename: file.name,
        content_type: file.type || 'text/plain',
        content,
        content_encoding: isPdf ? 'base64' : undefined
      }).subscribe({
        next: (document: any) => {
          input.value = '';
          this.selectedFileName = '';
          this.uploadLoading.set(false);
          this.message.set('Document uploaded. Processing in background.');
          this.toast.success('Document uploaded. Indexing has started.');
          this.documents.update(documents => [document, ...documents.filter(item => item.id !== document.id)]);
          this.updateDocumentStatusPolling();
          this.loadDocuments(true);
        },
        error: err => {
          if (err.status === 409 || String(err.error?.detail || '').toLowerCase().includes('already')) {
            this.duplicateDocument.set({ filename: file.name });
            this.error.set('');
          } else {
            const message = this.safeIngestionMessage(err.error?.detail || 'Upload failed');
            this.error.set(message);
            this.toast.error(message);
          }
          this.uploadLoading.set(false);
        }
      });
    };

    reader.onerror = () => {
      this.error.set('Could not read file');
      this.uploadLoading.set(false);
    };

    if (isPdf) {
      reader.readAsDataURL(file);
    } else {
      reader.readAsText(file);
    }
  }

  private syncSelectedDocument(documents: any[]) {
    const selected = this.selectedDocument();
    if (!selected) {
      if (documents.length && !this.chunksLoading()) {
        this.openDocument(documents[0]);
      }
      return;
    }

    const updated = documents.find(document => document.id === selected.id);
    if (updated) {
      this.selectedDocument.set(updated);
    } else if (documents.length) {
      this.openDocument(documents[0]);
    } else {
      this.selectedDocument.set(null);
      this.chunks.set([]);
    }
  }

  private updateDocumentStatusPolling() {
    if (!this.hasProcessingDocuments()) {
      this.stopDocumentStatusPolling();
      return;
    }

    if (this.documentStatusPoll || !this.isBrowser) return;
    this.documentStatusPoll = setInterval(() => this.loadDocuments(true), 2500);
  }

  private stopDocumentStatusPolling() {
    if (!this.documentStatusPoll) return;
    clearInterval(this.documentStatusPoll);
    this.documentStatusPoll = undefined;
  }

  private hasProcessingDocuments() {
    return this.documents().some(document => this.lifecycleStatus(document) === 'processing');
  }

  openDocument(document: any) {
    this.selectedDocument.set(document);
    this.openDocumentMenuId.set(undefined);
    this.expandedChunkIds.set([]);
    this.chunkPage.set(1);
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
    this.openDocumentMenuId.set(undefined);
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
    this.openDocumentMenuId.set(undefined);
    this.pendingConfirm.set({
      type: 'delete',
      document,
      title: 'Delete document?',
      message: `Are you sure you want to delete "${document.filename}"? This action cannot be undone.`,
      actionLabel: 'Delete document',
      destructive: true
    });
  }

  private deleteDocumentNow(document: any) {

    this.api.deleteDocument(document.id).subscribe({
      next: () => {
        this.pendingConfirm.set(null);
        this.message.set('Document deleted');
        this.toast.success('Document deleted');
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
    if (this.isDocumentActionBusy(document)) return;
    this.reprocessId.set(document.id);
    this.error.set('');
    this.message.set('');

    this.api.reprocessDocumentEmbeddings(document.id).subscribe({
      next: result => {
        this.reprocessId.set(undefined);
        const failed = Number(result.failed_chunks || 0);
        const message = failed
          ? `${failed} chunks still need attention after retry`
          : 'Document indexed successfully';
        this.message.set(failed ? `${result.ready_chunks}/${result.total_chunks} embeddings ready` : message);
        if (failed) {
          this.toast.show(message, 'warning');
        } else {
          this.toast.success(message);
        }
        this.loadDocuments();
        if (this.selectedDocument()?.id === document.id) {
          this.openDocument(document);
        }
      },
      error: err => {
        const message = this.safeIngestionMessage(err.error?.detail || 'Could not retry failed chunks');
        this.error.set(message);
        this.toast.error(message);
        this.reprocessId.set(undefined);
      }
    });
  }

  reprocessChunks(document: any) {
    this.openDocumentMenuId.set(undefined);
    this.pendingConfirm.set({
      type: 'reprocess_chunks',
      document,
      title: 'Reprocess document?',
      message: `A new indexing pass will be created for "${document.filename}". The current searchable version will remain available until the new processing succeeds.`,
      actionLabel: 'Reprocess'
    });
  }

  private reprocessChunksNow(document: any) {
    if (this.isDocumentActionBusy(document)) return;
    this.reprocessChunksId.set(document.id);
    this.error.set('');
    this.message.set('');

    this.api.reprocessDocumentChunks(document.id).subscribe({
      next: result => {
        this.reprocessChunksId.set(undefined);
        this.pendingConfirm.set(null);
        const failed = Number(result.failed_chunks || 0);
        const message = failed
          ? 'Document reprocess completed with remaining embedding failures'
          : 'Document indexed successfully';
        this.message.set(`${result.ready_chunks}/${result.total_chunks} embeddings ready`);
        if (failed) {
          this.toast.show(message, 'warning');
        } else {
          this.toast.success(message);
        }
        this.loadDocuments();
        if (this.selectedDocument()?.id === document.id) {
          this.openDocument(document);
        }
      },
      error: err => {
        const message = this.safeIngestionMessage(err.error?.detail || 'Could not reprocess document');
        this.error.set(message);
        this.toast.error(message);
        this.reprocessChunksId.set(undefined);
      }
    });
  }

  cancelPendingConfirm() {
    const pending = this.pendingConfirm();
    if (!pending) return;
    if (pending.type === 'reprocess_chunks' && this.reprocessChunksId() === pending.document.id) return;
    this.pendingConfirm.set(null);
  }

  confirmPendingAction() {
    const pending = this.pendingConfirm();
    if (!pending) return;
    if (pending.type === 'delete') {
      this.deleteDocumentNow(pending.document);
      return;
    }
    this.reprocessChunksNow(pending.document);
  }

  closeDuplicateModal() {
    this.duplicateDocument.set(null);
  }

  viewExistingDuplicate() {
    const duplicate = this.duplicateDocument();
    if (!duplicate) return;
    const existing = this.documents().find(document => document.filename === duplicate.filename) || this.documents()[0];
    this.duplicateDocument.set(null);
    if (existing) {
      this.openDocument(existing);
    } else {
      this.loadDocuments();
    }
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    this.closeDuplicateModal();
    this.cancelPendingConfirm();
    this.openDocumentMenuId.set(undefined);
  }

  @HostListener('document:click')
  onDocumentClick() {
    this.openDocumentMenuId.set(undefined);
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

  lifecycleStatus(document: any) {
    const status = String(document.status || '').toLowerCase();
    if (status === 'processed') return 'ready';
    if (status === 'embedding_failed') return 'partially_ready';
    if (['uploaded', 'processing', 'partially_ready', 'ready', 'failed'].includes(status)) return status;
    if (document.error_message || status.includes('failed')) return 'failed';
    return status || 'uploaded';
  }

  filteredDocuments() {
    const query = this.documentSearch().trim().toLowerCase();
    if (!query) return this.documents();
    return this.documents().filter(document => String(document.filename || '').toLowerCase().includes(query));
  }

  toggleDocumentMenu(document: any, event: Event) {
    event.stopPropagation();
    this.openDocumentMenuId.set(this.openDocumentMenuId() === document.id ? undefined : document.id);
  }

  menuIsOpen(document: any) {
    return this.openDocumentMenuId() === document.id;
  }

  viewDocument(document: any) {
    this.openDocument(document);
  }

  statusLabel(document: any) {
    const labels: Record<string, string> = {
      uploaded: 'Uploaded',
      processing: 'Processing',
      partially_ready: 'Partially Ready',
      ready: 'Ready',
      failed: 'Failed'
    };
    return labels[this.lifecycleStatus(document)] || 'Uploaded';
  }

  chunkStatusLabel(chunk: any) {
    const labels: Record<string, string> = {
      pending: 'Pending',
      processing: 'Processing',
      ready: 'Ready',
      failed: 'Failed'
    };
    return labels[String(chunk.embedding_status || '').toLowerCase()] || 'Pending';
  }

  statusTone(document: any) {
    return this.lifecycleStatus(document).replace('_', '-');
  }

  documentCounts(document: any) {
    const total = Number(document.chunks_count || 0);
    const ready = Number(document.embeddings_count || 0);
    const failed = Number(document.failed_embeddings_count || 0);
    const pending = Number(document.pending_embeddings_count || 0);
    return { total, ready, failed, pending };
  }

  aggregateCounts() {
    return this.documents().reduce(
      (totals, document) => {
        const counts = this.documentCounts(document);
        totals.total += counts.total;
        totals.ready += counts.ready;
        totals.failed += counts.failed;
        totals.pending += counts.pending;
        return totals;
      },
      { total: 0, ready: 0, failed: 0, pending: 0 }
    );
  }

  coveragePercent() {
    const counts = this.aggregateCounts();
    if (!counts.total) return 0;
    return Math.round((counts.ready / counts.total) * 100);
  }

  indexHealth() {
    const documents = this.documents();
    const counts = this.aggregateCounts();
    if (!documents.length) return { label: 'Empty', detail: 'No searchable knowledge yet', tone: 'empty' };
    if (counts.failed && counts.ready) return { label: 'Partial', detail: `${counts.ready}/${counts.total} chunks searchable`, tone: 'partial' };
    if (counts.failed && !counts.ready) return { label: 'Attention Required', detail: 'No searchable chunks', tone: 'failed' };
    if (counts.pending || documents.some(document => this.isProcessing(document))) return { label: 'Indexing', detail: `${counts.ready}/${counts.total} chunks embedded`, tone: 'processing' };
    return { label: 'Healthy', detail: `${counts.ready}/${counts.total} chunks searchable`, tone: 'ready' };
  }

  ragReadiness() {
    const health = this.indexHealth();
    if (health.tone === 'ready') return { label: 'RAG Ready', detail: 'Searchable knowledge is available' };
    if (health.tone === 'partial' || health.tone === 'failed') return { label: 'Needs attention', detail: health.detail };
    if (health.tone === 'processing') return { label: 'Indexing', detail: health.detail };
    return { label: 'Not configured', detail: 'Upload documents to enable retrieval' };
  }

  selectedDocumentCounts() {
    const document = this.selectedDocument();
    return document ? this.documentCounts(document) : { total: 0, ready: 0, failed: 0, pending: 0 };
  }

  selectedDocumentHealth() {
    const document = this.selectedDocument();
    if (!document) return '';
    const counts = this.documentCounts(document);
    if (!counts.total) return 'No chunks yet';
    if (counts.failed && counts.ready) return `${counts.ready}/${counts.total} chunks searchable`;
    if (counts.failed) return 'No searchable chunks';
    if (counts.pending) return `Embedding ${counts.ready}/${counts.total} chunks`;
    return `${counts.ready}/${counts.total} chunks searchable`;
  }

  progressPercent(document: any) {
    const counts = this.documentCounts(document);
    if (!counts.total) return 0;
    return Math.round((counts.ready / counts.total) * 100);
  }

  hasFailedChunks(document: any) {
    return this.documentCounts(document).failed > 0;
  }

  isPartial(document: any) {
    return this.lifecycleStatus(document) === 'partially_ready';
  }

  isProcessing(document: any) {
    return this.lifecycleStatus(document) === 'processing' || this.lifecycleStatus(document) === 'uploaded';
  }

  isDocumentActionBusy(document: any) {
    return this.reprocessId() === document.id || this.reprocessChunksId() === document.id || this.isProcessing(document);
  }

  pipelineSteps(document: any) {
    const status = this.lifecycleStatus(document);
    const steps = ['Uploaded', 'Chunking', 'Embedding'];
    steps.push(status === 'partially_ready' ? 'Partially Ready' : status === 'failed' ? 'Failed' : 'Ready');
    return steps;
  }

  pipelineStepClass(document: any, step: string) {
    const status = this.lifecycleStatus(document);
    if (this.activePipelineStep(document, step)) return 'active';
    if (status === 'ready') return 'done';
    if (status === 'partially_ready' && ['Uploaded', 'Chunking'].includes(step)) return 'done';
    if (status === 'processing' && step === 'Uploaded') return 'done';
    if (status === 'failed' && ['Uploaded', 'Chunking'].includes(step)) return 'done';
    return '';
  }

  activePipelineStep(document: any, step: string) {
    const status = this.lifecycleStatus(document);
    if (status === 'uploaded') return step === 'Uploaded';
    if (status === 'processing') return step === 'Chunking' || step === 'Embedding';
    if (status === 'partially_ready') return step === 'Partially Ready';
    if (status === 'failed') return step === 'Failed';
    return step === 'Ready';
  }

  safeIngestionMessage(detail: string) {
    const value = String(detail || '').toLowerCase();
    if (value.includes('429') || value.includes('rate limit') || value.includes('quota')) {
      return 'Rate limit reached. Please retry in a moment.';
    }
    if (value.includes('timeout') || value.includes('temporar') || value.includes('503') || value.includes('502') || value.includes('504')) {
      return 'Temporary AI service issue. Please retry.';
    }
    if (value.includes('embedding')) {
      return 'Embedding generation failed. Please retry failed chunks.';
    }
    if (value.includes('document') || value.includes('extract') || value.includes('readable')) {
      return 'Document processing failed. Please check the file and try again.';
    }
    return 'Knowledge Base operation failed. Please try again.';
  }

  embeddingSummary(document: any) {
    const selected = this.selectedDocument();
    const chunks = selected?.id === document.id ? this.chunks() : [];
    if (!chunks.length) {
      const ready = Number(document.embeddings_count || 0);
      const failed = Number(document.failed_embeddings_count || 0);
      const pending = Number(document.pending_embeddings_count || 0);
      const total = Number(document.chunks_count || 0);
      if (!total) return 'No chunks yet';
      if (failed) return `${failed} failed, ${ready} ready`;
      if (pending) return `${ready}/${total} ready, ${pending} pending`;
      return `${ready}/${total} embeddings ready`;
    }
    const ready = chunks.filter(chunk => chunk.embedding_status === 'ready').length;
    const failed = chunks.filter(chunk => chunk.embedding_status === 'failed').length;
    if (failed) return `${failed} failed, ${ready} ready`;
    return `${ready}/${chunks.length} embeddings ready`;
  }

  embeddingModel(document: any) {
    const selected = this.selectedDocument();
    const chunks = selected?.id === document.id ? this.chunks() : [];
    return chunks.find(chunk => chunk.embedding_model)?.embedding_model || 'Open document to view model';
  }

  versionLabel() {
    const selectedId = this.selectedVersionId();
    const version = this.versions().find(item => Number(item.id) === Number(selectedId));
    if (!version) return 'No version selected';
    return `v${version.version_number} ${version.status || ''}${version.is_active ? ' Active' : ''}`.trim();
  }

  retrievalConfigSummary() {
    const settings = this.ragSettings();
    const modeLabels: Record<string, string> = {
      auto: 'Semantic + keyword fallback',
      semantic: 'Semantic only',
      keyword: 'Keyword only'
    };
    return `${modeLabels[settings.retrieval_mode] || 'Auto'} · Top ${settings.max_chunks} · Min ${Number(settings.min_score || 0).toFixed(2)}`;
  }

  toggleSettings() {
    this.settingsExpanded.update(value => !value);
  }

  togglePlayground() {
    this.playgroundExpanded.update(value => !value);
  }

  filteredChunks() {
    const query = this.chunkSearch().trim().toLowerCase();
    const status = this.chunkStatusFilter();
    return this.chunks().filter(chunk => {
      const matchesStatus = status === 'all' || String(chunk.embedding_status || 'pending').toLowerCase() === status;
      const matchesSearch = !query
        || String(chunk.title || '').toLowerCase().includes(query)
        || String(chunk.text || '').toLowerCase().includes(query)
        || String(chunk.section_type || '').toLowerCase().includes(query);
      return matchesStatus && matchesSearch;
    });
  }

  setChunkSearch(value: string) {
    this.chunkSearch.set(value);
    this.chunkPage.set(1);
  }

  setChunkStatusFilter(value: 'all' | 'ready' | 'pending' | 'failed') {
    this.chunkStatusFilter.set(value);
    this.chunkPage.set(1);
  }

  readonly chunkPageSize = 12;

  pagedChunks() {
    const start = (this.chunkPage() - 1) * this.chunkPageSize;
    return this.filteredChunks().slice(start, start + this.chunkPageSize);
  }

  chunkPageCount() {
    return Math.max(1, Math.ceil(this.filteredChunks().length / this.chunkPageSize));
  }

  chunkRangeStart() {
    if (!this.filteredChunks().length) return 0;
    return (this.chunkPage() - 1) * this.chunkPageSize + 1;
  }

  chunkRangeEnd() {
    return Math.min(this.filteredChunks().length, this.chunkPage() * this.chunkPageSize);
  }

  goToChunkPage(page: number) {
    this.chunkPage.set(Math.max(1, Math.min(page, this.chunkPageCount())));
  }

  toggleChunk(chunk: any) {
    const id = Number(chunk.id ?? chunk.order);
    this.expandedChunkIds.update(ids => ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id]);
  }

  chunkExpanded(chunk: any) {
    const id = Number(chunk.id ?? chunk.order);
    return this.expandedChunkIds().includes(id);
  }

  chunkLength(chunk: any) {
    return String(chunk.text || '').length;
  }

  chunkPreview(chunk: any) {
    const text = String(chunk.text || '').replace(/\s+/g, ' ').trim();
    if (!text) return 'No text preview available for this chunk.';
    return text.length > 220 ? `${text.slice(0, 220).trim()}...` : text;
  }

  chunkOrdinal(chunk: any) {
    return Number(chunk.order ?? 0) + 1;
  }

  retrievalResultSummary() {
    const count = this.retrievalChunks().length;
    if (!count) return '';
    return `Retrieved ${count} ${count === 1 ? 'chunk' : 'chunks'}`;
  }

  totalChunks() {
    return this.documents().reduce((total, document) => total + Number(document.chunks_count || 0), 0);
  }

  totalEmbeddings() {
    return this.documents().reduce((total, document) => total + Number(document.embeddings_count || 0), 0);
  }

  processingStatus() {
    const documents = this.documents();
    if (!documents.length) return 'No documents';
    if (documents.some(document => ['failed', 'partially_ready'].includes(this.lifecycleStatus(document)))) return 'Needs attention';
    if (documents.some(document => this.isProcessing(document))) return 'Processing';
    return 'Ready';
  }

  goBack() {
    const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
    if (returnUrl && returnUrl.startsWith('/dashboard/')) {
      this.router.navigateByUrl(returnUrl);
      return;
    }

    this.router.navigate(['/dashboard/projects', this.projectId, 'chatbots']);
  }
}
