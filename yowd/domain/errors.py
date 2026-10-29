"""Exception hierarchy used by the domain and application layers.

Every exception carries a message that tells the user what to do next,
as required by usability requirement QU7 ("explain what the user should
do rather than simply indicating that the action has failed").
"""


class DmsError(Exception):
    """Base class for all expected (business) errors in the system."""


class ValidationError(DmsError):
    """Raised when user-supplied data is invalid (wrong type, range...)."""


class BusinessRuleError(DmsError):
    """Raised when valid data breaks a business rule.

    Examples are an expired quote being accepted or a status change that
    the configured transition table does not allow.
    """


class AuthorisationError(DmsError):
    """Raised when the acting user's role may not perform an action."""


class NotFoundError(DmsError):
    """Raised when a record (customer, delivery...) cannot be found."""
