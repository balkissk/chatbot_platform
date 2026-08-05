import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom, Observable, of, shareReplay, tap } from 'rxjs';
import { apiBaseUrl } from '../config/app-config';

@Injectable({
  providedIn: 'root'
})
export class ApiService {

  baseUrl = apiBaseUrl();
  private projectsCache = new Map<string, Observable<any[]>>();
  private projectCache = new Map<number, Observable<any>>();
  private projectChatbotsCache = new Map<number, Observable<any[]>>();
  private projectChatbotsValueCache = new Map<number, any[]>();
  private cacheToken = '';

  constructor(private http: HttpClient) {}

  getProjects(search = '', force = false, limit = 50, offset = 0, status = '') {
    this.ensureCacheScope();
    const params: any = {};
    if (search.trim()) params.search = search.trim();
    if (status.trim()) params.status = status.trim();
    params.limit = limit;
    params.offset = offset;
    const key = `${this.cacheToken}|${search.trim()}|${limit}|${offset}|${status.trim()}`;
    if (force || !this.projectsCache.has(key)) {
      this.projectsCache.set(
        key,
        this.http.get<any[]>(`${this.baseUrl}/projects`, { params }).pipe(
          tap(projects => projects.forEach(project => {
            this.projectCache.set(project.id, of(project).pipe(shareReplay(1)));
          })),
          shareReplay(1)
        )
      );
    }
    return this.projectsCache.get(key)!;
  }

  getProjectsPage(options: any = {}) {
    this.ensureCacheScope();
    const params: any = {
      page: options.page || 1,
      page_size: options.page_size || 50,
      sort: options.sort || 'recent_activity'
    };
    if (options.search?.trim()) params.search = options.search.trim();
    if (options.status?.trim()) params.status = options.status.trim();
    if (options.assistant_range?.trim()) params.assistant_range = options.assistant_range.trim();
    if (options.created_from) params.created_from = options.created_from;
    if (options.created_to) params.created_to = options.created_to;
    if (options.last_activity_from) params.last_activity_from = options.last_activity_from;
    if (options.last_activity_to) params.last_activity_to = options.last_activity_to;
    return this.http.get<any>(`${this.baseUrl}/projects/query`, { params }).pipe(
      tap(response => (response?.items || []).forEach((project: any) => {
        this.projectCache.set(project.id, of(project).pipe(shareReplay(1)));
      }))
    );
  }

  getProjectsSummary() {
    this.ensureCacheScope();
    return this.http.get<any>(`${this.baseUrl}/projects/summary`);
  }

  getProject(projectId: number, force = false) {
    this.ensureCacheScope();
    if (force || !this.projectCache.has(projectId)) {
      this.projectCache.set(
        projectId,
        this.http.get<any>(`${this.baseUrl}/projects/${projectId}`).pipe(shareReplay(1))
      );
    }
    return this.projectCache.get(projectId)!;
  }

