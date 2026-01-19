"""
Request models for the AI Assistant.

Provides type-safe, validated request objects for all API operations.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class QuestionRequest(BaseModel):
    """
    Request to process a question.
    """
    question: str = Field(..., min_length=1, max_length=32000, description="User's question")
    chat_id: Optional[str] = Field(None, description="Session ID for conversation continuity")

    # Optional processing hints
    stream: bool = Field(False, description="Whether to stream the response")
    max_tokens: Optional[int] = Field(None, ge=1, le=128000, description="Max tokens in response")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Response temperature")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Validate and clean the question."""
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the weather in Seattle?",
                "chat_id": "550e8400-e29b-41d4-a716-446655440000",
                "stream": False
            }
        }


class WorkflowRequest(BaseModel):
    """
    Request to execute a workflow.
    """
    workflow_name: str = Field(..., min_length=1, description="Name of the workflow to execute")
    message: str = Field(..., min_length=1, max_length=32000, description="Input message for workflow")

    # Optional processing hints
    stream: bool = Field(False, description="Whether to stream the response")

    @field_validator("workflow_name")
    @classmethod
    def validate_workflow_name(cls, v: str) -> str:
        """Validate workflow name."""
        v = v.strip()
        if not v:
            raise ValueError("Workflow name cannot be empty")
        # Only allow alphanumeric, dash, underscore
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("Workflow name can only contain alphanumeric characters, dashes, and underscores")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "workflow_name": "content-pipeline",
                "message": "Write an article about AI trends in 2025",
                "stream": True
            }
        }


class ChatDeleteRequest(BaseModel):
    """
    Request to delete a chat session.
    """
    chat_id: str = Field(..., min_length=1, description="Session ID to delete")
    delete_from_persistence: bool = Field(True, description="Also delete from ADLS")

    class Config:
        json_schema_extra = {
            "example": {
                "chat_id": "550e8400-e29b-41d4-a716-446655440000",
                "delete_from_persistence": True
            }
        }


class ToolCallRequest(BaseModel):
    """
    Direct tool call request (for testing/debugging).
    """
    tool_name: str = Field(..., description="Name of the tool to call")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")

    class Config:
        json_schema_extra = {
            "example": {
                "tool_name": "weather",
                "parameters": {"location": "Seattle, WA"}
            }
        }
