"""
Tests for the workflow module.

Tests conditional routing and workflow management.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestConditionEvaluator:
    """Tests for ConditionEvaluator."""

    def test_evaluator_initialization(self):
        """Test condition evaluator initialization."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()
        assert evaluator is not None

    def test_evaluate_empty_condition(self):
        """Test that empty condition returns True."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()
        result = evaluator.evaluate("", {"text": "hello"})
        assert result is True

    def test_evaluate_string_equality(self):
        """Test string equality condition."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"category": "technical"}
        assert evaluator.evaluate("output.category == 'technical'", output) is True
        assert evaluator.evaluate("output.category == 'billing'", output) is False

    def test_evaluate_numeric_comparison(self):
        """Test numeric comparison conditions."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"confidence": 0.85}
        assert evaluator.evaluate("output.confidence > 0.8", output) is True
        assert evaluator.evaluate("output.confidence < 0.8", output) is False
        assert evaluator.evaluate("output.confidence >= 0.85", output) is True
        assert evaluator.evaluate("output.confidence <= 0.9", output) is True

    def test_evaluate_in_operator(self):
        """Test 'in' operator conditions."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"priority": "high"}
        assert evaluator.evaluate("output.priority in ['high', 'critical']", output) is True
        assert evaluator.evaluate("output.priority in ['low', 'medium']", output) is False

    def test_evaluate_contains_operator(self):
        """Test 'contains' operator."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"text": "This is an error message"}
        assert evaluator.evaluate("output.text contains 'error'", output) is True
        assert evaluator.evaluate("output.text contains 'success'", output) is False

    def test_evaluate_and_condition(self):
        """Test AND logical condition."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"category": "billing", "priority": "high"}
        assert evaluator.evaluate(
            "output.category == 'billing' and output.priority == 'high'",
            output
        ) is True
        assert evaluator.evaluate(
            "output.category == 'billing' and output.priority == 'low'",
            output
        ) is False

    def test_evaluate_or_condition(self):
        """Test OR logical condition."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"category": "technical"}
        assert evaluator.evaluate(
            "output.category == 'technical' or output.category == 'billing'",
            output
        ) is True
        assert evaluator.evaluate(
            "output.category == 'sales' or output.category == 'billing'",
            output
        ) is False

    def test_evaluate_not_equal(self):
        """Test not equal condition."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"status": "pending"}
        assert evaluator.evaluate("output.status != 'completed'", output) is True
        assert evaluator.evaluate("output.status != 'pending'", output) is False

    def test_evaluate_nested_field(self):
        """Test nested field access."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"user": {"role": "admin", "level": 5}}
        assert evaluator.evaluate("output.user.role == 'admin'", output) is True
        assert evaluator.evaluate("output.user.level > 3", output) is True

    def test_evaluate_string_output(self):
        """Test evaluation with string output."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        # String output should be wrapped in dict
        output = "This is a text response"
        assert evaluator.evaluate("error", output) is False
        assert evaluator.evaluate("text", output) is True

    def test_evaluate_json_string_output(self):
        """Test evaluation with JSON string output."""
        import json
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = json.dumps({"category": "support", "score": 0.9})
        assert evaluator.evaluate("output.category == 'support'", output) is True
        assert evaluator.evaluate("output.score > 0.8", output) is True

    def test_evaluate_boolean_values(self):
        """Test boolean value conditions."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"is_urgent": True, "is_resolved": False}
        assert evaluator.evaluate("output.is_urgent == true", output) is True
        assert evaluator.evaluate("output.is_resolved == false", output) is True

    def test_evaluate_null_values(self):
        """Test null value conditions."""
        from src.loaders.workflows import ConditionEvaluator

        evaluator = ConditionEvaluator()

        output = {"data": None, "value": "exists"}
        assert evaluator.evaluate("output.data == null", output) is True
        assert evaluator.evaluate("output.value != null", output) is True


class TestConditionalEdge:
    """Tests for ConditionalEdge."""

    def test_edge_creation(self):
        """Test conditional edge creation."""
        from src.loaders.workflows import ConditionalEdge

        edge = ConditionalEdge(
            from_agent="Triage",
            to_agent="TechSupport",
            condition="output.category == 'technical'",
            priority=1
        )

        assert edge.from_agent == "Triage"
        assert edge.to_agent == "TechSupport"
        assert edge.condition == "output.category == 'technical'"
        assert edge.priority == 1

    def test_edge_without_condition(self):
        """Test edge without condition (default edge)."""
        from src.loaders.workflows import ConditionalEdge

        edge = ConditionalEdge(
            from_agent="Triage",
            to_agent="Default"
        )

        assert edge.condition is None
        assert edge.priority == 0

    def test_edge_repr(self):
        """Test edge string representation."""
        from src.loaders.workflows import ConditionalEdge

        edge = ConditionalEdge(
            from_agent="A",
            to_agent="B",
            condition="test"
        )

        repr_str = repr(edge)
        assert "A" in repr_str
        assert "B" in repr_str


class TestWorkflowManager:
    """Tests for WorkflowManager."""

    def test_workflow_manager_initialization(self):
        """Test workflow manager initialization."""
        from src.loaders.workflows import WorkflowManager

        mock_client = MagicMock()
        manager = WorkflowManager(mock_client)

        assert manager is not None
        assert manager._condition_evaluator is not None

    def test_evaluate_next_agent_no_edges(self):
        """Test evaluate_next_agent with no edges."""
        from src.loaders.workflows import WorkflowManager

        mock_client = MagicMock()
        manager = WorkflowManager(mock_client)

        result = manager.evaluate_next_agent(
            "test_workflow",
            "current_agent",
            {"text": "output"}
        )

        assert result is None

    def test_evaluate_next_agent_unconditional(self):
        """Test evaluate_next_agent with unconditional edge."""
        from src.loaders.workflows import WorkflowManager, ConditionalEdge

        mock_client = MagicMock()
        manager = WorkflowManager(mock_client)

        # Manually add edges for testing
        manager._workflow_edges["test_workflow"] = [
            ConditionalEdge("A", "B", None, 0)
        ]

        result = manager.evaluate_next_agent(
            "test_workflow",
            "A",
            {"text": "output"}
        )

        assert result == "B"

    def test_evaluate_next_agent_conditional_match(self):
        """Test evaluate_next_agent with matching condition."""
        from src.loaders.workflows import WorkflowManager, ConditionalEdge

        mock_client = MagicMock()
        manager = WorkflowManager(mock_client)

        manager._workflow_edges["test_workflow"] = [
            ConditionalEdge("Triage", "TechSupport", "output.category == 'technical'", 1),
            ConditionalEdge("Triage", "Billing", "output.category == 'billing'", 1),
            ConditionalEdge("Triage", "Default", None, 0),  # Default fallback
        ]

        result = manager.evaluate_next_agent(
            "test_workflow",
            "Triage",
            {"category": "technical"}
        )

        assert result == "TechSupport"

    def test_evaluate_next_agent_fallback(self):
        """Test evaluate_next_agent falls back to default edge."""
        from src.loaders.workflows import WorkflowManager, ConditionalEdge

        mock_client = MagicMock()
        manager = WorkflowManager(mock_client)

        manager._workflow_edges["test_workflow"] = [
            ConditionalEdge("Triage", "TechSupport", "output.category == 'technical'", 1),
            ConditionalEdge("Triage", "Default", None, 0),
        ]

        result = manager.evaluate_next_agent(
            "test_workflow",
            "Triage",
            {"category": "unknown"}  # Doesn't match any condition
        )

        assert result == "Default"

    def test_get_workflow_info(self):
        """Test getting workflow information."""
        from src.loaders.workflows import WorkflowManager, ConditionalEdge

        mock_client = MagicMock()
        manager = WorkflowManager(mock_client)

        manager._workflows["test_workflow"] = {
            "agents": {"A": MagicMock(), "B": MagicMock()},
            "edges": [],
            "start": "A"
        }
        manager._workflow_edges["test_workflow"] = [
            ConditionalEdge("A", "B", "output.done == true", 1)
        ]

        info = manager.get_workflow_info("test_workflow")

        assert info is not None
        assert info["name"] == "test_workflow"
        assert "A" in info["agents"]
        assert "B" in info["agents"]
        assert info["start"] == "A"
        assert info["conditional_edge_count"] == 1


class TestParseWorkflowConfigs:
    """Tests for parse_workflow_configs function."""

    def test_parse_list_format(self):
        """Test parsing workflow configs in list format."""
        from src.loaders.workflows import parse_workflow_configs

        config = {
            "workflows": [
                {"name": "workflow1", "type": "sequential"},
                {"name": "workflow2", "type": "custom"}
            ]
        }

        result = parse_workflow_configs(config)
        assert len(result) == 2
        assert result[0]["name"] == "workflow1"

    def test_parse_dict_format(self):
        """Test parsing workflow configs in dict format."""
        from src.loaders.workflows import parse_workflow_configs

        config = {
            "workflows": {
                "workflow1": {"type": "sequential"},
                "workflow2": {"type": "custom"}
            }
        }

        result = parse_workflow_configs(config)
        assert len(result) == 2

    def test_parse_empty_config(self):
        """Test parsing empty workflow config."""
        from src.loaders.workflows import parse_workflow_configs

        result = parse_workflow_configs({})
        assert result == []
