try:
	from display import DisplayController
	from errors import MissingEventIdError
except ImportError:
	from .display import DisplayController
	from .errors import MissingEventIdError
import curses
import matrix_client
import matrix_client.client

import logging
control_logger = logging.getLogger('root')

class Controller:
	def __init__(self, screen:"curses.window", homeserver:str, username:str=None, password:str=None):
		self.displayController = DisplayController(screen)

		self.homeserver = homeserver
		self.username = username
		self.password = password

		self.displayController.statusDisplay.printConnecting(self.homeserver)

		self.client = matrix_client.client.MatrixClient('https://%(homeServer)s' %
			{'homeServer': self.homeserver}, cache_level=matrix_client.client.CACHE.NONE)

		self.displayController.statusDisplay.printLoggingIn(self.username, self.homeserver)
		if username is None or password is None: self.promptLogin(username=username)
		else: self.client.login_with_password(username=self.username, password=self.password)
		

		self.eventQueue = EventQueue()

		self.stateManager = StateManager(self.client, self.displayController, self.handleEvent)

	def promptLogin(self, username:str=None): raise NotImplementedError

	def handleEvent(self, room:matrix_client.room.Room, event:dict):
		if self.eventQueue.checkAndSetHandled(event):
			control_logger.debug('Already handled event %(eventId)s' %
				{'eventId': event['event_id']})
			return
		else:
			control_logger.debug('Handling event %(eventId)s' %
				{'eventId': event['event_id']})
			self.displayController.enqueue(event, room)

	def sendMessage(self, text:str):
		self.stateManager.sendMessage(text)
		# TODO

	def printResult(self, output:dict):
		self.displayController.enqueue(output, self.stateManager.currentRoom)


class EventQueue:
	def __init__(self):
		self.handled = {}

	def checkAndSetHandled(self, event:dict) -> bool:
		"""
		Check whether an event has been handled, and if not set it to handled.
			Returns whether the event was previously handled.
		
		Args:
			event (dict): [description]

		Returns:
			bool: Whether the event was already handled
		"""

		if self.checkHandled(event):
			return(True)
		else:
			self.setHandled(event)
			return(False)


	def checkHandled(self, event:dict) -> bool:
		if 'event_id' not in event:
			raise MissingEventIdError
		if event['event_id'] in self.handled:
			return(True)
		else:
			return(False)

	def setHandled(self, event:dict):
		self.handled[event['event_id']] = event

class StateManager:
	def __init__(self, client:matrix_client.client.MatrixClient, displayController:DisplayController, eventHandler:callable):
		self.client = client
		self.displayController = displayController
		self.eventHandler = eventHandler
		self.currentRoom = None
		self.rooms = {}

	def joinRoom(self, roomId:str):
		self.displayController.statusDisplay.printJoining(roomId)
		if roomId in self.rooms: room = self.rooms[roomId]
		elif roomId in self.client.rooms: room = self.client.rooms[roomId]
		else:
			room = self.client.join_room(roomId)
			self.rooms[roomId] = room
			
			room.add_listener(self.eventHandler)
			self.client.stop_listener_thread()
			self.client.start_listener_thread()
			room.backfill_previous_messages(limit=500) # TODO
			#except Exception as e:
			#	control_logger.error('Exception while joining room: '+str(e))
			#	self.eventManager.displayManager.statusDisplay.printStatus('Failed to join room: '+roomId)
			#	room = self.currentRoom
			#	return
		self.currentRoom = room
		self.displayController.changeRoom(room)#, sortFirst=True)
		self.displayController.statusDisplay.printRoomHeader(room)
		#self.eventManager.displayManager.changeRoom(room)
		#self.eventManager.displayManager.messageDisplay.printQueue(room, sortFirst=True)

	def sendMessage(self, text:str):
		self.currentRoom.send_text(text)
		self.currentRoom.backfill_previous_messages(limit=5) # TODO: Replace this with something that doesn't get confused by _prev_batch

	def sendEmote(self, text:str):
		self.currentRoom.send_emote(text)
		self.currentRoom.backfill_previous_messages(limit=5) # TODO: Replace this with something that doesn't get confused by _prev_batch

	def pageUp(self):
		self.displayController.changeOffset(10)

	def pageDown(self):
		self.displayController.changeOffset(-10)
