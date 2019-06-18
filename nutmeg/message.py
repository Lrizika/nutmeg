try:
	from .utils import tsToDt, getMember, buildTypeTree, checkStructure
	from .constants import MTYPE
except ImportError:
	from utils import tsToDt, getMember, buildTypeTree, checkStructure
	from constants import MTYPE
import curses
from curses import textpad
import matrix_client.room

import logging
message_logger = logging.getLogger('root')

# class ChatObject:
# 	def __init__(self, size):
# 		self.pad = curses.newpad(size)

class Message:#(ChatObject):
	"""
	Base class for messages in the chat.
		Message types should extend this, overloading Message.constructPad and Message.checkEventType
	
	Args:
		event (dict): Event to construct from
		room (matrix_client.room.Room): Room in which the message lives

	Attributes:
		event (dict): Event the message is constructed from
		pad (textpad.Textbox): Textpad for the message
		width (int): Width of the pad
		height (int): Height of the pad

	Class Attributes:
		MAXLEN (int): Max length, in characters, of messages
		senderColour (int): Default colour of Senders
		tsColour (int): Default colour of timestamps
		contentColour (int): Default colour of content
	"""

	MAXLEN = 1024 # Maximum length, in characters, of the message

	def __init__(self, event:dict, room:matrix_client.room.Room):
		self.senderColour = curses.A_NORMAL
		self.tsColour = curses.color_pair(1)
		self.contentColour = curses.COLOR_WHITE

		self.room = room
		self.event = event

	def build(self, width:int) -> textpad.Textbox:
		"""
		Build the message's textpad.
		
		Args:
			width (int): Width of the pad to build
		
		Returns:
			textpad.Textbox: Textpad of the message.
				You should call textpad.refresh on this (or on self.pad later)
		"""

		self.width = width
		self.height = self.MAXLEN // width + 1
		self.pad = curses.newpad(self.height, self.width)
		self.constructPad()
		return(self.pad)

	@staticmethod
	def checkEventType(event:dict) -> bool:
		"""
		Check if an event has the correct properties for this class.
			Used in determining which subclass of Message to use for printing a message.
		
		Args:
			event (dict): Event to check
		
		Returns:
			bool: Whether this is an appropriate subclass to use in printing the message.
		"""
		
		return(True)

	def constructPad(self):
		"""
		Do event-type specific construction here.
			Most message types should overload this.
		"""

		message = ('Received unknown or mangled event: %(event)s' %
			{'event': str(self.event)})
		message_logger.warn(message)
		self.printGeneric(message, colour = curses.COLOR_RED)

	def printGeneric(self, text:str, pad:textpad.Textbox = None, colour:int = None) -> textpad.Textbox:
		"""
		Print generic text to the message.

		Args:
			text (str): Text to be written
			pad (textpad.Textbox, optional): Defaults to self.pad. The pad to write to.
			colour (int, optional): Defaults to self.contentColour. The colour to write in.

		Returns:
			textpad.Textbox: The pad written to.
		"""

		if colour is None: colour = self.contentColour
		if pad is None: pad = self.pad
		pad.addstr(str(text), colour)
		return(pad)

	def printSender(self, pad:textpad.Textbox = None, colour:int = None, append:str = None) -> textpad.Textbox:
		"""
		Add a Sender to the message.

		Args:
			pad (textpad.Textbox, optional): Defaults to self.pad. The pad to write to.
			colour (int, optional): Defaults to self.senderColour. The colour to write in.
			append (str, optional): Defaults to None. If supplied, appends the string to the pad in the same colour.

		Returns:
			textpad.Textbox: The pad written to.
		"""
		
		if colour is None: colour = self.senderColour
		if pad is None: pad = self.pad
		sender = getMember(self.room, self.event['sender']).displayname
		if append is not None: sender += append
		pad.addstr(sender, colour)
		return(pad)

	def printOriginTs(self, pad:textpad.Textbox = None, colour:int = None, append:str = None) -> textpad.Textbox:
		"""
		Add a timestamp to the message (origin server timestamp).

		Args:
			pad (textpad.Textbox, optional): Defaults to self.pad. The pad to write to.
			colour (int, optional): Defaults to self.tsColour. The colour to write in.
			append (str, optional): Defaults to None. If supplied, appends the string to the pad in the same colour.

		Returns:
			textpad.Textbox: The pad written to.
		"""

		if colour is None: colour = self.tsColour
		if pad is None: pad = self.pad
		ts = tsToDt(str(self.event['origin_server_ts']))
		if append is not None: ts += append
		pad.addstr(ts, colour)
		return(pad)

