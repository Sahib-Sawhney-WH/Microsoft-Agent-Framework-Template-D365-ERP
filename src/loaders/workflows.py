"""
Workflow loader for the AI Assistant.

Loads and manages Microsoft Agent Framework workflows from configuration.
Supports multiple workflow patterns:
- sequential: Agents execute in order
- custom: User-defined workflow graphs via config

Enhanced features:
- Conditional edge routing based on agent output
- Expression evaluation for dynamic workflow paths
"""

import re
import operator
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING
from pathlib import Path

import structlog

# Import Workflow types from Agent Framework
try:
    from agent_framework import ChatAgent, WorkflowBuilder
    from agent_framework._workflows import SequentialBuilder
    WORKFLOW_AVAILABLE = True
except ImportError:
    try:
        from agent_framework import ChatAgent
        from agent_framework.workflows import WorkflowBuilder, SequentialBuilder
        WORKFLOW_AVAILABLE = True
    except ImportError:
        WORKFLOW_AVAILABLE = False
        WorkflowBuilder = None
        SequentialBuilder = None

if TYPE_CHECKING:
    from src.models.providers import ModelRegistry

logger = structlog.get_logger(__name__)


class ConditionEvaluator:
    """
    Evaluates conditional expressions for workflow routing.

    Supports expressions like:
    - "output.category == 'technical'"
    - "output.confidence > 0.8"
    - "output.route == 'billing'"
    - "'error' in output.text"
    - "output.priority in ['high', 'critical']"

    The 'output' variable represents the previous agent's output.
    """

    # Supported comparison operators
    OPERATORS = {
        '==': operator.eq,
        '!=': operator.ne,
        '>': operator.gt,
        '>=': operator.ge,
        '<': operator.lt,
        '<=': operator.le,
        'in': lambda a, b: a in b,
        'not in': lambda a, b: a not in b,
        'contains': lambda a, b: b in a,
    }

    # Pattern to parse condition expressions
    # Matches: output.field op value, value in output.field, etc.
    CONDITION_PATTERN = re.compile(
        r"^(?:output\.(\w+(?:\.\w+)*))\s*(==|!=|>=?|<=?|in|not in|contains)\s*(.+)$|"
        r"^(.+?)\s+(in|not in)\s+(?:output\.(\w+(?:\.\w+)*))$",
        re.IGNORECASE
    )

    def __init__(self):
        """Initialize the condition evaluator."""
        self._cache: Dict[str, Callable] = {}

    def evaluate(
        self,
        condition: str,
        output: Union[str, Dict[str, Any]]
    ) -> bool:
        """
        Evaluate a condition against an agent's output.

        Args:
            condition: The condition expression to evaluate
            output: The agent's output (string or dict)

        Returns:
            True if condition is met, False otherwise
        """
        if not condition:
            return True  # No condition = always true

        condition = condition.strip()

        # Try to parse the output as a dict if it's a string that looks like JSON
        if isinstance(output, str):
            try:
                import json
                output_dict = json.loads(output)
                if isinstance(output_dict, dict):
                    output = output_dict
            except (json.JSONDecodeError, TypeError):
                # Wrap string output in a dict for consistent access
                output = {"text": output, "raw": output}

        try:
            return self._evaluate_condition(condition, output)
        except Exception as e:
            logger.warning(
                "Condition evaluation failed, returning False",
                condition=condition,
                error=str(e)
            )
            return False

    def _evaluate_condition(
        self,
        condition: str,
        output: Dict[str, Any]
    ) -> bool:
        """Internal condition evaluation."""
        # Handle logical operators (and, or)
        if ' and ' in condition.lower():
            parts = re.split(r'\s+and\s+', condition, flags=re.IGNORECASE)
            return all(self._evaluate_condition(p.strip(), output) for p in parts)

        if ' or ' in condition.lower():
            parts = re.split(r'\s+or\s+', condition, flags=re.IGNORECASE)
            return any(self._evaluate_condition(p.strip(), output) for p in parts)

        # Parse the condition
        match = self.CONDITION_PATTERN.match(condition)

        if match:
            groups = match.groups()

            # Pattern 1: output.field op value
            if groups[0] is not None:
                field_path = groups[0]
                op_str = groups[1].lower()
                value_str = groups[2].strip()

                field_value = self._get_field_value(output, field_path)
                compare_value = self._parse_value(value_str)

                op_func = self.OPERATORS.get(op_str)
                if op_func:
                    return op_func(field_value, compare_value)

            # Pattern 2: value in output.field
            elif groups[3] is not None:
                value_str = groups[3].strip()
                op_str = groups[4].lower()
                field_path = groups[5]

                compare_value = self._parse_value(value_str)
                field_value = self._get_field_value(output, field_path)

                op_func = self.OPERATORS.get(op_str)
                if op_func:
                    return op_func(compare_value, field_value)

        # Fallback: check if condition substring exists in output text
        output_text = str(output.get('text', output.get('raw', str(output))))
        return condition.lower() in output_text.lower()

    def _get_field_value(
        self,
        obj: Dict[str, Any],
        field_path: str
    ) -> Any:
        """Get a nested field value using dot notation."""
        parts = field_path.split('.')
        value = obj

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        return value

    def _parse_value(self, value_str: str) -> Any:
        """Parse a value string into the appropriate type."""
        value_str = value_str.strip()

        # String literal
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]

        # List literal - use json.loads() for safety (prevents DoS via memory exhaustion)
        if value_str.startswith('[') and value_str.endswith(']'):
            try:
                import json
                # Replace single quotes with double quotes for JSON compatibility
                json_str = value_str.replace("'", '"')
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                return value_str

        # Boolean
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False

        # None
        if value_str.lower() in ('none', 'null'):
            return None

        # Number
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        return value_str


