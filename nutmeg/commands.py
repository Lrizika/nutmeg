try:
	from .event_builder import EventBuilder
	from .utils import descendants
except ImportError:
	from event_builder import EventBuilder
	from utils import descendants

import logging
command_logger = logging.getLogger('root')

class Command:
	command = ''
	aliases = []
	def __init__(self, controller, args):
		self.result = {}
		command_logger.info('Executing command %(command)s with args: %(args)s' %
			{'command': str(self.command),
			'args': str(args)})
		try:
			self.validate(args)
			out = self.execute(controller, args)
			if isinstance(out, dict):
				self.result = out
			else:
				self.result = EventBuilder.commandOutput(self.command, out)
		except Exception as e:
			self.result = EventBuilder.commandError(self.command, str(e))
	def validate(self, args):
		pass
	def help(self) -> str:
		return('There\'s no help message for this command.')
	def execute(self, controller, args):
		raise NotImplementedError

class Join(Command):
	command = 'join'
	aliases = ['move']
	def validate(self, args):
		if len(args) != 1:
			raise IndexError('Join requires exactly one argument (destination room).')
	@staticmethod
	def help():
		return("""Usage: /join #room:matrix.homeserver.tld
			Join or move to another room.
			Aliases: /move""")
	def execute(self, controller, args):
		controller.stateManager.joinRoom(args[0])
		return('Joined '+args[0])

class Whoami(Command):
	command = 'whoami'
	def validate(self, args):
		if len(args) != 0:
			raise IndexError('Whoami requires zero arguments.')
	@staticmethod
	def help():
		return("""Usage: /whoami
			Print the current logged in client.""")
	def execute(self, controller, args):
		return(controller.client.user_id)

class Help(Command):
	command = 'help'
	aliases = ['h', '?']
	def validate(self, args):
		if len(args) > 1:
			raise IndexError('Help requires no more than one argument (hint: try /help).')
	@staticmethod
	def help():
		return("""Usage: /help [command]
			Print help about the given command.
			Aliases: /h, /?""")
	def execute(self, controller, args):
		if len(args) == 0:
			command = self.command
		else:
			command = args[0]
		return(CommandSelector.commands[command].help())

class CommandSelector:
	commands = {descendant.command:descendant for descendant in descendants(Command)}
	commands.update({alias:descendant for descendant in descendants(Command) for alias in descendant.aliases})
	command_logger.info('Loaded commands, CommandSelector.commands = '+str(commands))