class Event(Message):
	"""
	Standard events

	Defined in:
		Client-Server API: 9 Events
		https://matrix.org/docs/spec/client_server/r0.5.0#id276
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': str,
			'content': {}
		}
		return(checkStructure(event, structure))

class NutmegEvent(Event):
	"""
	Events sent from Nutmeg
		Used for errors, command output, etc.
	
	Required fields:
		'type': string
		'source': 'Nutmeg'
		'content': dict
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': str,
			'source': 'Nutmeg',
			'content': {}
		}
		return(checkStructure(event, structure))

	def constructPad(self):
		"""
		Generic output. This should be overloaded for most output.
		"""
		message = ('Unknown Nutmeg output: %(event)s' %
			{'event': str(self.event)})
		message_logger.warn(message)
		self.printGeneric(message, colour = curses.COLOR_RED)

class NutmegCommandOutput(NutmegEvent):
	"""
	Output sent from Nutmeg commands.
		This should be sent on a successful command - Use NutmegCommandError for failures
	
	Required fields:
		'type': 'n.output.command'
		'command': string
		'message': string

	Output style:
		Command: Message
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'n.output.command',
			'content': {
				'command': str,
				'message': str
			}
		}
		return(checkStructure(event, structure))

	def constructPad(self):
		self.printGeneric(self.event['content']['command'] + ': ', colour=self.senderColour)
		self.printGeneric(self.event['content']['message'], colour=self.contentColour)

class NutmegCommandHelp(NutmegEvent):
	"""
	Help messages sent from Nutmeg commands.
	
	Required fields:
		'type': 'n.output.help'
		'command': string
		'message': string

	Output style:
		Command: Message
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'n.output.help',
			'content': {
				'command': str,
				'message': str
			}
		}
		return(checkStructure(event, structure))

	def constructPad(self):
		self.printGeneric(self.event['content']['command'] + ': ', colour=self.senderColour)
		self.printGeneric(self.event['content']['message'], colour=self.contentColour)

class NutmegCommandError(NutmegEvent):
	"""
	Errors sent from Nutmeg commands.
	
	Required fields:
		'type': 'n.output.error'
		'command': string
		'message': string

	Output style:
		Command: Message
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'n.output.error',
			'content': {
				'command': str,
				'message': str
			}
		}
		return(checkStructure(event, structure))

	def constructPad(self):
		self.printGeneric(self.event['content']['command'] + ': ', colour=self.senderColour)
		self.printGeneric(self.event['content']['message'], colour=curses.COLOR_RED)

class RoomEvent(Event):
	"""
	Defined in:
		Client-Server API: 9.1.2 Room Event Fields
		https://matrix.org/docs/spec/client_server/r0.5.0#id279
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'event_id': str,
			'sender': str,
			'origin_server_ts': int
		}
		# Note that required field room_id is NOT checked
		# This is because events received through /sync do not include this field
		return(checkStructure(event, structure))

class StateEvent(RoomEvent):
	"""
	Defined in:
		Client-Server API: 9.1.3 State Event Fields
		https://matrix.org/docs/spec/client_server/r0.5.0#id280
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'state_key': str
		}
		return(checkStructure(event, structure))

class RoomAliases(StateEvent):
	"""
	Room Aliases
		We don't print this

	Defined in:
		Client-Server API: 9.3.1 m.room.aliases
		https://matrix.org/docs/spec/client_server/r0.5.0#id283

	Output style:
		None
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'm.room.aliases',
			'content': {
				'aliases': list
			}
		}
		return(checkStructure(event, structure))

	def constructPad(self): pass

