from datetime import datetime

from pydantic import BaseModel


class AdminUsersMetrics(BaseModel):
    total: int
    active: int
    disabled: int
    active_managers: int
    new_this_month: int


class AdminProjectsMetrics(BaseModel):
    total: int
    active: int | None = None
    disabled: int | None = None


class AdminChatbotsMetrics(BaseModel):
    total: int
    published: int
    draft: int
    active: int
    disabled: int


class AdminConversationsMetrics(BaseModel):
    total: int
    today: int
    total_messages: int
    messages_today: int


class AdminRuntimeMetrics(BaseModel):
    total_requests: int | None = None
    successful_requests: int | None = None
    failed_requests: int | None = None
    success_rate: float | None = None
    average_response_time_ms: int | None = None
    rag_usage_rate: float | None = None


class AdminKnowledgeBaseMetrics(BaseModel):
    total_documents: int
    processing_documents: int
    ready_documents: int
    failed_documents: int
    total_chunks: int
    total_embeddings: int


class AdminTopChatbot(BaseModel):
    chatbot_id: int
    chatbot_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    conversation_count: int
    published_version_id: int | None = None
    published_version_label: str | None = None
    status: str


class AdminChatbotsStats(BaseModel):
    total: int
    published: int
    draft_only: int
    disabled: int


class AdminChatbotListItem(BaseModel):
    chatbot_id: int
    chatbot_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    created_at: datetime | None = None
    versions_count: int
    latest_version_id: int | None = None
    latest_version_label: str | None = None
    published_version_id: int | None = None
    published_version_label: str | None = None
    conversations_count: int
    runtime_request_count: int
    last_activity_at: datetime | None = None
    last_runtime_at: datetime | None = None
    publication_status: str
    deployment_status: str
    disabled: bool
    enabled_channels: list[str]


class AdminChatbotsResponse(BaseModel):
    items: list[AdminChatbotListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: AdminChatbotsStats


class AdminChatbotDetailsResponse(AdminChatbotListItem):
    description: str | None = None
    language: str | None = None
    channel: str | None = None
    build_method: str | None = None
    updated_at: datetime | None = None


class AdminRecentActivityItem(BaseModel):
    id: int
    created_at: datetime | None = None
    actor_id: int | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    resource_type: str
    resource_id: int | None = None
    resource_name: str | None = None
    status: str
    details: dict | None = None


class AdminRecentActivityResponse(BaseModel):
    source: str
    items: list[AdminRecentActivityItem]


class AdminUsageResponse(BaseModel):
    labels: list[str]
    conversations: list[int]
    runtime_requests: list[int] | None = None


class AdminChannelsResponse(BaseModel):
    public_chat: int
    widget: int
    api: int
    legacy_other: int
    unknown: int


class AdminAnalyticsKpis(BaseModel):
    total_conversations: int
    runtime_requests: int
    runtime_success_rate: float | None = None
    average_response_time_ms: int | None = None


class AdminAnalyticsConversationSeries(BaseModel):
    labels: list[str]
    conversations: list[int]


class AdminAnalyticsRuntimeSeries(BaseModel):
    labels: list[str]
    successful_requests: list[int]
    failed_requests: list[int]
    total_requests: list[int]


class AdminAnalyticsChannelUsageItem(BaseModel):
    channel: str
    label: str
    conversations: int
    runtime_requests: int


class AdminAnalyticsTopChatbot(BaseModel):
    chatbot_id: int
    chatbot_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    conversations: int
    publication_status: str


class AdminAnalyticsRuntimePerformance(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float | None = None
    average_response_time_ms: int | None = None


class AdminAnalyticsResponse(BaseModel):
    period: str
    days: int
    start_date: datetime
    end_date: datetime
    kpis: AdminAnalyticsKpis
    conversations_over_time: AdminAnalyticsConversationSeries
    runtime_requests_over_time: AdminAnalyticsRuntimeSeries
    channel_usage: list[AdminAnalyticsChannelUsageItem]
    top_chatbots: list[AdminAnalyticsTopChatbot]
    runtime_performance: AdminAnalyticsRuntimePerformance
    legacy_channels_excluded: int


class AdminHealthService(BaseModel):
    status: str
    response_time_ms: int | None = None
    message: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    failures_last_24h: int | None = None
    success_rate_last_24h: float | None = None


class AdminSystemHealthResponse(BaseModel):
    checked_at: datetime
    services: dict[str, AdminHealthService]


class AdminDashboardOverview(BaseModel):
    users: AdminUsersMetrics
    projects: AdminProjectsMetrics
    chatbots: AdminChatbotsMetrics
    conversations: AdminConversationsMetrics
    runtime: AdminRuntimeMetrics
    knowledge_base: AdminKnowledgeBaseMetrics
    usage: AdminUsageResponse
    channels: AdminChannelsResponse
    top_chatbots: list[AdminTopChatbot]
    recent_activity: AdminRecentActivityResponse
    system_health: AdminSystemHealthResponse

    total_users: int
    active_users: int
    disabled_users: int
    active_managers: int
    new_users: int
    total_projects: int
    total_chatbots: int
    active_chatbots: int
    published_versions: int
    total_sessions: int
    total_messages: int
    sessions_today: int
    messages_today: int
    runtime_success_rate: float | None = None
    failed_runtime_requests: int | None = None
    average_response_time: int | None = None
    runtime_requests: int | None = None
    rag_usage: float | None = None
    documents_uploaded: int
    recent_sessions: list[dict]


class AdminRuntimeLogItem(BaseModel):
    id: int
    created_at: datetime | None = None
    chatbot_id: int | None = None
    chatbot_name: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    version_id: int | None = None
    version_label: str | None = None
    conversation_id: int | None = None
    channel: str
    status: str
    rag_used: bool
    response_time_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None


class AdminRuntimeLogsResponse(BaseModel):
    items: list[AdminRuntimeLogItem]
    total: int
    limit: int
    offset: int


class AdminAuditLogItem(BaseModel):
    id: int
    created_at: datetime | None = None
    actor_id: int | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    raw_action: str
    resource_type: str
    resource_id: int | None = None
    resource_name: str | None = None
    status: str


class AdminAuditLogsResponse(BaseModel):
    items: list[AdminAuditLogItem]
    total: int
    limit: int
    offset: int
