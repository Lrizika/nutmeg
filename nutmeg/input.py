try:
	from .utils import descendants
	from .commands import Command, CommandSelector
	from .errors import InvalidModeError, WrongModeError, MalformedCommandError
	from .event_builder import EventBuilder
	from .constants import MODES, MTYPE
except ImportError:
	from utils import descendants
	from commands import Command, CommandSelector
	from errors import InvalidModeError, WrongModeError, MalformedCommandError
	from event_builder import EventBuilder
	from constants import MODES, MTYPE
import curses

import logging
parse_logger = logging.getLogger('root')

class Parser:
	def __init__(self, 
			controller, 
			mode:MODES = MODES.EDIT, 
			stateManager = None,
			displayController = None):
		
		self.listening = False

		self.controller = controller
		self.mode = mode

		if stateManager is None: stateManager = controller.stateManager
		self.stateManager = stateManager
		if displayController is None: displayController = stateManager.displayController
		self.displayController = displayController

		self.commands = CommandSelector.commands
	
	def parse(self, text):
		text = str.strip(text)
		if not text: return
		if text[0] == '/':
			self.parseCommand(text)
		else:
			self.controller.sendMessage(text)
			#OutgoingText(text, self.controller.currentRoom, self.controller.eventManager.handleEvent, backfill=3)

	def parseCommand(self, text: str) -> None:
		"""
		Parse a string of text as a command
		
		Args:
			text (str): Input text

		Raises:
			MalformedCommandError
		"""

		if text[0] != '/': raise MalformedCommandError('Malformed command: %(text)s' % 
			{'text': str(text)})

		parse_logger.info('Parsing input as command: '+text)
		split = text.split(' ')
		command = split[0][1:].lower()
		args = []
		if len(split) > 1:
			args = split[1:]

		if command in self.commands:
			output = self.commands[command](self.controller, args).result
		else:
			parse_logger.warning('Invalid command string: '+text)
			output = EventBuilder.commandError(command, 'Unknown command.')

		if output != {}:
			self.controller.printResult(output)

	def listen(self):
		self.listening = True
		while self.listening:
			if self.mode is MODES.EDIT:
				out = self.displayController.inputBox.textbox.edit(self.getListener())
				self.displayController.clearInput()
				self.parse(out)
			elif self.mode is MODES.VISUAL:
				key = self.displayController.screen.getkey()
				self.visualParser(key)
			

	def editListener(self, keystroke: int) -> int:
		"""
		Edit-mode listener function, called on each keystroke in the inputBox's Textpad
			The Textpad calls this a validator function
		
		Args:
			keystroke (int): Input keystroke
		
		Raises:
			WrongModeError
		
		Returns:
			int: Output keystroke. Usually the same as input.
		"""

		if self.mode is not MODES.EDIT:
			raise WrongModeError('Parse.editListener called when not in edit mode.')
			
		if keystroke == curses.KEY_ENTER or keystroke == 10:
			# Send the message on enter as well as Ctrl-G
			return(7) # Ctrl-G
		elif keystroke in [curses.KEY_HOME, 27]:
			# Home or Escape. Both are accepted as Esc has some unusual behaviours in curses.
			self.setMode(MODES.VISUAL)
			return(7) # Send a Ctrl-G so we quit editing

		# TODO: Decide whether we want to use page up/down for scrolling in-Textpad or in chat
		elif keystroke == curses.KEY_PPAGE:
			self.stateManager.pageUp()
		elif keystroke == curses.KEY_NPAGE:
			self.stateManager.pageDown()

		return(keystroke)

	def visualParser(self, keystroke: int):
		"""
		Visual-mode parser function, called on each keystroke while in visual mode
			TODO: Build this
		
		Args:
			keystroke (int): Input keystroke
		"""

		if keystroke == 'i':
			self.setMode(MODES.EDIT)
		pass
		
	def getListener(self, mode:MODES=None) -> callable:
		"""
		Get the listener function for the appropriate mode
		
		Args:
			mode (MODES): Mode to get the listener for
		
		Raises:
			InvalidModeError

		Returns:
			callable: Listener function
		"""
		if mode is None: mode = self.mode
		if mode is MODES.EDIT:
			return(self.editListener)
		elif mode is MODES.VISUAL:
			return(self.visualParser)
		else:
			raise InvalidModeError('Tried to get listener for invalid mode: '+str(mode))

	def setMode(self, mode:MODES):
		"""
		Change the Parser and Display mode.
		
		Args:
			mode (MODES): Mode to change to
				One of: MODES.EDIT, MODES.VISUAL
		
		Raises:
			InvalidModeError
		"""

		if not isinstance(mode, MODES):
			raise InvalidModeError('Tried to enter invalid mode: '+str(mode))

		# Change the display config to the correct mode
		# And set up the listener in the appropriate object
		self.displayController.setMode(mode, self.getListener(mode)) 
		# TODO: BUILD THIS
		# Should call Textpad.do_command('Control-G') (or 7?) if in edit mode to kill the box
		# Probably save the contents as well, and repopulate on reentering edit mode
		# Also reconfigures display, of course
		self.mode = mode
		# This has to come second or we'll get a WrongModeError



