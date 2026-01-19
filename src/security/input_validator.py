"""
Input Validation for the AI Assistant.

Provides:
- Prompt injection detection
- Input sanitization
- PII detection
- Content length validation
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        validation_type: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.validation_type = validation_type
        self.details = details or {}


@dataclass
class ValidationConfig:
    """Configuration for input validation."""
    # Length limits
    max_question_length: int = 32000
    max_tool_param_length: int = 10000

    # Prompt injection
    block_prompt_injection: bool = True
    injection_patterns: List[str] = field(default_factory=list)

    # PII handling
    block_pii: bool = False
    redact_pii: bool = False

    # Content filtering
    blocked_patterns: List[str] = field(default_factory=list)
    allowed_languages: Optional[List[str]] = None  # None = all allowed


# Default prompt injection patterns
DEFAULT_INJECTION_PATTERNS = [
    # System prompt manipulation
    r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
    r"forget\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*you\s+are",
    r"<\s*system\s*>",
    r"\[\s*system\s*\]",
    r"override\s+(system|instructions?|rules?)",

    # Role manipulation
    r"pretend\s+you\s+are",
    r"act\s+as\s+(if\s+you\s+are\s+)?a",
    r"roleplay\s+as",
    r"you\s+are\s+now\s+a",
    r"from\s+now\s+on\s+you\s+are",

    # Jailbreak attempts
    r"do\s+anything\s+now",
    r"dan\s+mode",
    r"developer\s+mode",
    r"jailbreak",
    r"bypass\s+(safety|filter|restriction)",

    # Instruction extraction
    r"(print|show|reveal|display|output)\s+(your\s+)?(system\s+)?(prompt|instructions?)",
    r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?)",

    # Code injection markers (in non-code contexts)
    r"```\s*(python|bash|shell|javascript|js)\s*\n\s*(import\s+os|subprocess|eval|exec)",
]

# PII patterns (production-ready with proper validation)
# Note: For enterprise deployments, consider using python-pii-detect or presidio library
PII_PATTERNS = {
    # Email addresses
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    # US phone numbers (various formats)
    "phone": r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    # US Social Security Numbers
    "ssn": r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
    # Credit card numbers (major card types with Luhn-compatible patterns)
    "credit_card": r"\b(?:4\d{3}|5[1-5]\d{2}|6011|3[47]\d{2})[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b",
    # IPv4 addresses (with proper octet bounds 0-255)
    "ip_address": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
    # US Passport numbers (9 alphanumeric characters)
    "passport": r"\b[A-Z]?\d{8,9}\b",
    # US Driver's License (varies by state, common patterns)
    "drivers_license": r"\b[A-Z]{1,2}\d{5,8}\b",
    # Bank account numbers (US routing + account pattern)
    "bank_account": r"\b\d{9}[-.\s]?\d{8,17}\b",
    # IBAN (International Bank Account Number)
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
    # AWS Access Keys
    "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
    # AWS Secret Keys (40 character base64)
    "aws_secret_key": r"\b[A-Za-z0-9/+=]{40}\b",
    # Azure Connection Strings
    "azure_connection_string": r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+",
}


class InputValidator:
    """
    Validates and sanitizes user input.

    Provides protection against:
    - Prompt injection attacks
    - PII exposure
    - Malicious content
    - Oversized inputs
    """

    def __init__(self, config: ValidationConfig):
        """
        Initialize input validator.

        Args:
            config: ValidationConfig with validation settings
        """
        self.config = config

        # Compile injection patterns
        patterns = config.injection_patterns or DEFAULT_INJECTION_PATTERNS
        self._injection_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in patterns
        ]

        # Compile PII patterns
        self._pii_patterns = {
            name: re.compile(pattern)
            for name, pattern in PII_PATTERNS.items()
        }

        # Compile blocked patterns
        self._blocked_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in config.blocked_patterns
        ]

        logger.info(
            "Input validator initialized",
            injection_detection=config.block_prompt_injection,
            pii_detection=config.block_pii or config.redact_pii,
            blocked_patterns=len(config.blocked_patterns)
        )

    def validate(
        self,
        text: str,
        context: str = "question"
    ) -> str:
        """
        Validate and potentially sanitize input text.

        Args:
            text: Input text to validate
            context: Context of the input (e.g., "question", "tool_param")

        Returns:
            Validated (and possibly sanitized) text

        Raises:
            ValidationError: If validation fails
        """
        # Check length
        max_length = (
            self.config.max_question_length
            if context == "question"
            else self.config.max_tool_param_length
        )

        if len(text) > max_length:
            raise ValidationError(
                f"Input exceeds maximum length ({len(text)} > {max_length})",
                validation_type="length",
                details={"length": len(text), "max": max_length}
            )

        # Check for prompt injection
        if self.config.block_prompt_injection:
            injection_match = self._detect_prompt_injection(text)
            if injection_match:
                logger.warning(
                    "Prompt injection detected",
                    pattern=injection_match,
                    context=context
                )
                raise ValidationError(
                    "Input contains potentially harmful content",
                    validation_type="prompt_injection",
                    details={"pattern": injection_match}
                )

        # Check blocked patterns
        for pattern in self._blocked_patterns:
            if pattern.search(text):
                raise ValidationError(
                    "Input contains blocked content",
                    validation_type="blocked_content"
                )

        # Handle PII
        if self.config.block_pii:
            pii_found = self._detect_pii(text)
            if pii_found:
                raise ValidationError(
                    f"Input contains PII: {', '.join(pii_found)}",
                    validation_type="pii",
                    details={"pii_types": list(pii_found)}
                )

        if self.config.redact_pii:
            text = self._redact_pii(text)

        return text

    def _detect_prompt_injection(self, text: str) -> Optional[str]:
        """
        Detect potential prompt injection attempts.

        Args:
            text: Input text to check

        Returns:
            Matched pattern string if injection detected, None otherwise
        """
        for pattern in self._injection_patterns:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def _detect_pii(self, text: str) -> Set[str]:
        """
        Detect PII in text.

        Args:
            text: Input text to check

        Returns:
            Set of PII types found
        """
        found = set()
        for pii_type, pattern in self._pii_patterns.items():
            if pattern.search(text):
                found.add(pii_type)
        return found

    def _redact_pii(self, text: str) -> str:
        """
        Redact PII from text.

        Args:
            text: Input text to redact

        Returns:
            Text with PII redacted
        """
        for pii_type, pattern in self._pii_patterns.items():
            text = pattern.sub(f"[REDACTED-{pii_type.upper()}]", text)
        return text

    def validate_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        allowed_tools: Optional[List[str]] = None,
        blocked_tools: Optional[List[str]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Validate a tool call.

        Args:
            tool_name: Name of the tool being called
            parameters: Tool parameters
            allowed_tools: Whitelist of allowed tools (None = all allowed)
            blocked_tools: Blacklist of blocked tools

        Returns:
            Tuple of (validated tool_name, validated parameters)

        Raises:
            ValidationError: If validation fails
        """
        # Check tool whitelist
        if allowed_tools is not None and tool_name not in allowed_tools:
            raise ValidationError(
                f"Tool '{tool_name}' is not allowed",
                validation_type="tool_not_allowed",
                details={"tool": tool_name, "allowed": allowed_tools}
            )

        # Check tool blacklist
        if blocked_tools and tool_name in blocked_tools:
            raise ValidationError(
                f"Tool '{tool_name}' is blocked",
                validation_type="tool_blocked",
                details={"tool": tool_name}
            )

        # Validate parameters
        validated_params = {}
        for key, value in parameters.items():
            if isinstance(value, str):
                validated_params[key] = self.validate(value, context="tool_param")
            else:
                validated_params[key] = value

        return tool_name, validated_params


def detect_prompt_injection(text: str) -> bool:
    """
    Convenience function to detect prompt injection.

    Args:
        text: Input text to check

    Returns:
        True if potential injection detected
    """
    for pattern in DEFAULT_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def sanitize_input(
    text: str,
    max_length: int = 32000,
    redact_pii: bool = False
) -> str:
    """
    Convenience function to sanitize input.

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length
        redact_pii: Whether to redact PII

    Returns:
        Sanitized text
    """
    # Truncate if needed
    if len(text) > max_length:
        text = text[:max_length]

    # Redact PII if requested
    if redact_pii:
        for pii_type, pattern in PII_PATTERNS.items():
            text = re.sub(pattern, f"[REDACTED-{pii_type.upper()}]", text)

    return text
