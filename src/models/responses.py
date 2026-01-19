"""
Response models for the AI Assistant.

Provides type-safe, validated response objects for all API operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status for a single component."""
    name: str = Field(..., description="Component name")
    status: HealthStatus = Field(..., description="Health status")
    latency_ms: Optional[float] = Field(None, description="Check latency in milliseconds")
    message: Optional[str] = Field(None, description="Additional status message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class HealthResponse(BaseModel):
    """
    Health check response.

    Used for Kubernetes readiness/liveness probes.
    """
    status: HealthStatus = Field(..., description="Overall health status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    version: str = Field("1.0.0", description="Service version")
    components: List[ComponentHealth] = Field(default_factory=list, description="Component health details")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "version": "1.0.0",
                "components": [
                    {"name": "azure_openai", "status": "healthy", "latency_ms": 150},
                    {"name": "redis", "status": "healthy", "latency_ms": 5},
                    {"name": "adls", "status": "healthy", "latency_ms": 50}
                ]
            }
        }


class QuestionResponse(BaseModel):
    """
    Response for a processed question.

    Contains the AI assistant's response along with metadata.
    """
    question: str = Field(..., description="Original question")
    response: str = Field(..., description="AI assistant's response")
    success: bool = Field(..., description="Whether processing succeeded")
    chat_id: str = Field(..., description="Session ID for conversation continuity")

    # Optional metadata
    tokens_used: Optional[int] = Field(None, description="Total tokens used")
    prompt_tokens: Optional[int] = Field(None, description="Tokens in prompt")
    completion_tokens: Optional[int] = Field(None, description="Tokens in completion")
    tool_calls: List[str] = Field(default_factory=list, description="Tools that were called")
    latency_ms: Optional[float] = Field(None, description="Processing latency in milliseconds")
    model: Optional[str] = Field(None, description="Model used for response")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the weather in Seattle?",
                "response": "Based on the weather data, Seattle is currently 55°F with partly cloudy skies.",
                "success": True,
                "chat_id": "550e8400-e29b-41d4-a716-446655440000",
                "tokens_used": 150,
                "tool_calls": ["weather_lookup"],
                "latency_ms": 1250.5
            }
        }


class StreamChunk(BaseModel):
    """
    Streaming response chunk.

    Used for streaming responses token by token.
    """
    text: str = Field("", description="Text content in this chunk")
    done: bool = Field(False, description="Whether this is the final chunk")
    chat_id: Optional[str] = Field(None, description="Session ID (included in final chunk)")

    # Optional metadata (usually only in final chunk)
    tokens_used: Optional[int] = Field(None, description="Total tokens (final chunk only)")
    tool_calls: Optional[List[str]] = Field(None, description="Tools called (final chunk only)")
    error: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "The weather in ",
                "done": False,
                "chat_id": None
            }
        }


class WorkflowResponse(BaseModel):
    """
    Response for a workflow execution.

    Contains the combined output from all workflow agents.
    """
    workflow: str = Field(..., description="Name of the executed workflow")
    message: str = Field(..., description="Original input message")
    response: str = Field(..., description="Combined output from workflow")
    success: bool = Field(..., description="Whether workflow completed successfully")

    # Optional metadata
    author: Optional[str] = Field(None, description="Name of the final responding agent")
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="Workflow step details")
    latency_ms: Optional[float] = Field(None, description="Total execution latency")

    class Config:
        json_schema_extra = {
            "example": {
                "workflow": "content-pipeline",
                "message": "Write about AI trends",
                "response": "**Researcher:**\nKey trends include...\n\n**Writer:**\nThe AI landscape...",
                "success": True,
                "author": "Writer",
                "steps": [
                    {"agent": "Researcher", "status": "completed"},
                    {"agent": "Writer", "status": "completed"}
                ]
            }
        }


class WorkflowStreamChunk(BaseModel):
    """
    Streaming workflow response chunk.

    Includes agent attribution for each chunk.
    """
    text: str = Field("", description="Text content in this chunk")
    author: Optional[str] = Field(None, description="Agent that produced this text")
    done: bool = Field(False, description="Whether workflow is complete")

    # Optional metadata (final chunk)
    steps: Optional[List[Dict[str, Any]]] = Field(None, description="Workflow steps (final chunk)")
    error: Optional[str] = Field(None, description="Error message if failed")


class ChatListItem(BaseModel):
    """
    Chat session metadata for listing.
    """
    chat_id: str = Field(..., description="Session ID")
    active: bool = Field(False, description="Whether session is currently active")
    created_at: Optional[datetime] = Field(None, description="Session creation time")
    last_accessed: Optional[datetime] = Field(None, description="Last access time")
    message_count: int = Field(0, description="Number of messages in session")
    persisted: bool = Field(False, description="Whether session is persisted to ADLS")

    # Source information
    source: Optional[str] = Field(None, description="Where this session data came from")
    ttl_remaining: Optional[int] = Field(None, description="Seconds until cache expiry")


class ErrorResponse(BaseModel):
    """
    Standard error response.

    Used for all error conditions.
    """
    error: str = Field(..., description="Error message")
    error_type: str = Field("unknown", description="Error classification")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Azure OpenAI service unavailable",
                "error_type": "service_error",
                "details": {"retry_after": 30},
                "request_id": "req_12345",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }
