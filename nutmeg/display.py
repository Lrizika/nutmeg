try:
	from .utils import tsToDt, getMember, descendants, getLastChar2
	from .constants import MTYPE, MODES
	from .message import MessageBuilder, Message
	from .errors import InvalidModeError
except ImportError:
	from utils import tsToDt, getMember, descendants, getLastChar2
	from constants import MTYPE, MODES
	from message import MessageBuilder, Message
	from errors import InvalidModeError
import curses, _curses
import matrix_client.room

import logging
display_logger = logging.getLogger('root')

class MessageQueues:
	def __init__(self):
		self.queues = {}
		# Structure:
		# {'room_id': [Message, Message, Message...]}
		# Keys are Room.room_id
		# Values are lists of Messsages
		# 	(These would be collections.deque, but those don't support sorts or slicing)
		# 	Message lists are ordered new to old

	def buildAndEnqueue(self, event:dict, room:matrix_client.room.Room):
		"""
		Build a Message from an event, then queue that Message in a room's queue
		
		Args:
			event (dict): Event to build a Message for and queue
			room (matrix_client.room.Room): Room in which to queue it
		"""

		message = MessageBuilder.initMessage(event, room)
		self.enqueue(message, room)

	def enqueue(self, message:Message, room:matrix_client.room.Room):
		"""
		Queue a Message in a room's queue
		
		Args:
			message (Message): Message to queue
			room (matrix_client.room.Room): Room in which to queue it
		"""

		if room.room_id not in self.queues: self.queues[room.room_id] = []
		display_logger.debug('Queueing Message to room %(roomId)s: %(message)s' %
			{'roomId':room.room_id,
			'message':str(message)})
		self.queues[room.room_id].insert(0, message)


	def sortQueue(self, room:matrix_client.room.Room):
		"""
		Sort a room queue by timestamp (in-place)
		
		Args:
			room (matrix_client.room.Room): Room for which to sort the queue
		"""

		self.queues[room.room_id].sort(key=lambda message: int(message.event['origin_server_ts']), reverse=True)

	def getQueue(self, room:matrix_client.room.Room, start:int = 0, count:int = 0) -> list:
		#display_logger.debug('Queues: '+str(self.queues))
		if count is 0:
			return(self.queues[room.room_id][start:])
		return(self.queues[room.room_id][start:start+count])

class DisplayController:
	def __init__(self, screen:"curses.window"):
		self.screen = screen
		curses.use_default_colors()
		curses.init_color(curses.COLOR_WHITE, 500, 500, 500)
		curses.init_pair(1, curses.COLOR_WHITE, -1)
		screen.bkgd(curses.color_pair(1))
		self.messageDisplay = None
		self.buildWindows()
		self.offset = 0
		self.currentRoom = None
		self.mode = MODES.EDIT

	def setMode(self, mode:MODES, inputListener:callable):
		if not isinstance(mode, MODES):
			raise InvalidModeError('Tried to enter invalid mode: '+str(mode))

		self.mode = mode

		if self.mode is MODES.EDIT:
			self.buildWindows()
		elif self.mode is MODES.VISUAL:
			self.inputBox.clear()
			self.buildWindows(inputHeight=0)

		self.changeOffset(0)

	def clearInput(self):
		if self.inputBox is not None:
			self.inputBox.clear()

	def buildWindows(self, statusHeight:int=1, inputHeight:int=4):
		self.height, self.width = self.screen.getmaxyx()

		statusY = 0
		statusX = 0
		statusWidth = self.width - statusX
		statusWindow = self.screen.subwin(statusHeight, statusWidth, statusY, statusX)
		self.statusDisplay = StatusDisplay(statusWindow, statusY, statusX)

		messageY = statusY + statusHeight
		messageX = 0
		messageHeight = self.height - statusHeight - inputHeight - 1
		messageWidth = self.width - messageX
		messageWindow = self.screen.subwin(messageHeight, messageWidth, messageY, messageX)
		if self.messageDisplay is None:
			self.messageDisplay = MessageDisplay(messageWindow, messageY, messageX)
		else:
			self.messageDisplay.setWindow(messageWindow, messageY, messageX)

		if inputHeight > 0:
			inputY = self.height - inputHeight
			inputX = 0
			inputWidth = self.width - inputX
			self.inputWindow = self.screen.subwin(inputHeight, inputWidth, inputY, inputX)
			self.inputBox = InputBox(self.inputWindow, inputY, inputX)
		else:
			self.inputBox = None

	def changeRoom(self, room:matrix_client.room.Room, sortFirst:bool=False):
		if sortFirst: self.messageDisplay.messageQueues.sortQueue(room)
		if room is not self.currentRoom:
			self.currentRoom = room
			self.messageDisplay.printQueue(room, offset=self.offset)
		else:
			self.offset = 0
			self.messageDisplay.printQueue(room, offset=self.offset)
			# TODO: Update status etc

	def changeOffset(self, amount:int):
		display_logger.debug('changeOffset called. Current offset: '+str(self.offset)+', amount: '+str(amount))
		self.offset += amount
		if self.offset < 0: self.offset = 0
		topSpace = self.messageDisplay.printQueue(self.currentRoom, offset=self.offset)
		while topSpace > 1 and self.offset > 0:
			self.offset -= 1
			topSpace = self.messageDisplay.printQueue(self.currentRoom, offset=self.offset)
		display_logger.debug('New offset: '+str(self.offset))

	def enqueue(self, event:dict, room:matrix_client.room.Room):
		self.messageDisplay.messageQueues.buildAndEnqueue(event, room)
		if room is self.currentRoom:
			self.messageDisplay.printQueue(self.currentRoom, offset=self.offset)

