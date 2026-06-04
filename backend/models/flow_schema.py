from pydantic import BaseModel


class FlowNodeResponse(BaseModel):
    id: int
    node_key: str
    type: str
    label: str
    config: dict | None
    position_x: int
    position_y: int

    class Config:
        from_attributes = True


class FlowTransitionResponse(BaseModel):
    id: int
    source_node_key: str
    target_node_key: str
    label: str | None
    condition: str | None

    class Config:
        from_attributes = True


class FlowResponse(BaseModel):
    id: int
    version_id: int
    name: str
    nodes: list[FlowNodeResponse]
    transitions: list[FlowTransitionResponse]

    class Config:
        from_attributes = True


class BuilderContextResponse(BaseModel):
    chatbot: dict
    version: dict
    flow: FlowResponse


class FlowNodeUpdate(BaseModel):
    label: str | None = None
    config: dict | None = None
    position_x: int | None = None
    position_y: int | None = None


class FlowNodeCreate(BaseModel):
    type: str
    label: str
    config: dict | None = None
    position_x: int = 120
    position_y: int = 120


class FlowTransitionCreate(BaseModel):
    source_node_key: str
    target_node_key: str
    label: str | None = None
    condition: str | None = None


class FlowTransitionUpdate(BaseModel):
    source_node_key: str | None = None
    target_node_key: str | None = None
    label: str | None = None
    condition: str | None = None
