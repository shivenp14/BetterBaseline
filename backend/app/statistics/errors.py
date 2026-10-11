"""Transport-independent statistical domain errors."""


class StatisticalInputError(ValueError):
    """An input failure that API adapters can map to a structured response."""

    def __init__(self, message: str, *, field: str, code: str = "INVALID_MODEL_INPUT"):
        super().__init__(message)
        self.code = code
        self.field = field