class InputBox:
	def __init__(self, screen:"curses.window", y:int, x:int):
		self.screen = screen
		self.y = y
		self.x = x
		self.height, self.width = screen.getmaxyx()
		#self.textpad = curses.newpad(16, self.width)
		self.textbox = curses.textpad.Textbox(self.screen, insert_mode=True)

	def clear(self):
		self.screen.clear()
		self.screen.refresh()

	@property
	def cursorIsAtTop(self):
		y, x = curses.getsyx()
		return(y == self.y)
	@property
	def cursorIsAtBottom(self):
		y, x = curses.getsyx()
		return(y == self.y+self.height-1)

class MessageDisplay:
	"""
	Section of the screen in which messages are displayed.

	Arguments:
		window ("curses.window"): Window object to use
		y (int): Top of the window
		x (int): Left of the window
	"""

	def __init__(self, window:"curses.window", y:int, x:int):
		self.setWindow(window, y, x)
		self.messageQueues = MessageQueues()

	def setWindow(self, window:"curses.window", y:int, x:int):
		"""
		Called to set or update the window.
			E.g. on resize or move
		
		Args:
			window ("curses.window"): New window to use
			y (int): y of the window
			x (int): x of the window
		"""

		self.y = y
		self.x = x
		self.window = window
		self.height, self.width = window.getmaxyx()

	def printQueue(self, room:matrix_client.room.Room, offset:int = 0) -> int:
		"""
		Print the MessageQueue to the screen.
		
		Args:
			room (matrix_client.room.Room): Room to print
			offset (int, optional): Defaults to 0. If set, starts from the nth oldest message.

		Returns:
			int: Number of empty lines at the top of the screen
		"""

		self.window.clear()
		self.window.refresh()

		messages = self.messageQueues.getQueue(room, start=offset)#, count=self.height)
		# We just get the entire queue, as otherwise hidden message mess stuff up
		# Plus it's not like the memory usage will cause issues unless you somehow load many tens of thousands of messages

		display_logger.debug('Printing queue. Length: '+str(len(messages)))

		y = self.height + self.y
		for message in messages:
			if y < self.y: break

			pad = message.build(self.width)
			try:
				writeHeight = getLastChar2(pad)[0]

				writeTop = y - writeHeight
				padTop = max(self.y - writeTop, 0)
				if writeTop < self.y:
					writeTop = self.y

				pad.refresh(padTop,0, writeTop,self.x, y,self.x+self.width)		

				y -= writeHeight + 1 # Step back the height of the message, plus one (otherwise we'd just overwrite the same one line)

			except IndexError:
				# If the pad doesn't have any characters in it, we don't want to step up
				pass

		display_logger.debug('printQueue returned: '+str(max(y-self.y, 0)))

		return(max(y-self.y, 0))

class StatusDisplay:
	def __init__(self, screen, y, x):
		self.screen = screen
		self.y = y
		self.x = x
		self.height, self.width = screen.getmaxyx()

	def printStatus(self, status: str) -> None:
		display_logger.info('Status: '+status)
		if len(status) >= self.width:
			status = status[:self.width-4] + '...'
		self.screen.clear()
		try:
			self.screen.addstr(0,0,status,curses.color_pair(1))
		except curses.error as e:
			self.screen.clear()
			self.screen.addstr(0,0,'Nutmeg')
			display_logger.warning('Error when printing status: '+str(e))
			display_logger.info('Printing "Nutmeg" instead.')
		self.screen.refresh()
	
	def printRoomHeader(self, room, loading=False):
		topic = room.topic
		if not topic: topic = '(No topic)'
		#if len(topic) > 23: topic = topic[:20] + '...'
		status = ('%(user)s - %(roomName)s - %(topic)s' %
			{'user': str(getMember(room, room.client.user_id).get_display_name()),
			'roomName': str(room.display_name),
			'topic': str(topic)})
		if loading is True:
			status = '(Loading) ' + status
		self.printStatus(status)

	def printConnecting(self, server):
		status = ('Connecting to homeserver %(homeserver)s...' %
			{'homeserver': str(server)})
		self.printStatus(status)

	def printLoggingIn(self, username, server):
		status = ('Logging in as %(username)s on %(homeServer)s...' % 
			{'username': str(username),
			'homeServer': server})
		self.printStatus(status)

	def printJoining(self, roomId):
		status = ('Joining %(roomId)s...' % 
			{'roomId': roomId})
		self.printStatus(status)
