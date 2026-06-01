class ParserError(Exception):
    """Base parser error."""


class ConfigError(ParserError):
    """Raised when the parser config is invalid."""


class MetadataError(ParserError):
    """Raised when metadata loading fails."""


class SchemaValidationError(ParserError):
    """Raised when a page input schema is invalid."""
