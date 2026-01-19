"""
AI Assistant using Microsoft Agent Framework + Dynamic Tool Loader.

A general-purpose, extensible AI agent that dynamically loads tools from
config/tools/*.json files and automatically discovers services using a
strict naming convention.

NAMING CONVENTION (Required for auto-discovery)
===============================================

config/tools/<NAME>.json         → Tool config file
src/<NAME>/service.py            → Service implementation class: <NAME>Service

Example:
  config/tools/weather.json → src/weather/service.py (WeatherService)

SERVICE INTERFACE
=================

All services must implement:

    def run(self, tool_call: Dict[str, Any]) -> str:
        # Extract parameters from tool_call (provided by LLM)
        query = tool_call.get('query', '')

        # Execute your logic
        result = self._do_something(query)

        # Return as string
        return str(result)

CONFIGURATION
=============

All configuration is in TOML format:
- config/agent.toml (recommended)
- or pyproject.toml [tool.agent] section

Environment variables can override TOML settings:
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_DEPLOYMENT
- AZURE_OPENAI_API_VERSION

ADDING NEW TOOLS (3 Steps)
==========================

1. Create config file: config/tools/<NAME>.json
   - Define function name, description, and parameters

2. Create service: src/<NAME>/service.py with <NAME>Service class
   - Implement run(tool_call) -> str method

3. (Optional) Add tool-specific config in agent.toml:
   [agent.tools.<NAME>]
   setting = "value"
"""

from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional
import time

import structlog
from azure.identity import DefaultAzureCredential
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Agent Framework imports
from agent_framework import ChatAgent

# Local imports
from src.config import get_config, AgentConfig
from src.models.providers import ModelFactory, ModelRegistry, parse_model_configs
from src.mcp.session import MCPSessionManager, MCPSessionConfig, parse_mcp_session_config
from src.loaders import load_and_register_tools, MCPManager, WorkflowManager
from src.agent.middleware import function_call_middleware, create_security_middleware
from src.memory import ChatHistoryManager
from src.models.responses import (
    QuestionResponse,
    StreamChunk,
    WorkflowResponse,
    WorkflowStreamChunk,
    HealthResponse,
    ChatListItem,
)
from src.observability import (
    setup_tracing,
    get_tracer,
    TracingConfig,
    setup_metrics,
    get_metrics,
)
from src.observability.metrics import MetricsConfig
from src.observability.tracing import trace_llm_call, trace_tool_execution
from src.health import (
    HealthChecker,
    HealthCheckConfig,
    create_redis_check,
    create_adls_check,
    create_mcp_check,
)
from src.security import RateLimiter, RateLimitConfig, InputValidator, ValidationConfig


logger = structlog.get_logger(__name__)


def _load_system_prompt(config: AgentConfig) -> str:
    """Load system prompt from configuration file."""
    prompt_path = Path(config.system_prompt_file)

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"System prompt file not found: {config.system_prompt_file}"
        )

    prompt = prompt_path.read_text(encoding="utf-8").strip()
    logger.info("Loaded system prompt", prompt_file=config.system_prompt_file)
    return prompt


