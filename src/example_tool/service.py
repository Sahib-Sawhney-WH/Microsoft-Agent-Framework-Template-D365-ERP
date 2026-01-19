"""
Example Tool Service

A template service demonstrating how to implement tools for the AI Assistant.
Copy this file as a starting point for your own tools.

NAMING CONVENTION
=================
Tool config file: config/tools/<name>.json
Service file:     src/<name>/service.py
Service class:    <Name>Service (PascalCase + "Service")

Example:
  config/tools/weather.json  →  src/weather/service.py  →  WeatherService
  config/tools/database.json →  src/database/service.py →  DatabaseService
"""

from typing import Any, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class ExampleToolService:
    """
    Example service demonstrating the tool interface.
    
    All services must implement:
    - __init__(): Initialize any resources, connections, API clients
    - run(tool_call: Dict[str, Any]) -> str: Execute the tool logic
    - close() (optional): Clean up resources
    
    The run() method receives parameters from the LLM via the tool_call dict.
    Parameters match what's defined in the tool's JSON config file.
    """

    def __init__(self, prefix: str = "[Example]"):
        """
        Initialize the service.
        
        Args:
            prefix: String to prepend to responses (example config parameter)
        """
        self.prefix = prefix
        logger.info("Initialized ExampleToolService", prefix=prefix)

    def run(self, tool_call: Dict[str, Any]) -> str:
        """
        Execute the tool logic.
        
        This method is called by the agent framework when the LLM decides
        to use this tool. The tool_call dict contains parameters as defined
        in the tool's JSON config file.
        
        Args:
            tool_call: Dictionary containing parameters from the LLM:
                - message (str): The message to process
                - uppercase (bool, optional): Convert to uppercase
        
        Returns:
            str: The result to return to the LLM for further reasoning
        """
        try:
            # Extract parameters from tool_call
            message = tool_call.get("message", "")
            uppercase = tool_call.get("uppercase", False)
            
            logger.info(
                "Processing example tool call",
                message_preview=message[:50] if message else None,
                uppercase=uppercase
            )
            
            # Validate required parameters
            if not message:
                return "Error: 'message' parameter is required"
            
            # Process the message
            result = message
            if uppercase:
                result = result.upper()
            
            # Format response
            response = f"{self.prefix} Processed message: {result}"
            
            logger.info("Example tool completed successfully")
            return response
            
        except Exception as e:
            logger.error("Example tool failed", error=str(e))
            return f"Error: {str(e)}"

    def close(self) -> None:
        """
        Clean up resources.
        
        Called when the AI Assistant shuts down.
        Use this for closing database connections, API clients, etc.
        """
        logger.info("ExampleToolService closed")


# Singleton instance (optional pattern for expensive resources)
_service: Optional[ExampleToolService] = None


def get_example_tool_service() -> ExampleToolService:
    """
    Factory function to get or create service instance.
    
    This function is automatically discovered by the tool loader.
    Convention: get_<tool_name>_service()
    
    Use this pattern when:
    - Service initialization is expensive
    - You need to share state across tool calls
    - You want to customize initialization based on config
    
    Returns:
        ExampleToolService: Service instance
    """
    global _service
    
    if _service is None:
        # You can load tool-specific config here
        # from src.config import get_config
        # config = get_config()
        # tool_config = config.get_tool_config("example_tool")
        
        _service = ExampleToolService(prefix="[Example Tool]")
    
    return _service