class ConditionalEdge:
    """Represents a conditional edge in the workflow graph."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        condition: Optional[str] = None,
        priority: int = 0
    ):
        """
        Initialize a conditional edge.

        Args:
            from_agent: Name of the source agent
            to_agent: Name of the target agent
            condition: Optional condition expression
            priority: Edge priority (higher = evaluated first)
        """
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.condition = condition
        self.priority = priority

    def __repr__(self) -> str:
        return f"ConditionalEdge({self.from_agent} -> {self.to_agent}, condition={self.condition})"


class WorkflowManager:
    """
    Manages workflow creation and execution for the AI Assistant.
    
    Creates multi-agent workflows from configuration, allowing complex
    orchestration patterns like sequential pipelines, parallel execution,
    and conditional routing.
    
    Supports per-agent model selection via the ModelRegistry, allowing
    different agents in a workflow to use different LLM providers.
    """
    
    def __init__(
        self,
        chat_client: Any,
        model_registry: Optional["ModelRegistry"] = None,
    ):
        """
        Initialize the workflow manager.

        Args:
            chat_client: The default chat client to use for agents
            model_registry: Optional ModelRegistry for per-agent model selection.
                          If provided, agents can specify a "model" in their config
                          to use a different model than the default.
        """
        self._chat_client = chat_client
        self._model_registry = model_registry
        self._workflows: Dict[str, Any] = {}
        self._workflow_agents: Dict[str, Any] = {}
        self._workflow_edges: Dict[str, List[ConditionalEdge]] = {}
        self._condition_evaluator = ConditionEvaluator()
        self._initialized = False

    def _get_client_for_agent(self, agent_config: Dict[str, Any]) -> Any:
        """
        Get the appropriate chat client for an agent.
        
        Args:
            agent_config: Agent configuration that may include a "model" key
            
        Returns:
            Chat client for this agent
        """
        agent_model = agent_config.get("model")
        
        if agent_model and self._model_registry:
            try:
                from src.models.providers import ModelFactory
                model_config = self._model_registry.get_provider(agent_model)
                client = ModelFactory.create_client(model_config)
                logger.debug(
                    "Created client for agent with specific model",
                    agent_name=agent_config.get("name"),
                    model=agent_model,
                )
                return client
            except KeyError:
                logger.warning(
                    "Model not found in registry, using default",
                    agent_name=agent_config.get("name"),
                    requested_model=agent_model,
                )
        
        return self._chat_client
        
    def load_workflows(self, workflow_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Load and initialize workflows from configuration.
        
        Args:
            workflow_configs: List of workflow configurations, each containing:
                - name: Friendly name for the workflow
                - type: "sequential" or "custom"
                - enabled: Whether this workflow is enabled (default: true)
                
                For sequential type:
                - agents: List of agent definitions with name and instructions
                
                For custom type:
                - agents: List of agent definitions
                - edges: List of edge definitions (from, to, optional condition)
                - start: Name of the starting agent
                
        Returns:
            Dict mapping workflow names to workflow agent instances
        """
        if not WORKFLOW_AVAILABLE:
            logger.warning(
                "Workflow support not available. Install agent-framework with workflow support."
            )
            return {}
        
        if not workflow_configs:
            logger.debug("No workflows configured")
            return {}
        
        for config in workflow_configs:
            # Skip disabled workflows
            if not config.get("enabled", True):
                logger.debug("Skipping disabled workflow", name=config.get("name"))
                continue
                
            try:
                workflow_agent = self._create_workflow(config)
                if workflow_agent:
                    name = config.get("name", "unnamed-workflow")
                    self._workflow_agents[name] = workflow_agent
                    logger.info(
                        "Loaded workflow",
                        name=name,
                        type=config.get("type")
                    )
            except Exception as e:
                logger.error(
                    "Failed to load workflow",
                    name=config.get("name"),
                    error=str(e)
                )
        
        self._initialized = True
        logger.info("Workflows loaded", count=len(self._workflow_agents))
        return self._workflow_agents
    
    def _create_workflow(self, config: Dict[str, Any]) -> Optional[Any]:
        """Create a workflow based on configuration."""
        workflow_type = config.get("type", "").lower()
        name = config.get("name", "unnamed-workflow")
        
        if workflow_type == "sequential":
            return self._create_sequential_workflow(config)
        elif workflow_type == "custom":
            return self._create_custom_workflow(config)
        else:
            logger.error("Unknown workflow type", name=name, type=workflow_type)
            return None
    
    def _create_sequential_workflow(self, config: Dict[str, Any]) -> Any:
        """
        Create a sequential workflow where agents execute in order.
        
        Args:
            config: Workflow configuration containing:
                - name: Workflow name
                - agents: List of agent definitions
                    - name: Agent name
                    - instructions: Agent system prompt
                    - model: Optional model name for per-agent model selection
                    
        Returns:
            Workflow agent instance
        """
        agents_config = config.get("agents", [])
        if not agents_config:
            raise ValueError(f"Workflow '{config.get('name')}' requires 'agents' list")
        
        # Create agents with per-agent model support
        agents = []
        for agent_config in agents_config:
            # Get appropriate client (may be model-specific)
            client = self._get_client_for_agent(agent_config)
            
            agent = ChatAgent(
                name=agent_config.get("name", f"Agent-{len(agents)}"),
                instructions=agent_config.get("instructions", "You are a helpful assistant."),
                chat_client=client,
            )
            agents.append(agent)
            
            model_used = agent_config.get("model", "default")
            logger.debug(
                "Created agent for workflow",
                agent_name=agent.name,
                model=model_used
            )
        
        # Build sequential workflow
        workflow = (
            SequentialBuilder()
            .participants(agents)
            .build()
        )
        
        # Convert to workflow agent
        workflow_agent = workflow.as_agent(name=config.get("name", "Sequential Workflow"))
        
        logger.info(
            "Created sequential workflow",
            name=config.get("name"),
            agent_count=len(agents)
        )
        
        return workflow_agent
    
    def _create_custom_workflow(self, config: Dict[str, Any]) -> Any:
        """
        Create a custom workflow with user-defined edges.

        Args:
            config: Workflow configuration containing:
                - name: Workflow name
                - agents: List of agent definitions
                - edges: List of edge definitions (from, to, optional condition, optional priority)
                - start: Name of starting agent

        Edge configuration examples:
            # Simple edge (always taken)
            [[agent.workflows.edges]]
            from = "Triage"
            to = "TechSupport"

            # Conditional edge (based on agent output)
            [[agent.workflows.edges]]
            from = "Triage"
            to = "TechSupport"
            condition = "output.category == 'technical'"
            priority = 1

            # Multiple conditions with AND/OR
            [[agent.workflows.edges]]
            from = "Triage"
            to = "Escalation"
            condition = "output.priority == 'high' and output.category == 'billing'"

        Returns:
            Workflow agent instance
        """
        workflow_name = config.get("name", "unnamed-workflow")
        agents_config = config.get("agents", [])
        edges_config = config.get("edges", [])
        start_agent = config.get("start")

        if not agents_config:
            raise ValueError(f"Workflow '{workflow_name}' requires 'agents' list")
        if not start_agent:
            raise ValueError(f"Workflow '{workflow_name}' requires 'start' agent name")

        # Create agents and store by name, with per-agent model support
        agents_by_name: Dict[str, Any] = {}
        for agent_config in agents_config:
            agent_name = agent_config.get("name")
            if not agent_name:
                raise ValueError("Each agent in workflow must have a 'name'")

            # Get appropriate client (may be model-specific)
            client = self._get_client_for_agent(agent_config)

            agent = ChatAgent(
                name=agent_name,
                instructions=agent_config.get("instructions", "You are a helpful assistant."),
                chat_client=client,
            )
            agents_by_name[agent_name] = agent
            
            model_used = agent_config.get("model", "default")
            logger.debug(
                "Created agent for workflow",
                agent_name=agent_name,
                model=model_used
            )

        # Validate start agent exists
        if start_agent not in agents_by_name:
            raise ValueError(f"Start agent '{start_agent}' not found in agents list")

        # Parse and store conditional edges
        conditional_edges: List[ConditionalEdge] = []
        for edge in edges_config:
            from_agent = edge.get("from")
            to_agent = edge.get("to")
            condition = edge.get("condition")
            priority = edge.get("priority", 0)

            if from_agent not in agents_by_name:
                raise ValueError(f"Edge 'from' agent '{from_agent}' not found")
            if to_agent not in agents_by_name:
                raise ValueError(f"Edge 'to' agent '{to_agent}' not found")

            conditional_edge = ConditionalEdge(
                from_agent=from_agent,
                to_agent=to_agent,
                condition=condition,
                priority=priority
            )
            conditional_edges.append(conditional_edge)

            if condition:
                logger.debug(
                    "Added conditional edge",
                    from_agent=from_agent,
                    to_agent=to_agent,
                    condition=condition,
                    priority=priority
                )
            else:
                logger.debug("Added edge", from_agent=from_agent, to_agent=to_agent)

        # Store conditional edges for runtime routing
        self._workflow_edges[workflow_name] = sorted(
            conditional_edges,
            key=lambda e: e.priority,
            reverse=True  # Higher priority first
        )

        # Build workflow with standard edges
        builder = WorkflowBuilder()
        builder.set_start_executor(agents_by_name[start_agent])

        # Add edges to the builder
        # Note: Conditional routing is handled at runtime via evaluate_next_agent
        for edge in conditional_edges:
            builder.add_edge(
                agents_by_name[edge.from_agent],
                agents_by_name[edge.to_agent]
            )

        workflow = builder.build()

        # Convert to workflow agent
        workflow_agent = workflow.as_agent(name=workflow_name)

        # Store the agents map for runtime routing
        self._workflows[workflow_name] = {
            "agents": agents_by_name,
            "edges": conditional_edges,
            "start": start_agent
        }

        logger.info(
            "Created custom workflow",
            name=workflow_name,
            agent_count=len(agents_by_name),
            edge_count=len(conditional_edges),
            conditional_edges=sum(1 for e in conditional_edges if e.condition)
        )

        return workflow_agent

    def evaluate_next_agent(
        self,
        workflow_name: str,
        current_agent: str,
        agent_output: Union[str, Dict[str, Any]]
    ) -> Optional[str]:
        """
        Evaluate which agent should execute next based on conditions.

        Args:
            workflow_name: Name of the workflow
            current_agent: Name of the agent that just executed
            agent_output: Output from the current agent

        Returns:
            Name of the next agent to execute, or None if no matching edge
        """
        edges = self._workflow_edges.get(workflow_name, [])

        # Find edges from the current agent
        outgoing_edges = [e for e in edges if e.from_agent == current_agent]

        if not outgoing_edges:
            logger.debug("No outgoing edges from agent", agent=current_agent)
            return None

        # Evaluate conditions in priority order
        for edge in outgoing_edges:
            if not edge.condition:
                # Unconditional edge - use as default/fallback
                logger.debug(
                    "Taking unconditional edge",
                    from_agent=current_agent,
                    to_agent=edge.to_agent
                )
                return edge.to_agent

            # Evaluate condition
            if self._condition_evaluator.evaluate(edge.condition, agent_output):
                logger.info(
                    "Condition matched, routing to agent",
                    from_agent=current_agent,
                    to_agent=edge.to_agent,
                    condition=edge.condition
                )
                return edge.to_agent

        # No condition matched - check for default edge (no condition)
        default_edge = next(
            (e for e in outgoing_edges if not e.condition),
            None
        )
        if default_edge:
            logger.debug(
                "Using default edge",
                from_agent=current_agent,
                to_agent=default_edge.to_agent
            )
            return default_edge.to_agent

        logger.warning(
            "No matching edge found",
            workflow=workflow_name,
            agent=current_agent
        )
        return None

    def get_workflow_info(self, workflow_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a workflow.

        Args:
            workflow_name: Name of the workflow

        Returns:
            Dict with workflow details or None if not found
        """
        if workflow_name not in self._workflows:
            return None

        workflow_data = self._workflows[workflow_name]
        edges = self._workflow_edges.get(workflow_name, [])

        return {
            "name": workflow_name,
            "agents": list(workflow_data["agents"].keys()),
            "start": workflow_data["start"],
            "edges": [
                {
                    "from": e.from_agent,
                    "to": e.to_agent,
                    "condition": e.condition,
                    "priority": e.priority
                }
                for e in edges
            ],
            "conditional_edge_count": sum(1 for e in edges if e.condition)
        }
    
    def get_workflow(self, name: str) -> Optional[Any]:
        """Get a workflow agent by name."""
        return self._workflow_agents.get(name)
    
    @property
    def workflows(self) -> Dict[str, Any]:
        """Get all loaded workflow agents."""
        return self._workflow_agents
    
    @property
    def workflow_names(self) -> List[str]:
        """Get names of all loaded workflows."""
        return list(self._workflow_agents.keys())


def parse_workflow_configs(config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse workflow configurations from agent config.
    
    Supports two formats in TOML:
    
    1. Array format (recommended for multiple workflows):
        [[agent.workflows]]
        name = "content-pipeline"
        type = "sequential"
        
        [[agent.workflows.agents]]
        name = "Researcher"
        instructions = "Research the topic..."
        
        [[agent.workflows.agents]]
        name = "Writer"
        instructions = "Write content based on research..."
    
    2. Table format (for named workflows):
        [agent.workflows.content-pipeline]
        type = "sequential"
        agents = [
            { name = "Researcher", instructions = "..." },
            { name = "Writer", instructions = "..." }
        ]
    
    Args:
        config_dict: The agent configuration dictionary
        
    Returns:
        List of workflow configuration dictionaries
    """
    workflow_config = config_dict.get("workflows", {})
    
    # If it's a list, return as-is
    if isinstance(workflow_config, list):
        return workflow_config
    
    # If it's a dict, convert to list format
    if isinstance(workflow_config, dict):
        workflow_list = []
        for name, settings in workflow_config.items():
            if isinstance(settings, dict):
                # Add name from key if not specified
                if "name" not in settings:
                    settings["name"] = name
                workflow_list.append(settings)
        return workflow_list
    
    return []
