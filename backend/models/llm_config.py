from sqlalchemy import Column, String, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship
from database.db import Base


STRUCTURED_PROMPT_LABELS = {
    "tone": "Tone",
    "language": "Language",
    "response style": "Response style",
}


def split_structured_prompt_metadata(system_prompt: str | None) -> tuple[str, dict[str, str]]:
    lines = (system_prompt or "").splitlines()
    metadata: dict[str, str] = {}
    metadata_line_count = 0

    while lines:
        line = lines[-1].strip()
        if not line:
            lines.pop()
            continue
        if ":" not in line:
            break
        label, value = line.split(":", 1)
        key = label.strip().lower()
        if key not in STRUCTURED_PROMPT_LABELS:
            break
        metadata[key] = value.strip()
        metadata_line_count += 1
        lines.pop()

    if metadata_line_count < 2:
        return system_prompt or "", {}

    return "\n".join(lines).strip(), metadata


def effective_system_prompt(config: "LLMConfig") -> str:
    base_prompt, prompt_metadata = split_structured_prompt_metadata(config.system_prompt)
    base_prompt = base_prompt or "You are a helpful assistant"
    tone = (config.tone or prompt_metadata.get("tone") or "").strip()
    language = (config.language or prompt_metadata.get("language") or "").strip()
    response_style = (config.response_style or prompt_metadata.get("response style") or "").strip()

    lines = [base_prompt]
    if tone:
        lines.append(f"Tone: {tone}")
    if language:
        lines.append(f"Language: {language}")
    if response_style:
        lines.append(f"Response style: {response_style}")
    return "\n".join(lines)


class LLMConfig(Base):
    __tablename__ = "llm_configs"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id"), unique=True)

    model = Column(String, default="llama3")
    temperature = Column(Float, default=0.7)
    system_prompt = Column(String)
    tone = Column(String, default="Professional")
    language = Column(String, default="French")
    response_style = Column(String, default="Concise")

    version = relationship("VersionChatbot", back_populates="llm_config")