class AIAssistant:
    """
    AI Assistant with dynamic tool loading, MCP support, workflows, and service discovery.

    Uses Microsoft Agent Framework to reason across multiple data sources.

    Tools are loaded from:
    1. Local tools: config/tools/*.json files matched to src/<NAME>/service.py
    2. MCP servers: Configured in agent.toml [[agent.mcp]] sections

    Workflows are loaded from:
    - agent.toml [[agent.workflows]] sections - multi-agent orchestration pipelines

    Services implement the run(tool_call) -> str method.

    Features:
    - Streaming responses
    - OpenTelemetry observability
    - Retry logic for transient failures
    - Rate limiting and input validation
    - Health checks
    """

    def __init__(self, config: AgentConfig = None) -> None:
        """
        Initialize assistant with Azure OpenAI and load tools dynamically.

        Note: MCP servers require async initialization. Call `await assistant.initialize()`
        after creating the instance, or use the async context manager:

            async with await AIAssistant.create() as assistant:
                result = await assistant.process_question("Hello!")

        Args:
            config: Optional AgentConfig instance. If not provided, loads from
                   config/agent.toml or pyproject.toml
        """
        # Load configuration
        self.config = config or get_config()
        self.config.validate()

        # Load system prompt
        self.system_prompt = _load_system_prompt(self.config)
        self.tools: list = []

        # MCP manager for external tool servers
        self._mcp_manager = MCPManager()
        self._mcp_initialized = False

        # Workflow manager for multi-agent pipelines
        self._workflow_manager: Optional[WorkflowManager] = None

        # Chat history manager (cache + persistence)
        self._history_manager: Optional[ChatHistoryManager] = None

        # Security components
        # Rate limiting enabled by default for production safety
        self._rate_limiter = RateLimiter(RateLimitConfig(
            enabled=getattr(self.config, 'rate_limit_enabled', True),
            requests_per_minute=getattr(self.config, 'rate_limit_rpm', 30),
        ))
        self._input_validator = InputValidator(ValidationConfig(
            block_prompt_injection=getattr(self.config, 'block_prompt_injection', True),
        ))

        # Health checker
        self._health_checker = HealthChecker(HealthCheckConfig(
            version=getattr(self.config, 'version', '1.0.0'),
        ))

        # Initialize observability
        self._init_observability()

        # Initialize model registry for multi-model support
        self._model_registry = ModelRegistry()
        model_configs, default_model = parse_model_configs(self.config._config)
        if model_configs:
            self._model_registry.load_from_config(model_configs, default_model)
        else:
            # Fallback to legacy Azure OpenAI config
            from src.models.providers import ModelProviderConfig
            legacy_config = ModelProviderConfig(
                name="azure_openai",
                provider="azure_openai",
                model=self.config.azure_openai_deployment,
                endpoint=self.config.azure_openai_endpoint,
                api_version=self.config.azure_openai_api_version,
            )
            self._model_registry.register(legacy_config, is_default=True)

        # Initialize chat client from model registry
        self.chat_client = ModelFactory.create_client(self._model_registry.get_default())

        # MCP session manager (initialized in async initialize())
        self._mcp_session_manager: Optional[MCPSessionManager] = None
        self._mcp_session_config = parse_mcp_session_config(self.config._config)

        # Load local tools (sync)
        self._load_tools()

        # Agent will be created after MCP initialization
        self.agent = None

        # Metrics
        self._metrics = get_metrics()

        logger.info(
            "AI Assistant created (call initialize() for MCP support)",
            local_tools_count=len(self.tools),
            deployment=self.config.azure_openai_deployment
        )

    def _init_observability(self) -> None:
        """Initialize observability (tracing and metrics)."""
        # Check if observability config exists
        obs_config = getattr(self.config, 'observability', None)

        if obs_config:
            # Setup tracing
            tracing_config = TracingConfig(
                enabled=obs_config.get('tracing_enabled', False),
                service_name=obs_config.get('service_name', 'ai-assistant'),
                exporter_type=obs_config.get('tracing_exporter', 'console'),
            )
            setup_tracing(tracing_config)

            # Setup metrics
            metrics_config = MetricsConfig(
                enabled=obs_config.get('metrics_enabled', False),
                service_name=obs_config.get('service_name', 'ai-assistant'),
                exporter_type=obs_config.get('metrics_exporter', 'console'),
            )
            setup_metrics(metrics_config)

    async def initialize(self) -> "AIAssistant":
        """
        Initialize async components (MCP servers, workflows).

        Call this after creating the instance to enable MCP and workflow support:

            assistant = AIAssistant()
            await assistant.initialize()

        Returns:
            self for method chaining
        """
        if self._mcp_initialized:
            return self

        # Initialize MCP session manager if enabled
        if self._mcp_session_config.enabled:
            # Will be set up after history manager is created
            pass

        # Load MCP servers if configured
        if self.config.mcp_configs:
            mcp_tools = await self._mcp_manager.load_mcp_servers(self.config.mcp_configs)
            logger.info("MCP servers initialized", count=len(mcp_tools))

        # Load workflows if configured (with per-agent model support)
        if self.config.workflow_configs:
            self._workflow_manager = WorkflowManager(
                self.chat_client,
                model_registry=self._model_registry
            )
            self._workflow_manager.load_workflows(self.config.workflow_configs)
            logger.info(
                "Workflows initialized",
                count=len(self._workflow_manager.workflows),
                names=self._workflow_manager.workflow_names
            )

        # Combine local tools with MCP tools
        all_tools = self.tools + self._mcp_manager.tools

        # Create security middleware
        security_middleware = create_security_middleware(self._input_validator)

        # Create agent with all tools and middleware
        self.agent = ChatAgent(
            chat_client=self.chat_client,
            instructions=self.system_prompt,
            tools=all_tools,
            middleware=[function_call_middleware, security_middleware],
        )

        # Initialize chat history manager
        self._history_manager = ChatHistoryManager(self.config.memory_config)
        self._history_manager.set_agent(self.agent)

        # Start background persist if configured
        await self._history_manager.start_background_persist()

        # Initialize MCP session manager with cache/persistence from history manager
        if self._mcp_session_config.enabled:
            self._mcp_session_manager = MCPSessionManager(
                cache=self._history_manager._cache,
                persistence=self._history_manager._persistence,
                config=self._mcp_session_config,
            )
            # Attach session manager to MCP manager for stateful tool wrapping
            self._mcp_manager.set_session_manager(self._mcp_session_manager)
            logger.info("MCP session manager initialized")

        # Register health checks
        await self._register_health_checks()

        self._mcp_initialized = True
        workflow_count = len(self._workflow_manager.workflows) if self._workflow_manager else 0
        logger.info(
            "AI Assistant fully initialized",
            local_tools=len(self.tools),
            mcp_tools=len(self._mcp_manager.tools),
            total_tools=len(all_tools),
            workflows=workflow_count
        )

        return self

    async def _register_health_checks(self) -> None:
        """Register health check functions."""
        # Redis check
        if self._history_manager and self._history_manager._cache:
            self._health_checker.register_check(
                "redis",
                await create_redis_check(self._history_manager._cache)
            )

        # ADLS check
        if self._history_manager and self._history_manager._persistence:
            self._health_checker.register_check(
                "adls",
                await create_adls_check(self._history_manager._persistence)
            )

        # MCP check
        if self._mcp_manager:
            self._health_checker.register_check(
                "mcp",
                await create_mcp_check(self._mcp_manager)
            )

    @classmethod
    async def create(cls, config: AgentConfig = None) -> "AIAssistant":
        """
        Factory method to create and initialize an AI Assistant.

        Use this for full initialization including MCP support:

            assistant = await AIAssistant.create()
            result = await assistant.process_question("Hello!")

        Args:
            config: Optional AgentConfig instance

        Returns:
            Fully initialized AIAssistant instance
        """
        instance = cls(config)
        await instance.initialize()
        return instance

    async def __aenter__(self) -> "AIAssistant":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    def _load_tools(self) -> None:
        """
        Load and register all tools using the hybrid tool loader.

        Supports two patterns:
        1. Decorator Pattern (SDK-compliant): Auto-discovers @register_tool functions
        2. JSON Config Pattern (Legacy): Loads from config/tools/*.json files

        Configuration in agent.toml [agent.tools]:
        - enable_decorator_tools: Enable @register_tool auto-discovery (default: True)
        - enable_json_tools: Enable JSON config loading (default: True)
        - tool_modules: Optional explicit list of module paths to load

        Decorator tools take precedence on name conflicts.
        """
        tools_loaded = load_and_register_tools(
            self,
            config_dir=self.config.tools_config_dir,
            tool_modules=getattr(self.config, 'tool_modules', None),
            enable_decorator_tools=getattr(self.config, 'enable_decorator_tools', True),
            enable_json_tools=getattr(self.config, 'enable_json_tools', True),
        )
        logger.info("Tools loaded via hybrid loader", count=tools_loaded)

    def get_chat_client(self, model_name: Optional[str] = None) -> Any:
        """
        Get chat client for a specific model or the default.

        Args:
            model_name: Optional model name from the registry.
                       If not provided, returns the default client.

        Returns:
            Chat client instance

        Raises:
            KeyError: If model_name not found in registry
        """
        if model_name:
            config = self._model_registry.get_provider(model_name)
            return ModelFactory.create_client(config)
        return self.chat_client

    def list_models(self) -> list[str]:
        """Get list of available model provider names."""
        return self._model_registry.list_providers()

    @property
    def model_registry(self) -> ModelRegistry:
        """Access the model registry for advanced usage."""
        return self._model_registry

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )
    async def _call_agent(self, question: str, thread: Any) -> Any:
        """
        Call the agent with retry logic.

        Args:
            question: User's question
            thread: Conversation thread

        Returns:
            Agent response
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("agent_run") as span:
            span.set_attribute("question_length", len(question))
            result = await self.agent.run(question, thread=thread)
            span.set_attribute("response_length", len(result.text) if result.text else 0)
            return result

    async def process_question(
        self,
        question: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> QuestionResponse:
        """
        Process a question using the Agent Framework.

        The Agent Framework automatically handles:
        - Agentic reasoning loop
        - Tool selection and calling
        - Context management
        - Multi-step reasoning
        - Loop termination

        Args:
            question: User's question to process
            chat_id: Optional session ID for conversation continuity.
                    If provided and found in cache/ADLS, continues that session.
                    If provided but not found, creates new session with that ID.
                    If not provided, generates new UUID for the session.
            user_id: Optional user ID for rate limiting
            model: Optional model name for per-request model override.
                  Must be registered in the model registry.

        Returns:
            QuestionResponse with the agent's response and metadata
        """
        start_time = time.perf_counter()
        tracer = get_tracer()

        with tracer.start_as_current_span("process_question") as span:
            span.set_attribute("chat_id", chat_id or "new")

            # Auto-initialize if needed (for simple usage without MCP)
            if self.agent is None:
                await self.initialize()

            # Rate limiting
            try:
                await self._rate_limiter.check_limit(user_id)
                await self._rate_limiter.acquire_concurrent_slot(user_id)
            except Exception as e:
                return QuestionResponse(
                    question=question,
                    response=f"Rate limit exceeded: {str(e)}",
                    success=False,
                    chat_id=chat_id or "",
                )

            try:
                # Input validation
                question = self._input_validator.validate(question, context="question")

                # Log request metadata without sensitive content (security best practice)
                logger.info(
                    "Processing question",
                    question_length=len(question),
                    question_hash=hash(question) % 10000,  # Non-reversible identifier
                    chat_id=chat_id,
                    model=model
                )

                # Get or create thread for this session
                chat_id, thread = await self._history_manager.get_or_create_thread(chat_id)

                # Build MCP session kwargs for stateful MCP tools
                mcp_kwargs = {}
                if chat_id:
                    mcp_kwargs["chat_id"] = chat_id
                if user_id:
                    mcp_kwargs["user_id"] = user_id

                # Use specified model or default
                agent_to_use = self.agent
                if model and model != self._model_registry.default_name:
                    # Create temporary agent with specified model
                    model_client = self.get_chat_client(model)
                    agent_to_use = ChatAgent(
                        chat_client=model_client,
                        instructions=self.system_prompt,
                        tools=self.tools + self._mcp_manager.tools,
                    )
                    logger.debug("Using model override", model=model)

                # Run agent with retry logic (MCP kwargs propagated via thread context)
                result = await self._call_agent(question, thread)

                # Save thread state
                await self._history_manager.save_thread(chat_id, thread)

                # Calculate latency
                latency_ms = (time.perf_counter() - start_time) * 1000

                # Record metrics
                self._metrics.record_request(latency_ms, success=True, chat_id=chat_id)
                await self._rate_limiter.record_request(user_id)

                logger.info("Processing completed successfully", chat_id=chat_id, latency_ms=latency_ms)

                return QuestionResponse(
                    question=question,
                    response=result.text,
                    success=True,
                    chat_id=chat_id,
                    latency_ms=latency_ms,
                )

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                self._metrics.record_request(latency_ms, success=False, chat_id=chat_id)
                self._metrics.record_error(type(e).__name__, "process_question")

                logger.error("Processing failed", error=str(e), chat_id=chat_id)
                span.record_exception(e)

                return QuestionResponse(
                    question=question,
                    response=f"Error: {str(e)}",
                    success=False,
                    chat_id=chat_id or "",
                    latency_ms=latency_ms,
                )
            finally:
                await self._rate_limiter.release_concurrent_slot(user_id)

    async def process_question_stream(
        self,
        question: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Process a question with streaming response.

        Streams the response token by token for better UX.

        Args:
            question: User's question to process
            chat_id: Optional session ID for conversation continuity
            user_id: Optional user ID for rate limiting

        Yields:
            StreamChunk objects with progressive response text
        """
        start_time = time.perf_counter()
        tracer = get_tracer()

        with tracer.start_as_current_span("process_question_stream") as span:
            span.set_attribute("chat_id", chat_id or "new")
            span.set_attribute("streaming", True)

            # Auto-initialize if needed
            if self.agent is None:
                await self.initialize()

            # Rate limiting
            try:
                await self._rate_limiter.check_limit(user_id)
                await self._rate_limiter.acquire_concurrent_slot(user_id)
            except Exception as e:
                yield StreamChunk(text="", done=True, error=str(e))
                return

            try:
                # Input validation
                question = self._input_validator.validate(question, context="question")

                # Get or create thread
                chat_id, thread = await self._history_manager.get_or_create_thread(chat_id)

                logger.info("Starting streaming response", chat_id=chat_id)

                # Stream from agent
                tool_calls = []
                async for update in self.agent.run_stream(question, thread=thread):
                    if hasattr(update, 'text') and update.text:
                        yield StreamChunk(text=update.text, done=False)

                    # Track tool calls if available
                    if hasattr(update, 'tool_call') and update.tool_call:
                        tool_calls.append(update.tool_call.name)

                # Save thread state
                await self._history_manager.save_thread(chat_id, thread)

                # Calculate latency
                latency_ms = (time.perf_counter() - start_time) * 1000

                # Record metrics
                self._metrics.record_request(latency_ms, success=True, chat_id=chat_id)
                await self._rate_limiter.record_request(user_id)

                # Final chunk with metadata
                yield StreamChunk(
                    text="",
                    done=True,
                    chat_id=chat_id,
                    tool_calls=tool_calls if tool_calls else None,
                )

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                self._metrics.record_request(latency_ms, success=False, chat_id=chat_id)
                self._metrics.record_error(type(e).__name__, "process_question_stream")

                logger.error("Streaming failed", error=str(e), chat_id=chat_id)
                span.record_exception(e)

                yield StreamChunk(text="", done=True, error=str(e))
            finally:
                await self._rate_limiter.release_concurrent_slot(user_id)

    async def run_workflow(
        self,
        workflow_name: str,
        message: str,
        stream: bool = False
    ) -> WorkflowResponse | AsyncGenerator[WorkflowStreamChunk, None]:
        """
        Run a named workflow with the given message.

        Workflows are multi-agent pipelines that can include:
        - Sequential execution (agents run in order)
        - Custom routing (user-defined agent graph)

        Args:
            workflow_name: Name of the workflow to run (as defined in config)
            message: Input message to process through the workflow
            stream: If True, streams responses (returns async generator)

        Returns:
            WorkflowResponse or AsyncGenerator[WorkflowStreamChunk]
        """
        start_time = time.perf_counter()
        tracer = get_tracer()

        with tracer.start_as_current_span("run_workflow") as span:
            span.set_attribute("workflow", workflow_name)
            span.set_attribute("streaming", stream)

            # Auto-initialize if needed
            if self.agent is None:
                await self.initialize()

            if not self._workflow_manager:
                return WorkflowResponse(
                    workflow=workflow_name,
                    message=message,
                    response="No workflows configured",
                    success=False,
                )

            workflow_agent = self._workflow_manager.get_workflow(workflow_name)
            if not workflow_agent:
                available = self._workflow_manager.workflow_names
                return WorkflowResponse(
                    workflow=workflow_name,
                    message=message,
                    response=f"Workflow '{workflow_name}' not found. Available: {available}",
                    success=False,
                )

            logger.info("Running workflow", workflow=workflow_name, message=message[:100])

            try:
                # Import message types
                from agent_framework import ChatMessage, Role

                # Create thread for workflow state
                thread = workflow_agent.get_new_thread()
                messages = [ChatMessage(role=Role.USER, content=message)]

                if stream:
                    # Return streaming generator
                    async def stream_workflow():
                        async for update in workflow_agent.run_stream(messages, thread=thread):
                            yield WorkflowStreamChunk(
                                text=update.text if hasattr(update, 'text') else "",
                                author=update.author_name if hasattr(update, 'author_name') else None,
                                done=False
                            )
                        yield WorkflowStreamChunk(text="", done=True)
                    return stream_workflow()
                else:
                    # Non-streaming execution
                    response = await workflow_agent.run(messages, thread=thread)

                    # Collect response text
                    response_text = ""
                    final_author = None
                    steps = []

                    for msg in response.messages:
                        if msg.text:
                            response_text += f"\n\n**{msg.author_name}:**\n{msg.text}" if msg.author_name else msg.text
                            final_author = msg.author_name
                            steps.append({"agent": msg.author_name, "status": "completed"})

                    latency_ms = (time.perf_counter() - start_time) * 1000

                    logger.info("Workflow completed", workflow=workflow_name, author=final_author, latency_ms=latency_ms)

                    return WorkflowResponse(
                        workflow=workflow_name,
                        message=message,
                        response=response_text.strip(),
                        success=True,
                        author=final_author,
                        steps=steps,
                        latency_ms=latency_ms,
                    )

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                self._metrics.record_error(type(e).__name__, "run_workflow")

                logger.error("Workflow failed", workflow=workflow_name, error=str(e))
                span.record_exception(e)

                return WorkflowResponse(
                    workflow=workflow_name,
                    message=message,
                    response=f"Error: {str(e)}",
                    success=False,
                    latency_ms=latency_ms,
                )

    def list_workflows(self) -> list:
        """Get list of available workflow names."""
        if not self._workflow_manager:
            return []
        return self._workflow_manager.workflow_names

    async def list_chats(
        self,
        source: str = "all",
        limit: int = 100
    ) -> list[ChatListItem]:
        """
        List available chat sessions.

        Args:
            source: "cache", "persistence", or "all"
            limit: Maximum number of results

        Returns:
            List of ChatListItem objects
        """
        if not self._history_manager:
            return []

        raw_chats = await self._history_manager.list_chats(source=source, limit=limit)

        return [
            ChatListItem(
                chat_id=chat["chat_id"],
                active=chat.get("active", False),
                created_at=chat.get("created_at"),
                last_accessed=chat.get("last_accessed"),
                message_count=chat.get("message_count", 0),
                persisted=chat.get("persisted", False),
                source=chat.get("source"),
                ttl_remaining=chat.get("ttl_remaining"),
            )
            for chat in raw_chats
        ]

    async def delete_chat(self, chat_id: str) -> bool:
        """
        Delete a chat session from all storage layers.

        Args:
            chat_id: The session ID to delete

        Returns:
            True if deleted successfully
        """
        if not self._history_manager:
            return False
        return await self._history_manager.delete_chat(chat_id)

    async def health_check(self) -> HealthResponse:
        """
        Run health checks on all components.

        Returns:
            HealthResponse with component status
        """
        result = await self._health_checker.check_all()
        return HealthResponse(
            status=result.status,
            timestamp=result.timestamp,
            version=result.version,
            components=[
                {
                    "name": c.name,
                    "status": c.status,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "details": c.details,
                }
                for c in result.components
            ]
        )

    async def close(self) -> None:
        """Close resources and cleanup."""
        # Close chat history manager (persists active sessions)
        if self._history_manager:
            await self._history_manager.close()

        # Close MCP connections
        if self._mcp_manager:
            await self._mcp_manager.close()

        # Close local services
        for attr_name in dir(self):
            if attr_name.endswith('_service'):
                service = getattr(self, attr_name, None)
                if service and hasattr(service, 'close'):
                    try:
                        service.close()
                        logger.debug("Closed service", service_name=attr_name)
                    except Exception as e:
                        logger.warning(
                            "Failed to close service",
                            service_name=attr_name,
                            error=str(e)
                        )
        logger.info("AI Assistant closed")


# Singleton instance for convenience
_assistant_instance = None


async def process_query(question: str, chat_id: Optional[str] = None) -> str:
    """
    Simple helper function to process a query using the AI Assistant.
    Creates a singleton instance for efficiency.

    Args:
        question: User's question to process
        chat_id: Optional session ID for conversation continuity

    Returns:
        str: Agent's response text
    """
    global _assistant_instance

    if _assistant_instance is None:
        _assistant_instance = await AIAssistant.create()
        logger.info("Created new AI Assistant instance")

    result = await _assistant_instance.process_question(question, chat_id=chat_id)
    return result.response


async def main():
    """Example usage of the AI Assistant with MCP support."""
    # Method 1: Using async context manager (recommended)
    async with AIAssistant() as assistant:
        # Non-streaming
        result = await assistant.process_question("Hello! What can you help me with?")
        print(f"Response: {result.response}")

        # Streaming
        print("\nStreaming response:")
        async for chunk in await assistant.process_question_stream("Tell me a short joke"):
            if chunk.text:
                print(chunk.text, end="", flush=True)
            if chunk.done:
                print(f"\n\nChat ID: {chunk.chat_id}")

        # Health check
        health = await assistant.health_check()
        print(f"\nHealth Status: {health.status}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
