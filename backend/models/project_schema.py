from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str


class ProjectUpdate(BaseModel):
    name: str
    description: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    user_id: int
    status: str = "active"
    created_at: datetime
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    chatbot_count: int = 0
    assistants_count: int = 0
    version_count: int = 0
    published_version_count: int = 0
    assistant_count: int = 0
    published_assistants_count: int = 0
    draft_assistants_count: int = 0
    published_assistant_count: int = 0
    draft_only_assistant_count: int = 0
    last_activity_at: datetime | None = None
    last_activity: datetime | None = None
    health_status: str | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


class ProjectOverview(ProjectResponse):
    draft_version_count: int = 0
    archived_version_count: int = 0


class ProjectSummaryResponse(BaseModel):
    projects: int = 0
    assistants: int = 0
    published_assistants: int = 0
    draft_only: int = 0


class WorkspaceSummary(BaseModel):
    total_assistants: int = 0
    published_assistants: int = 0
    draft_only_assistants: int = 0


class WorkspaceMetric(BaseModel):
    label: str
    value: int | float | str | None = None
    suffix: str | None = None
    helper: str | None = None
    tone: str | None = None


class WorkspaceReadinessItem(BaseModel):
    label: str
    status: str
    message: str


class WorkspaceRecommendation(BaseModel):
    title: str
    message: str
    priority: str
    action: str | None = None
    affected_assistant_id: int | None = None
    affected_assistant_name: str | None = None
    expected_impact: str | None = None


class WorkspaceKnowledgeGap(BaseModel):
    question: str
    count: int
    last_asked_at: datetime | None = None
    session_id: int | None = None


class WorkspaceReleaseState(BaseModel):
    latest_version: dict | None = None
    latest_version_status: str | None = None
    published_version: dict | None = None
    last_published_at: datetime | None = None
    rollback_available: bool = False


class WorkspaceEvent(BaseModel):
    type: str
    title: str
    message: str
    created_at: datetime | None = None
    source: str | None = None
    severity: str | None = None
    category: str | None = None
    affected_assistant_id: int | None = None
    affected_assistant_name: str | None = None


class WorkspaceQualitySignal(BaseModel):
    session_id: int | None = None
    user_message: str = ""
    ai_response: str = ""
    retrieved_chunks: list = []
    latency_ms: int | None = None
    issue_type: str
    severity: str | None = None
    reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectWorkspaceDashboardResponse(BaseModel):
    project: ProjectOverview
    summary: WorkspaceSummary
    metrics: list[WorkspaceMetric]
    readiness_center: list[WorkspaceReadinessItem]
    recommended_actions: list[WorkspaceRecommendation]
    knowledge_gaps: list[WorkspaceKnowledgeGap]
    release_state: WorkspaceReleaseState
    operational_alerts: list[WorkspaceEvent]
    quality_signals: list[WorkspaceQualitySignal]


class ProjectAnalyticsKpis(BaseModel):
    conversations_count: int = 0
    messages_count: int = 0
    runtime_request_count: int = 0
    runtime_success_rate: int | None = None
    runtime_failure_count: int = 0
    average_response_latency_ms: int | None = None
    fallback_count: int = 0
    fallback_rate: int | None = None
    active_assistants_count: int = 0
    published_assistants_count: int = 0
    draft_assistants_count: int = 0


class ProjectAnalyticsResponse(BaseModel):
    project: ProjectOverview
    kpis: ProjectAnalyticsKpis
    usage_by_channel: list[dict]
    recent_errors: list[dict]
