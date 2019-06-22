class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class MissingEventIdError(Error):
	"""Raised if an event does not have an event_id field."""
	pass

class CommandError(Error):
	"""Base class for exceptions relating to commands."""
	pass

class MalformedCommandError(CommandError):
	"""Raised when a command is sent to the parser with an unexpected structure."""
	pass


class StateError(Error):
	"""Base class for exceptions relating to state."""
	pass

class InvalidModeError(StateError):
	"""Raised when something tries to enter an invalid mode."""
	pass

class WrongModeError(StateError):
	"""
	Raised when the input.InputController processes input in the wrong mode.
		E.G. receives edit input for processing while in visual mode.
		This should never happen.
	"""
	pass