class CanonicalAlias(StateEvent):
	"""
	Defined in:
		Client-Server API: 9.3.2 m.room.canonical_alias
		https://matrix.org/docs/spec/client_server/r0.5.0#id284

	Output style:
		Timestamp - Sender changed the room's canonical alias to Alias
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'm.room.canonical_alias',
			'content': {
				'alias': str
			}
		}
		return(checkStructure(event, structure))
	
	def constructPad(self):
		message = ('changed the room\'s canonical alias to %(alias)s.' %
			{'alias':str(self.event['content']['alias'])})
		self.printOriginTs(append=' - ')
		self.printSender(append=' ')
		self.printGeneric(message, colour=self.senderColour)

class RoomName(StateEvent):
	"""
	Defined in:
		Client-Server API: 13.2.1.3 m.room.name
		https://matrix.org/docs/spec/client_server/r0.5.0#id364

	Output style:
		Timestamp - Sender changed the room name to Name
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'm.room.name',
			'content': {
				'name': str
			}
		}
		return(checkStructure(event, structure))
	
	def constructPad(self):
		message = ('changed the room name to %(name)s.' %
			{'name':str(self.event['content']['name'])})
		self.printOriginTs(append=' - ')
		self.printSender(append=' ')
		self.printGeneric(message, colour=self.senderColour)
	

class RoomMessage(RoomEvent):
	"""
	Room Message Events

	Defined in:
		Client-Server API: 13.2.1.1 m.room.message
		https://matrix.org/docs/spec/client_server/r0.5.0#id362

	Output style:
		Timestamp - Sender: Text
	"""
	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'type': 'm.room.message',
			'content': {
				'body': str,
				'msgtype': str
			}
		}
		return(checkStructure(event, structure))
	
	def constructPad(self):
		"""
		As per spec, the body key should be printed if a more specific msgtype is not able to be used
		"""
		self.printOriginTs(append=' - ')
		self.printSender(append=': ')
		self.printGeneric(str(self.event['content']['body']))

class TextMessage(RoomMessage):
	"""
	Defined in:
		Client-Server API: 13.2.1.7.1 m.text
		https://matrix.org/docs/spec/client_server/r0.5.0#id369
	"""

	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'content': {
				'msgtype': 'm.text'
			}
		}
		return(checkStructure(event, structure))

class EmoteMessage(RoomMessage):
	"""
	Defined in:
		Client-Server API: 13.2.1.7.2 m.emote
		https://matrix.org/docs/spec/client_server/r0.5.0#id370
		
	Output style: 
		Timestamp * Sender Text
	"""

	@staticmethod
	def checkEventType(event:dict) -> bool:
		structure = {
			'content': {
				'msgtype': 'm.emote'
			}
		}
		return(checkStructure(event, structure))
	
	def constructPad(self):
		self.printOriginTs(append=' * ')
		self.printSender(append=' ')
		self.printGeneric(str(self.event['content']['body']), colour=self.senderColour)


class MessageBuilder:
	"""
	Container method for building generic events into Messages.
		Only MessageBuilder.initMessage should usually be used.
	"""

	messageTypeTree = {Message: buildTypeTree(Message)}

	@staticmethod
	def initMessage(event:dict, room:matrix_client.room.Room) -> Message:
		"""
		Initialize a Message of the appropriate class from an event and a room.
			Checks each subclass of Message to see if that subclass is the appropriate type for that event.
			If none are, defaults to base Message class.
		
		Args:
			event (dict): event to build the Message from
			room (matrix_client.room.Room): room in which the event occurred
		
		Returns:
			Message: Message or subclass therein built from the event and room
				Displays should call .build(width) on this to print the message
		"""

		message_logger.debug('Building message for event: %(event)s' %
			{'event': str(event)})

		messageType = MessageBuilder._selectInTypeTree(MessageBuilder.messageTypeTree, event)
		message_logger.debug('Using messageType: %(messageType)s' %
			{'messageType': str(messageType)})
		if messageType is None: raise ValueError('MessageBuilder._selectInTypeTree returned None. This should never happen.')
		return(messageType(event, room))

	@staticmethod
	def _selectInTypeTree(typeTree:dict, event:dict):
		"""
		Recurse through the messageTypeTree to find the most specific applicable class
			Note that if multiple subclasses are valid for an event, the first one parsed will be chosen
			So make sure to keep classes hierarchical 
		
		Args:
			typeTree (dict): [description]
			event (dict): [description]

		Returns:
			type or None: The subclass in the typeTree that is applicable
				If none are applicable, returns None
		"""

		for cls in typeTree:
			if cls.checkEventType(event):
				if typeTree[cls] == {}:
					return(cls)
				else:
					res = MessageBuilder._selectInTypeTree(typeTree[cls], event)
					if res is not None:
						return(res)
					else:
						return(cls)
		return(None)

