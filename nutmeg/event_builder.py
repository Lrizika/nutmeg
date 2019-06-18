try:
	from .utils import nowToTs
except ImportError:
	from utils import nowToTs

class EventBuilder:
	@staticmethod
	def commandHelp(command:str, message:str) -> dict:
		event = {
			'type': 'n.output.help',
			'source': 'Nutmeg',
			'origin_server_ts': nowToTs(),
			'content': {
				'command': command,
				'message': message
			}
		}
		return(event)

	@staticmethod
	def commandOutput(command:str, message:str) -> dict:
		event = {
			'type': 'n.output.command',
			'source': 'Nutmeg',
			'origin_server_ts': nowToTs(),
			'content': {
				'command': command,
				'message': message
			}
		}
		return(event)

	@staticmethod
	def commandError(command:str, message:str) -> dict:
		event = {
			'type': 'n.output.error',
			'source': 'Nutmeg',
			'origin_server_ts': nowToTs(),
			'content': {
				'command': command,
				'message': message
			}
		}
		return(event)