  getProjectWorkspaceDashboard(projectId: number) {
    this.ensureCacheScope();
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/workspace-dashboard`);
  }

  getProjectAnalytics(projectId: number) {
    this.ensureCacheScope();
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/analytics`);
  }

  createProject(data: any) {
    this.ensureCacheScope();
    return this.http.post(`${this.baseUrl}/projects`, data).pipe(
      tap(() => this.clearProjectCaches())
    );
  }

  updateProject(projectId: number, data: any) {
    this.ensureCacheScope();
    return this.http.put(`${this.baseUrl}/projects/${projectId}`, data).pipe(
      tap((project: any) => {
        this.clearProjectCaches(projectId);
        this.projectCache.set(projectId, of(project).pipe(shareReplay(1)));
      })
    );
  }

  duplicateProject(projectId: number) {
    this.ensureCacheScope();
    return this.http.post(`${this.baseUrl}/projects/${projectId}/duplicate`, {}).pipe(
      tap(() => this.clearProjectCaches())
    );
  }

  archiveProject(projectId: number) {
    this.ensureCacheScope();
    return this.http.put(`${this.baseUrl}/projects/${projectId}/archive`, {}).pipe(
      tap(() => this.clearProjectCaches(projectId))
    );
  }

  restoreProject(projectId: number) {
    this.ensureCacheScope();
    return this.http.put(`${this.baseUrl}/projects/${projectId}/restore`, {}).pipe(
      tap(() => this.clearProjectCaches(projectId))
    );
  }

  deleteProject(projectId: number) {
    this.ensureCacheScope();
    return this.http.delete(`${this.baseUrl}/projects/${projectId}`).pipe(
      tap(() => this.clearProjectCaches(projectId))
    );
  }

  // ===== CHATBOTS =====

  getChatbotsByProject(projectId: number, force = false) {
    this.ensureCacheScope();
    if (force || !this.projectChatbotsCache.has(projectId)) {
      this.projectChatbotsCache.set(
        projectId,
        this.http.get<any[]>(`${this.baseUrl}/projects/${projectId}/chatbots`).pipe(
          tap(chatbots => this.projectChatbotsValueCache.set(projectId, chatbots)),
          shareReplay(1)
        )
      );
    }
    return this.projectChatbotsCache.get(projectId)!;
  }

  getCachedChatbotsByProject(projectId: number) {
    this.ensureCacheScope();
    return this.projectChatbotsValueCache.get(projectId);
  }

  createChatbot(data: any) {
    return this.http.post(
      `${this.baseUrl}/chatbots`,
      data
    ).pipe(tap(() => this.clearChatbotCaches(data.project_id)));
  }

  getChatbot(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}`);
  }

  getChatbotSetup(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/setup`);
  }

  getChatbotAnalytics(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/analytics`);
  }

  getChatbotOperationsDashboard(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/operations-dashboard`);
  }

  getChatbotConversations(chatbotId: number, filters: any = {}) {
    const params: any = {};
    if (filters.search?.trim()) params.search = filters.search.trim();
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.channel) params.channel = filters.channel;
    if (filters.feedback) params.feedback = filters.feedback;
    if (filters.response_type) params.response_type = filters.response_type;
    if (filters.limit) params.limit = filters.limit;
    if (filters.offset) params.offset = filters.offset;
    return this.http.get<any[]>(`${this.baseUrl}/chatbots/${chatbotId}/conversations`, { params });
  }

  getChatbotConversation(chatbotId: number, sessionId: number, messageLimit = 200) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/conversations/${sessionId}`, {
      params: { message_limit: messageLimit }
    });
  }

  getChatbotUnansweredQuestions(chatbotId: number) {
    return this.http.get<any[]>(`${this.baseUrl}/chatbots/${chatbotId}/conversations/unanswered`);
  }

  getChatbotCollectedData(chatbotId: number, filters: any = {}) {
    const params: any = {};
    if (filters.search?.trim()) params.search = filters.search.trim();
    if (filters.field_type) params.field_type = filters.field_type;
    if (filters.limit) params.limit = filters.limit;
    if (filters.offset) params.offset = filters.offset;
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/collected-data`, { params });
  }

  updateConversationFollowUp(chatbotId: number, sessionId: number, data: any) {
    return this.http.patch<any>(`${this.baseUrl}/chatbots/${chatbotId}/conversations/${sessionId}/follow-up`, data);
  }

  updateChatbot(chatbotId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}`, data).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }

  updateChatbotSetup(chatbotId: number, data: any) {
    return this.http.patch<any>(`${this.baseUrl}/chatbots/${chatbotId}/setup`, data).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }

  reapplyAssistantTemplateDraft(chatbotId: number) {
    return this.http.post<any>(`${this.baseUrl}/chatbots/${chatbotId}/setup/template-draft`, {}).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }

  regenerateAssistantAiDraft(chatbotId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/chatbots/${chatbotId}/setup/ai-draft`, data).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }

  updateChatbotStatus(chatbotId: number, isActive: boolean) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/status`, {
      is_active: isActive
    }).pipe(tap(() => this.clearChatbotCaches()));
  }

  regenerateChatbotApiKey(chatbotId: number) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/api-key/regenerate`, {});
  }

  getChatbotChannels(chatbotId: number) {
    return this.http.get<any[]>(`${this.baseUrl}/chatbots/${chatbotId}/channels`);
  }

  createChatbotChannel(chatbotId: number, channelType: string, data: any) {
    return this.http.post<any>(`${this.baseUrl}/chatbots/${chatbotId}/channels/${channelType}`, data);
  }

  updateChatbotChannel(chatbotId: number, channelType: string, data: any) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/channels/${channelType}`, data);
  }

  deleteChatbotChannel(chatbotId: number, channelType: string) {
    return this.http.delete<any>(`${this.baseUrl}/chatbots/${chatbotId}/channels/${channelType}`);
  }

  testChatbotChannel(chatbotId: number, channelType: string) {
    return this.http.post<any>(`${this.baseUrl}/chatbots/${chatbotId}/channels/${channelType}/test`, {});
  }

  clearChatbotChannelError(chatbotId: number, channelType: string) {
    return this.http.patch<any>(`${this.baseUrl}/chatbots/${chatbotId}/channels/${channelType}/clear-error`, {});
  }

  getChatbotRagSettings(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/rag-settings`);
  }

  updateChatbotRagSettings(chatbotId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/chatbots/${chatbotId}/rag-settings`, data);
  }

  deleteChatbot(chatbotId: number) {
    return this.http.delete(`${this.baseUrl}/chatbots/${chatbotId}`).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }
  // ===== VERSIONS =====

  getVersionsByChatbot(chatbotId: number) {
    return this.http.get<any[]>(
      `${this.baseUrl}/chatbots/${chatbotId}/versions`
    );
  }

  createVersion(data: any) {
    return this.http.post(
      `${this.baseUrl}/versions`,
      data
    );
  }
  publishVersion(versionId: number, confirmWarnings = false) {
    return this.http.put(
      `${this.baseUrl}/versions/${versionId}/publish`,
      {},
      { params: confirmWarnings ? { confirm_warnings: 'true' } : {} }
    );
  }

  getVersionReadiness(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/versions/${versionId}/readiness`);
  }

  runVersionSmokeTest(versionId: number) {
    return this.http.post<any>(`${this.baseUrl}/versions/${versionId}/smoke-test`, {});
  }

  getEvaluationDatasets(chatbotId: number, includeArchived = false) {
    return this.http.get<any[]>(`${this.baseUrl}/evaluations/assistants/${chatbotId}/datasets`, {
      params: includeArchived ? { include_archived: 'true' } : {}
    });
  }

  getEvaluationDataset(datasetId: number) {
    return this.http.get<any>(`${this.baseUrl}/evaluations/datasets/${datasetId}`);
  }

  createEvaluationDataset(chatbotId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/evaluations/assistants/${chatbotId}/datasets`, data);
  }

  updateEvaluationDataset(datasetId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/evaluations/datasets/${datasetId}`, data);
  }

  createEvaluationCase(datasetId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/evaluations/datasets/${datasetId}/cases`, data);
  }

  updateEvaluationCase(caseId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/evaluations/cases/${caseId}`, data);
  }

  duplicateEvaluationCase(caseId: number) {
    return this.http.post<any>(`${this.baseUrl}/evaluations/cases/${caseId}/duplicate`, {});
  }

  setEvaluationCaseEnabled(caseId: number, enabled: boolean) {
    return this.http.post<any>(`${this.baseUrl}/evaluations/cases/${caseId}/enabled`, {}, {
      params: { enabled: String(enabled) }
    });
  }

  importEvaluationCases(datasetId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/evaluations/datasets/${datasetId}/import`, data);
  }

  exportEvaluationDataset(datasetId: number, format: 'json' | 'csv' = 'json') {
    return this.http.get<any>(`${this.baseUrl}/evaluations/datasets/${datasetId}/export`, {
      params: { format },
      responseType: format === 'csv' ? 'text' as 'json' : 'json'
    });
  }

  runEvaluation(data: any) {
    return this.http.post<any>(`${this.baseUrl}/evaluations/runs`, data);
  }

  getEvaluationRuns(chatbotId: number) {
    return this.http.get<any[]>(`${this.baseUrl}/evaluations/assistants/${chatbotId}/runs`);
  }

  getEvaluationRun(runId: number) {
    return this.http.get<any>(`${this.baseUrl}/evaluations/runs/${runId}`);
  }

  compareEvaluationRuns(baselineRunId: number, candidateRunId: number) {
    return this.http.get<any>(`${this.baseUrl}/evaluations/compare`, {
      params: {
        baseline_run_id: String(baselineRunId),
        candidate_run_id: String(candidateRunId)
      }
    });
  }

  getEvaluationPolicy(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/evaluations/assistants/${chatbotId}/policy`);
  }

  updateEvaluationPolicy(chatbotId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/evaluations/assistants/${chatbotId}/policy`, data);
  }

  archiveVersion(versionId: number) {
    return this.http.put(
      `${this.baseUrl}/versions/${versionId}/archive`,
      {}
    );
  }

  duplicateVersion(versionId: number) {
    return this.http.post(
      `${this.baseUrl}/versions/${versionId}/duplicate`,
      {}
    );
  }

  deleteVersion(versionId: number) {
    return this.http.delete(`${this.baseUrl}/versions/${versionId}`);
  }

  getLlmConfig(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/llm-config/${versionId}`);
  }

  saveLlmConfig(data: any) {
    return this.http.post<any>(`${this.baseUrl}/llm-config`, data);
  }

  getFlow(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/versions/${versionId}/flow`);
  }

  validateFlow(versionId: number) {
    return this.http.get<any>(`${this.baseUrl}/versions/${versionId}/flow/validate`);
  }

  getFlowTemplates(filters: { purpose?: string; exposed_only?: boolean } = {}) {
    const params: any = {};
    if (filters.purpose) params.purpose = filters.purpose;
    if (filters.exposed_only !== undefined) params.exposed_only = filters.exposed_only;
    return this.http.get<any[]>(`${this.baseUrl}/flow-templates`, { params });
  }

  getFlowTemplateQa() {
    return this.http.get<any>(`${this.baseUrl}/flow-templates/qa`);
  }

  getFlowTemplate(templateKey: string, revision?: number) {
    const params: any = {};
    if (revision) params.revision = revision;
    return this.http.get<any>(`${this.baseUrl}/flow-templates/${encodeURIComponent(templateKey)}`, { params });
  }

  updateFlowTemplate(templateKey: string, data: any) {
    return this.http.patch<any>(`${this.baseUrl}/flow-templates/${encodeURIComponent(templateKey)}`, data);
  }

  runFlowTemplateTest(templateKey: string, data: any = {}) {
    return this.http.post<any>(`${this.baseUrl}/flow-templates/${encodeURIComponent(templateKey)}/test`, data);
  }

  createFlowTemplateFromFlow(flowId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/template-library`, data);
  }

  createFlowTemplateRevisionFromFlow(flowId: number, templateKey: string, data: any = {}) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/template-library/${encodeURIComponent(templateKey)}/revisions`, data);
  }

  applyFlowTemplate(flowId: number, templateKey: string, purpose?: string, templateRevision?: number) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/template`, {
      template_key: templateKey,
      ...(purpose ? { purpose } : {}),
      ...(templateRevision ? { template_revision: templateRevision } : {})
    }).pipe(
      tap(() => this.clearChatbotCaches())
    );
  }

  generateAssistantWithAi(data: any) {
    return this.http.post<any>(`${this.baseUrl}/assistants/ai-generate`, data);
  }

  applyGeneratedFlow(flowId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/generated`, data);
  }

  getChatbotBuilder(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/chatbots/${chatbotId}/builder`);
  }

  updateFlowNode(nodeId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/flow-nodes/${nodeId}`, data);
  }

  createFlowNode(flowId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/nodes`, data);
  }

  deleteFlowNode(nodeId: number) {
    return this.http.delete(`${this.baseUrl}/flow-nodes/${nodeId}`);
  }

  createFlowTransition(flowId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/flows/${flowId}/transitions`, data);
  }

  updateFlowTransition(transitionId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/flow-transitions/${transitionId}`, data);
  }

  deleteFlowTransition(transitionId: number) {
    return this.http.delete(`${this.baseUrl}/flow-transitions/${transitionId}`);
  }

  getDocuments(versionId: number) {
    return this.http.get<any[]>(
      `${this.baseUrl}/versions/${versionId}/documents`
    );
  }

  getDocument(documentId: number) {
    return this.http.get<any>(`${this.baseUrl}/documents/${documentId}`);
  }

  updateDocument(documentId: number, data: any) {
    return this.http.put<any>(`${this.baseUrl}/documents/${documentId}`, data);
  }

  getDocumentChunks(documentId: number) {
    return this.http.get<any[]>(`${this.baseUrl}/documents/${documentId}/chunks`);
  }

  reprocessDocumentEmbeddings(documentId: number) {
    return this.http.post<any>(`${this.baseUrl}/documents/${documentId}/embeddings/reprocess`, {});
  }

  reprocessDocumentChunks(documentId: number) {
    return this.http.post<any>(`${this.baseUrl}/documents/${documentId}/chunks/reprocess`, {});
  }

  uploadDocument(versionId: number, data: any) {
    return this.http.post(
      `${this.baseUrl}/versions/${versionId}/documents`,
      data
    );
  }

  testRagRetrieval(versionId: number, data: any) {
    return this.http.post<any>(`${this.baseUrl}/versions/${versionId}/rag-test`, data);
  }

  deleteDocument(documentId: number) {
    return this.http.delete(`${this.baseUrl}/documents/${documentId}`);
  }

  chat(data: any) {
    return this.http.post<any>(
      `${this.baseUrl}/chat`,
      data
    );
  }

  async chatStream(data: any, onEvent: (event: any) => void) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = this.authToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const requestDispatchedAt = Date.now();
    const response = await fetch(`${this.baseUrl}/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        ...data,
        client_request_dispatched_at_ms: requestDispatchedAt
      })
    });

    if (!response.ok || !response.body) {
      let detail = 'Chat failed';
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {}
      if (response.status === 404 && detail === 'Not Found') {
        const result = await firstValueFrom(this.chat(data));
        onEvent({
          type: 'final',
          ...result,
          __frontend_chunk_received_at_ms: this.nowMs(),
          latency: {
            ...(result?.latency || {}),
            stream_fallback_used: true
          }
        });
        return;
      }
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = this.consumeStreamingEvents(buffer, onEvent);
    }

    if (buffer.trim()) {
      this.consumeStreamingEvents(`${buffer}\n\n`, onEvent);
    }
  }

  private consumeStreamingEvents(buffer: string, onEvent: (event: any) => void) {
    if (buffer.includes('data:')) {
      const events = buffer.split('\n\n');
      const remainder = events.pop() || '';
      for (const rawEvent of events) {
        const dataLines = rawEvent
          .split('\n')
          .filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart());
        if (!dataLines.length) continue;
        onEvent({
          ...JSON.parse(dataLines.join('\n')),
          __frontend_chunk_received_at_ms: this.nowMs()
        });
      }
      return remainder;
    }

    const lines = buffer.split('\n');
    const remainder = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent({
        ...JSON.parse(line),
        __frontend_chunk_received_at_ms: this.nowMs()
      });
    }
    return remainder;
  }

  private nowMs() {
    return typeof performance !== 'undefined' ? performance.now() : Date.now();
  }

  startChatSession(data: any) {
    return this.http.post<any>(
      `${this.baseUrl}/chat/sessions`,
      data
    );
  }

  getPublicChatbot(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/public/chatbots/${chatbotId}`);
  }

  publicChat(data: any) {
    return this.http.post<any>(`${this.baseUrl}/public/chat`, data);
  }

  submitPublicFeedback(data: any) {
    return this.http.post<any>(`${this.baseUrl}/public/chat/feedback`, data);
  }

  async publicChatStream(data: any, onEvent: (event: any) => void) {
    const response = await fetch(`${this.baseUrl}/public/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    if (!response.ok || !response.body) {
      let detail = 'Chat failed';
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {}
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        onEvent(JSON.parse(line));
      }
    }

    if (buffer.trim()) {
      onEvent(JSON.parse(buffer));
    }
  }

  startPublicChatSession(data: any) {
    return this.http.post<any>(`${this.baseUrl}/public/chat/sessions`, data);
  }

  getAdminAnalyticsOverview() {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/overview`);
  }

  getAdminPlatformAnalytics(range = '30d') {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/platform`, {
      params: { range }
    });
  }

  getAdminAuditLogs(params: any = {}) {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/audit-logs`, { params });
  }

  getAdminChatbots(params: any = {}) {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/chatbots`, { params });
  }

  getAdminChatbot(chatbotId: number) {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/chatbots/${chatbotId}`);
  }

  getAdminRuntimeLogs(params: any = {}) {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/runtime-logs`, { params });
  }

  getPlatformSettings() {
    return this.http.get<any>(`${this.baseUrl}/admin/platform-settings`);
  }

  updatePlatformSettings(data: any) {
    return this.http.put<any>(`${this.baseUrl}/admin/platform-settings`, data);
  }

  getAdminSessions(chatbotId?: number) {
    const params: any = {};
    if (chatbotId) params.chatbot_id = chatbotId;
    return this.http.get<any[]>(`${this.baseUrl}/admin/analytics/sessions`, { params });
  }

  getAdminSession(sessionId: number) {
    return this.http.get<any>(`${this.baseUrl}/admin/analytics/sessions/${sessionId}`);
  }

  private clearProjectCaches(projectId?: number) {
    this.projectsCache.clear();
    if (projectId) {
      this.projectCache.delete(projectId);
      this.projectChatbotsCache.delete(projectId);
      this.projectChatbotsValueCache.delete(projectId);
    } else {
      this.projectCache.clear();
      this.projectChatbotsCache.clear();
      this.projectChatbotsValueCache.clear();
    }
  }

  private clearChatbotCaches(projectId?: number) {
    if (projectId) {
      this.projectChatbotsCache.delete(projectId);
      this.projectChatbotsValueCache.delete(projectId);
    } else {
      this.projectChatbotsCache.clear();
      this.projectChatbotsValueCache.clear();
    }
  }

  private ensureCacheScope() {
    const token = this.authToken();
    if (token !== this.cacheToken) {
      this.cacheToken = token;
      this.clearProjectCaches();
      this.clearChatbotCaches();
    }
  }

  private authToken() {
    if (typeof localStorage === 'undefined' || typeof localStorage.getItem !== 'function') {
      return '';
    }
    return localStorage.getItem('chatbot_factory_token') || '';
  }

}
