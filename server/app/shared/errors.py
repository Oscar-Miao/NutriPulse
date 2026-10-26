class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def require(condition: bool, message: str, code: str = "VALIDATION_ERROR") -> None:
    if not condition:
        raise ApiError(code, message)
