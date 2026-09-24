class UserError(Exception):
    """A problem the user can fix (shown as-is in the UI, returned as HTTP 400)."""


class NotFound(Exception):
    pass


class Cancelled(Exception):
    pass
