from pydantic import BaseModel, ConfigDict, field_validator


SUPPORTED_CHATBOT_LANGUAGES = {"en", "fr"}
SUPPORTED_CHATBOT_CHANNELS = {"public_chat", "web_widget", "rest_public_api"}


def normalize_chatbot_language(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip().lower()
    aliases = {
        "english": "en",
        "anglais": "en",
        "en": "en",
        "french": "fr",
        "francais": "fr",
        "fr": "fr",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_CHATBOT_LANGUAGES:
        raise ValueError("Unsupported assistant language")
    return normalized


def safe_chatbot_language(value: str | None, default: str = "en") -> str:
    try:
        return normalize_chatbot_language(value) or default
    except ValueError:
        return default


def chatbot_language_instruction(value: str | None) -> str:
    if safe_chatbot_language(value) == "fr":
        return "Always respond in French by default. Use French for user-facing messages, greetings, fallback responses, and answers unless the user explicitly asks for another language."
    return "Always respond in English by default. Use English for user-facing messages, greetings, fallback responses, and answers unless the user explicitly asks for another language."


def normalize_chatbot_channel(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip().lower().replace(" ", "_")
    aliases = {
        "public_chat": "public_chat",
        "public": "public_chat",
        "web": "public_chat",
        "web_chat": "public_chat",
        "web_widget": "web_widget",
        "widget": "web_widget",
        "rest_public_api": "rest_public_api",
        "rest_api": "rest_public_api",
        "public_api": "rest_public_api",
        "api": "rest_public_api",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_CHATBOT_CHANNELS:
        raise ValueError("Unsupported assistant channel")
    return normalized


class ChatbotCreate(BaseModel):
    name: str
    description: str | None = None
    language: str
    assistant_type: str | None = None
    creation_mode: str | None = None
    type: str = "builder"
    project_id: int
    purpose: str = "custom"
    mode: str = "builder"
    channel: str = "web_widget"
    build_method: str = "blank"
    template_key: str | None = None
    source_template_key: str | None = None
    source_template_version: str | None = None
    ai_assistant_goal: str | None = None
    ai_business_context: str | None = None
    ai_knowledge_base_description: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_chatbot_language(value) or "fr"

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        return normalize_chatbot_channel(value) or "web_widget"


class ChatbotUpdate(BaseModel):
    name: str
    description: str | None = None
    language: str
    type: str = "builder"
    purpose: str = "custom"
    mode: str = "builder"
    channel: str = "web_widget"
    build_method: str | None = None
    creation_mode: str | None = None
    template_key: str | None = None
    source_template_key: str | None = None
    source_template_version: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_chatbot_language(value) or "fr"

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        return normalize_chatbot_channel(value) or "web_widget"


class ChatbotSetupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    language: str | None = None
    purpose: str | None = None
    channel: str | None = None
    ai_assistant_goal: str | None = None
    ai_business_context: str | None = None
    ai_knowledge_base_description: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        return normalize_chatbot_language(value)

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str | None) -> str | None:
        return normalize_chatbot_channel(value)


class ChatbotSetupResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    language: str
    purpose: str
    assistant_type: str
    channel: str
    creation_mode: str
    build_method: str
    template_key: str | None = None
    source_template_key: str | None = None
    source_template_version: str | None = None
    project_id: int
    template_name: str | None = None
    template_update_available: bool = False
    ai_regeneration_available: bool = False
    ai_assistant_goal: str | None = None
    ai_business_context: str | None = None
    ai_knowledge_base_description: str | None = None


class SetupGeneratedNode(BaseModel):
    key: str
    type: str
    label: str
    config: dict
    position_x: int
    position_y: int


class SetupGeneratedTransition(BaseModel):
    source_node_key: str
    target_node_key: str
    label: str | None = None
    condition: str | None = None


class ChatbotAiDraftRegenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_goal: str
    business_context: str
    knowledge_base_description: str | None = None
    generated_name: str | None = None
    generated_description: str | None = None
    nodes: list[SetupGeneratedNode]
    transitions: list[SetupGeneratedTransition]


class ChatbotStatusUpdate(BaseModel):
    is_active: bool


class ChatbotApiKeyResponse(BaseModel):
    public_api_key: str


class RagSettingsUpdate(BaseModel):
    retrieval_mode: str = "auto"
    max_chunks: int = 3
    min_score: float = 0.2
    show_sources: bool = True
    strict_context: bool = True
    response_length: str = "short"
