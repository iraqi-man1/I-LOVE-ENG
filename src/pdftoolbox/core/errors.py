class ToolError(Exception):
    """An error with a message that is safe to show to the user."""


class Cancelled(Exception):
    """Raised inside a job when the user cancels it."""


class PasswordRequired(ToolError):
    def __init__(self, path):
        super().__init__(f"“{path}” is password protected. Enter its password and try again.")
        self.path = path
