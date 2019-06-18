#!/usr/bin/python36

from matrix_client.client import MatrixClient, CACHE
from matrix_client.errors import MatrixHttpLibError
import datetime
import curses
from curses import textpad

import logging
from logging.handlers import RotatingFileHandler


#
# Utility Functions
#
def descendants(cls: type) -> list:
	"""
	Return a list of all descendant classes of a class
	
	Arguments:
		cls (type): Class from which to identify descendants
	Returns:
		subclasses (list): List of all descendant classes
	"""

	subclasses = cls.__subclasses__()
	for subclass in subclasses:
		subclasses.extend(descendants(subclass))

	return(subclasses)

def tsToDt(timestamp: str) -> str:
	"""
	Convert a timestamp string to a human-readable string.
	Returns timestamps from today as H:M:S, and earlier as Y-M-D
	
	Arguments:
		timestamp {str} -- Unix-style timestamp
	
	Returns:
		str -- Y-M-D or H:M:S
	"""
	dt = datetime.datetime.fromtimestamp(int(timestamp)/1000)
	if abs(datetime.datetime.today()-dt) < datetime.timedelta(days=1):
		return(dt.strftime('%H:%M:%S'))
	return(dt.strftime('%Y-%m-%d'))
	#return(dt.strftime('%Y-%m-%d %H:%M:%S'))

def getEvent(room, eventId):
	for event in room.events:
		if event['event_id'] == eventId:
			return(event)
	else:
		raise IndexError('Event %(eventId)s not found. Do you need to call room.backfill_previous_messages?' %
			{'eventId': str(eventId)})

def getUser(room, userId):
	for member in room.get_joined_members():
		if member.user_id == userId:
			return(member)
	else:
		raise IndexError('User %(userId)s not found in room %(roomName)s (%(roomId)s).' %
			{'userId': str(userId),
			'roomName': str(room.display_name),
			'roomId': str(room.room_id)})

def getLastChar(window) -> tuple:
	"""
	Returns the last filled character in a window object.
	
	Arguments:
		window {curses.window} -- The window to check
	
	Returns:
		tuple (y,x) -- The (y,x) of the last filled character, relative to the window
	"""

	height, width = window.getmaxyx()
	for y in range(height-1, -1, -1):
		for x in range(width-1, -1, -1):
			if window.instr(y,x,1) != b' ':
				return(y,x)
	raise IndexError('No filled characters in window.')

def stripAutoNewlines(text: str, interval: int) -> str:
	"""
	Removes newlines that are automatically added by Textpads on linewrap
	
	Arguments:
		text {[type]} -- [description]
		interval {[type]} -- [description]
	"""

	i = interval
	newText = ''
	while i<len(text) and text[i] == '\n':
		newText += text[i-interval:i]
		i += interval + 1
	newText += text[i-interval:]
	if newText[-1] == '\n': newText = newText[:-1]
	return(newText)

def backfill_previous_messages_and_update_batch(room, reverse=False, limit=10):
	"""Backfill handling of previous messages, then update prev_batch
	Allows for loading of older messages.

	Args:
		reverse (bool): When false messages will be backfilled in their original
			order (old to new), otherwise the order will be reversed (new to old).
		limit (int): Number of messages to go back.

	Returns:
		int: Number of events in chunk
	"""
	res = room.client.api.get_room_messages(room.room_id, room.prev_batch, direction="b", limit=limit)
	events = res["chunk"]
	room.prev_batch = res['end']
	if not reverse:
		events = reversed(events)
	for event in events:
		room._put_event(event)
	return(len(res['chunk']))
	#if len(res['chunk']) == 0:
	#		raise IndexError('Tried to load beyond end of messages.')

#class PadBox(curses.textpad.Textbox):
	# """
	# Variant Textbox that supports using a pad for the window.
	# """
	# def edit(self, pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol, validate=None):
	# 	"""
	# 	Edit in the widget window and collect the results.

	# 	Arguments:
	# 		pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol -- See curses.window.refresh
	# 	"""
	# 	while 1:
	# 		ch = self.win.getch()
	# 		if validate:
	# 			ch = validate(ch)
	# 		if not ch:
	# 			continue
	# 		if not self.do_command(ch):
	# 			break
	# 		self.win.refresh(pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol)
	# 	return self.gather()


class OutgoingText:
	"""
	Object for sending outgoing messages.
	Allows for registering a handler to be called on the event ID post-sending.
	TODO: Make this properly asynchronous
	"""

	def __init__(self, text, room, completeHandler, backfill: int=0):
		try:
			self.eventId = room.send_text(text)['event_id']
		except MatrixHttpLibError as e:
			app_log.warning('Exception while sending text, trying again: '+str(e))
			try:
				self.eventId = room.send_text(text)['event_id']
			except MatrixHttpLibError as e:
				app_log.error('Exception on second try sending text, aborting try: '+str(e))
				raise
		if backfill: room.backfill_previous_messages(limit=backfill)
		completeHandler(room, getEvent(room, self.eventId))


class EventManager:
	"""
	Handles incoming events.
	"""

	def __init__(self, displayManager):
		self.displayManager = displayManager
		self.handled = []

	def handleEvent(self, room, event):
		oldY, oldX = curses.getsyx()
		if event['event_id'] not in self.handled:
			app_log.debug('Handling event: '+event['event_id'])
			try:
				self.handleMessage(room, event)
			except Exception as e:
				app_log.error('Error while handling event: %(event)s' %
					{'event': str(event)})
				app_log.error(str(e))
			self.handled.append(event['event_id'])
		else:
			app_log.debug('Already handled event: '+event['event_id'])
		self.displayManager.screen.move(oldY, oldX)
		self.displayManager.screen.refresh()

	def handleMessage(self, room, event):
		if self.displayManager.messageDisplay.queueMessage(room, event, sortAfter=True):
			if self.displayManager.currentRoom is not None and self.displayManager.currentRoom.room_id == room.room_id:
				self.displayManager.messageDisplay.printQueue(room)
		
class DisplayManager:
	def __init__(self, screen, y, x, startRoom = None):
		self.screen = screen
		self.y = y
		self.x = x
		self.height, self.width = screen.getmaxyx()
		self.currentRoom = None

		# TODO: Change new windows into new pads
		#self.messageQueue = MessageQueue()
		statusY = 0
		statusHeight = 1
		statusX = 0
		statusWidth = self.width - statusX
		self.statusScreen = curses.newwin(statusHeight,statusWidth,statusY,statusX)
		self.statusDisplay = StatusDisplay(self.statusScreen, statusY, statusX)
		inputHeight = 4
		inputY = self.height-inputHeight
		inputX = 0
		inputWidth = self.width - inputX
		self.inputScreen = curses.newwin(inputHeight, inputWidth, inputY, inputX)
		self.inputBox = InputBox(self.inputScreen, inputY, inputX)
		messageY = statusHeight + statusY
		messageHeight = self.height - messageY - inputHeight
		messageX = 0#10
		messageWidth = self.width - messageX
		self.messageScreen = curses.newwin(messageHeight, messageWidth, messageY, messageX)
		self.messageDisplay = MessageDisplay(self.messageScreen, messageY, messageX)#, self.messageQueue)
		if startRoom is not None: self.changeRoom(startRoom)
		
	def changeRoom(self, room):
		oldY, oldX = curses.getsyx()
		self.currentRoom = room
		#self.messageQueue.addRoom(room)
		self.currentRoom.update_room_name()
		self.currentRoom.update_room_topic()
		self.currentRoom.update_aliases()
		self.statusDisplay.printRoomHeader(room)
		self.screen.move(oldY, oldX)

class InputBox:
	def __init__(self, screen, y, x):
		self.screen = screen
		self.y = y
		self.x = x
		self.height, self.width = screen.getmaxyx()
		#self.textpad = curses.newpad(16, self.width)
		self.textbox = textpad.Textbox(self.screen, insert_mode=True)

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

class StatusDisplay:
	def __init__(self, screen, y, x):
		self.screen = screen
		self.y = y
		self.x = x
		self.height, self.width = screen.getmaxyx()

	def printStatus(self, status: str) -> None:
		app_log.info('Status: '+status)
		if len(status) >= self.width:
			status = status[:self.width-4] + '...'
		self.screen.clear()
		try:
			self.screen.addstr(0,0,status,curses.color_pair(1))
		except curses.error as e:
			self.screen.clear()
			self.screen.addstr(0,0,'Nutmeg')
			app_log.warning('Error when printing status: '+str(e))
			app_log.info('Printing "Nutmeg" instead.')
		self.screen.refresh()
	
	def printRoomHeader(self, room, loading=False):
		topic = room.topic
		if not topic: topic = '(No topic)'
		#if len(topic) > 23: topic = topic[:20] + '...'
		status = ('%(user)s - %(roomName)s - %(topic)s' %
			{'user': str(getUser(room, room.client.user_id).get_display_name()),
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

class MessageDisplay:
	def __init__(self, screen, y, x):#, messageQueue):
		self.screen = screen
		self.y = y
		self.x = x
		self.offset = 0
		self.height, self.width = screen.getmaxyx()
		#self.messageQueue = messageQueue
		self.messageQueue = {}
		
	def printMessage(self, room, event):
		self.queueMessage(room, event)
		self.printQueue(room, sortFirst=True)

	def printQueue(self, room, sortFirst: bool=False):
		"""[summary]
		
		Arguments:
			room {[type]} -- [description]
		
		Keyword Arguments:
			sortFirst {bool} -- [description] (default: {False})

		Returns:
			bool -- Whether there is empty space at the top of the screen
		"""

		if sortFirst is True:
			self.sortQueue(room)
		self.screen.clear()
		self.screen.refresh()
		y=self.height + self.y
		#app_log.info(self.messageQueue)
		#app_log.info(room)
		queue = list(reversed(self.messageQueue[room.room_id]))[self.offset:]#self.height+self.offset]
		for message in queue:#.get(room, count=self.height):
			y -= message.printHeight
			if y+message.printHeight<=self.y: return(False)
			if message.printHeight:
				try:
					message.pad.refresh(max(0, self.y-y),0, max(y, self.y),self.x, max(y+message.printHeight-1, self.y),self.width+self.x)
				except curses.error as e:
					app_log.error('Exception received while printing queue: '+str(e))
					app_log.info((max(0, self.y-y),0, max(y, self.y),self.x, max(y+message.printHeight-1, self.y),self.width+self.x))
		return(y > self.y + 2)
			
	def queueMessage(self, room, event, sortAfter: bool=False) -> bool:
		"""[summary]
		
		Arguments:
			room {[type]} -- [description]
			event {[type]} -- [description]
		
		Keyword Arguments:
			sortAfter {bool} -- [description] (default: {False})

		Returns:
			bool -- True if event is still last in queue
		"""

		if room.room_id not in self.messageQueue: self.messageQueue[room.room_id] = []
		
		messagePad = curses.newpad(self.height, self.width)
		self.messageQueue[room.room_id].append(Message(messagePad, room, event))
		if sortAfter is True: self.sortQueue(room)
		return(self.messageQueue[room.room_id][-1].event == event)

	def queueMessageChunk(self, room, events: list):
		for event in events: self.queueMessage(room, event)
		self.sortQueue(room)

	def sortQueue(self, room):
		self.messageQueue[room.room_id].sort(key=lambda ts: int(ts.event['origin_server_ts']))

class Message:
	def __init__(self, pad, room, event):
		self.event = event
		self.room = room
		self.pad = pad
		self.height, self.width = pad.getmaxyx()
		try:
			self.build()
		except curses.error as e:
			app_log.error('Exception in Message.build: '+str(e))
			self.buildBroken()
		try:
			self.printHeight = getLastChar(self.pad)[0]+1
		except IndexError:
			self.printHeight = 0

	def build(self):
		if self.event['type'] == 'm.room.message':
			self.buildMessage()
		elif self.event['type'] == 'm.room.member':
			self.buildMember()
		elif self.event['type'] == 'm.room.create':
			self.buildCreate()
		elif self.event['type'] == 'm.room.name':
			self.buildName()
		elif self.event['type'] == 'm.room.aliases':
			self.buildAliases()
		elif self.event['type'] == 'm.room.canonical_alias':
			self.buildCanonical()
		elif self.event['type'] == 'm.room.topic':
			self.buildTopic()
		elif self.event['type'] in [
				'm.room.power_levels', 
				'm.room.join_rules', 
				'm.room.history_visibility', 
				'm.room.guest_access']:
			app_log.debug('Not building message for event: %(event)s' %
				{'event': str(self.event)})
			# These events don't warrant display
		else:
			self.buildBroken()

	def buildTopic(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s changed the topic to "%(topic)s".' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'topic': str(self.event['content']['topic'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildCanonical(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s changed the room\'s canonical alias to %(alias)s.' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'alias': str(self.event['content']['alias'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildAliases(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		aliasStr = ''
		if len(self.event['content']['aliases']) == 0:
			aliasStr = ' There are no known aliases.'
		elif len(self.event['content']['aliases']) <= 5:
			aliasStr = ' Current known aliases: '
			for alias in self.event['content']['aliases']:
				aliasStr += str(alias) + ', '
			aliasStr = aliasStr[:-2]
		message = ('%(timestamp)s %(sender)s updated the room aliases.' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name())})
		message += aliasStr
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildName(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s changed the room name to %(name)s.' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'name': str(self.event['content']['name'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildCreate(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s created the room.' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name())})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildMember(self):
		if self.event['content']['membership'] == 'join':
			if 'unsigned' in self.event and \
				'prev_content' in self.event['unsigned'] and \
					'displayname' in self.event['unsigned']['prev_content']:
				self.buildChangedName()
			else:
				self.buildJoin()
		elif self.event['content']['membership'] == 'invite':
			self.buildInvite()
		elif self.event['content']['membership'] == 'leave':
			if 'unsigned' in self.event and \
				'prev_content' in self.event['unsigned'] and \
					'membership' in self.event['unsigned']['prev_content'] and \
						self.event['unsigned']['prev_content']['membership'] == 'ban':
				self.buildUnban()
			else:
				self.buildLeave()
		elif self.event['content']['membership'] == 'ban':
			self.buildBan()
		else:
			self.buildBroken()

	def buildInvite(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(username)s invited %(invitee)s (%(stateKey)s).' %
			{'timestamp': timestamp,
			'username': str(getUser(self.room, self.event['sender']).get_display_name()),
			'invitee': str(self.event['content']['displayname']),
			'stateKey': str(self.event['state_key'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildChangedName(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		oldName = str(self.event['unsigned']['prev_content']['displayname'])
		newName = str(self.event['content']['displayname'])
		if oldName != newName:
			message = ('%(timestamp)s %(oldName)s changed their display name to %(newName)s.' %
				{'timestamp': timestamp,
				'oldName': oldName,
				'newName': newName})
			getUser(self.room, self.event['sender']).displayname = self.event['content']['displayname']
			app_log.debug('Built message: '+message)
			self.pad.addstr(0,0,message,curses.color_pair(1))
		else:
			self.buildJoin()

	def buildBan(self):
		reasonStr = ''
		if 'reason' in self.event['content']:
			reasonStr = ' Reason: '+str(self.event['content']['reason'])
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s banned %(stateKey)s.' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'stateKey': str(self.event['state_key'])})
		message += reasonStr
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildUnban(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s unbanned %(stateKey)s.' %
			{'timestamp': timestamp,
			'stateKey': str(self.event['state_key']),
			'sender': str(getUser(self.room, self.event['sender']).get_display_name())})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildLeave(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(stateKey)s left the room.' %
			{'timestamp': timestamp,
			'stateKey': str(self.event['state_key'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildJoin(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(username)s joined the room.' %
			{'timestamp': timestamp,
			'username': str(getUser(self.room, self.event['state_key']).get_friendly_name())})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))

	def buildMessage(self):
		if self.event['content']['msgtype'] == 'm.text':
			self.buildText()
		elif self.event['content']['msgtype'] == 'm.emote':
			self.buildEmote()
		else:
			self.buildBroken()

	def buildText(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s: %(message)s' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'message': str(self.event['content']['body'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.A_NORMAL)
		self.pad.addstr(0,0,timestamp,curses.color_pair(1)) # Just overwrite the timestamp with the dim version

	def buildEmote(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s %(message)s' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'message': str(self.event['content']['body'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.A_BOLD)
		self.pad.addstr(0,0,timestamp,curses.color_pair(1)) # Just overwrite the timestamp with the dim version

	def buildBroken(self):
		app_log.warning('Unknown event: %(event)s' %
			{'event': str(self.event)})
		message = ('%(timestamp)s: Something went wrong displaying message %(eventId)s. Check the logs for more info.' %
			{'timestamp': tsToDt(str(self.event['origin_server_ts'])),
			'eventId': str(self.event['event_id'])})
		app_log.debug('Built message: '+message)
		self.pad.addstr(0,0,message,curses.color_pair(1))
		
class Controller:
	def __init__(self, client, eventManager):
		self.client = client
		self.currentRoom = None
		self.offset = 0
		self.rooms = {}
		self.eventManager = eventManager
		self.loadedAll = [] # For keeping track of which rooms we've already loaded all the messages in

	def joinRoom(self, roomId):
		app_log.info('Joining '+str(roomId))
		self.eventManager.displayManager.statusDisplay.printJoining(roomId)
		if roomId in self.rooms: room = self.rooms[roomId]
		elif roomId in self.client.rooms: room = self.client.rooms[roomId]
		else:
			try:
				room = self.client.join_room(roomId)
				self.rooms[roomId] = room
				room.add_listener(self.eventManager.handleEvent)
				room.backfill_previous_messages(limit=self.eventManager.displayManager.messageDisplay.height*5)
				self.client.stop_listener_thread()
				self.client.start_listener_thread()
			except Exception as e:
				app_log.error('Exception while joining room: '+str(e))
				self.eventManager.displayManager.statusDisplay.printStatus('Failed to join room: '+roomId)
				room = self.currentRoom
				return
		self.currentRoom = room
		self.eventManager.displayManager.changeRoom(room)
		self.eventManager.displayManager.messageDisplay.printQueue(room, sortFirst=True)

	def changeOffset(self, amount):
		self.offset += amount
		if self.offset < 0: self.offset = 0
		messageDisplay = self.eventManager.displayManager.messageDisplay
		messageDisplay.offset = self.offset
		atTop = messageDisplay.printQueue(self.currentRoom)

		# Load more messages if queue is too short and we haven't loaded all the messages yet
		if self.currentRoom not in self.loadedAll and \
				len(messageDisplay.messageQueue[self.currentRoom.room_id]) - self.offset < messageDisplay.height*5:
			#app_log.info('Queue too short, loading more messages...')
			self.eventManager.displayManager.statusDisplay.printRoomHeader(self.currentRoom, loading=True)
			if backfill_previous_messages_and_update_batch(self.currentRoom, limit=messageDisplay.height*5) == 0:
				self.loadedAll.append(self.currentRoom)
			atTop = messageDisplay.printQueue(self.currentRoom, sortFirst=True)
			self.eventManager.displayManager.statusDisplay.printRoomHeader(self.currentRoom, loading=False)

		# Ugly hack to prevent scrolling up beyond the start of the room
		if atTop and len(messageDisplay.messageQueue[self.currentRoom.room_id]) >= messageDisplay.height:
			self.changeOffset(-1)

	def setOffset(self, num):
		self.offset = num
		self.eventManager.displayManager.messageDisplay.offset = self.offset
		self.eventManager.displayManager.messageDisplay.printQueue(self.currentRoom)

	def inputListener(self, keystroke):
		#app_log.info(keystroke)
		if keystroke == curses.KEY_ENTER or keystroke == 10:
			return(7) # Ctrl-G
		elif keystroke == curses.KEY_UP and self.eventManager.displayManager.inputBox.cursorIsAtTop:
			self.changeOffset(1)
		elif keystroke == curses.KEY_DOWN and self.eventManager.displayManager.inputBox.cursorIsAtBottom:
			self.changeOffset(-1)
		elif keystroke == curses.KEY_PPAGE:
			self.changeOffset(10)
		elif keystroke == curses.KEY_NPAGE:
			self.changeOffset(-10)
		return(keystroke)

class InputParser:
	def __init__(self, controller):
		self.controller = controller
		self.commands = {descendant.command:descendant for descendant in descendants(Command)}
		self.commands.update({alias:descendant for descendant in descendants(Command) for alias in descendant.aliases})
		app_log.info('Loaded commands, InputParser.commands = '+str(self.commands))
	
	def parse(self, text):
		text = str.strip(text)
		if not text: return
		if text[0] == '/':
			self.parseCommand(text)
		else:
			OutgoingText(text, self.controller.currentRoom, self.controller.eventManager.handleEvent, backfill=3)

	def parseCommand(self, text):
		app_log.info('Parsing input as command: '+text)
		split = text.split(' ')
		command = split[0][1:]
		args = []
		if len(split) > 1:
			args = split[1:]

		if command in self.commands:
			self.commands[command](self.controller, args)
		#if command == '/join':
		#	self.controller.joinRoom(args[0])
		else:
			app_log.warning('Invalid command string: '+text)
			# TODO: Something

class Command:
	command = None
	aliases = []
	def __init__(self, controller, args):
		app_log.info('Executing command %(command)s with args: %(args)s' %
			{'command': str(self.command),
			'args': str(args)})
		self.validate(args)
		self.execute(controller, args)
	def validate(self, args):
		pass
	def help(self):
		return('There\'s no help message for this command.')
	def execute(self, controller, args):
		raise NotImplementedError

class Join(Command):
	command = 'join'
	aliases = ['move']
	def validate(self, args):
		if len(args) != 1:
			raise IndexError('Join requires exactly one argument (destination room).')
	def help(self):
		return("""Usage: /join #room:homeserver.tld
			Join or move to another room.
			Aliases: /move""")
	def execute(self, controller, args):
		controller.joinRoom(args[0])

class Whoami(Command):
	command = 'whoami'
	def validate(self, args):
		if len(args) != 0:
			raise IndexError('Whoami requires zero arguments.')
	def help(self):
		return("""Usage: /whoami
			Print the current logged in client.""")
	def execute(self, controller, args):
		raise NotImplementedError

#logging.basicConfig(filename='nutmeg.log',level=logging.INFO)
log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')

logFile = 'logs/nutmeg.log'

my_handler = RotatingFileHandler(logFile, mode='a', maxBytes=1*1024*1024, 
                                 backupCount=10, encoding=None, delay=0)
my_handler.setFormatter(log_formatter)
my_handler.setLevel(logging.INFO)

app_log = logging.getLogger('root')
app_log.setLevel(logging.INFO)#INFO

app_log.addHandler(my_handler)
app_log.critical('***********************************')
app_log.critical('Nutmeg started, logging initialized')


def main(stdscr):
	app_log.info('curses.wrapper initialized successfully. has_colors: %(hasColours)s, can_change_color: %(changeColours)s' %
		{'hasColours': curses.has_colors(),
		'changeColours': curses.can_change_color()})

	curses.use_default_colors()
	curses.init_color(curses.COLOR_WHITE, 500, 500, 500)
	curses.init_pair(1, curses.COLOR_WHITE, -1)
	stdscr.bkgd(curses.color_pair(1))

	displayManager = DisplayManager(stdscr, 0, 0)
	# Clear screen
	stdscr.clear()
	displayManager.statusDisplay.printStatus('Loading Nutmeg...')
	stdscr.refresh()

	with open('testuser-password', 'r') as passFile:
		PASSWORD = passFile.read().strip()
	HOMESERVER = 'lrizika.com'
	USERNAME = 'testuser'
	ROOMNAME = 'test4'

	displayManager.statusDisplay.printConnecting(HOMESERVER)

	client = MatrixClient('https://%(homeServer)s' %
		{'homeServer': HOMESERVER}, cache_level=CACHE.NONE)

	displayManager.statusDisplay.printLoggingIn(USERNAME, HOMESERVER)

	# Existing user
	token = client.login_with_password(username=USERNAME, password=PASSWORD)

	displayManager.statusDisplay.printJoining('#'+ROOMNAME+':'+HOMESERVER)

	controller = Controller(client, EventManager(displayManager))

	inputParser = InputParser(controller)
	
	controller.joinRoom('#%(roomName)s:%(homeServer)s' % 
		{'roomName': ROOMNAME,
		'homeServer': HOMESERVER})

	#t = client.api.get_room_messages(controller.currentRoom.room_id, controller.currentRoom.prev_batch, direction="b", limit=10)
	#controller.currentRoom.prev_batch = t['end']
	#app_log.info(t)
	#app_log.info(client.api.get_room_messages(controller.currentRoom.room_id, controller.currentRoom.prev_batch, direction="b", limit=10))

	#tbox = displayManager.inputBox
	while True:
		#app_log.info((0,0, tbox.y,tbox.x, tbox.y+tbox.height,tbox.x+tbox.width))
		#out = displayManager.inputBox.textbox.edit(0,0, tbox.y,tbox.x, tbox.y+tbox.height-1,tbox.x+tbox.width-1, controller.inputListener)
		inp = displayManager.inputBox.textbox.edit(controller.inputListener)
		inp = stripAutoNewlines(inp, displayManager.inputBox.width)
		controller.setOffset(0)
		displayManager.inputBox.clear()
		try:
			inputParser.parse(inp)
		except Exception as e:
			app_log.warning('Exception while parsing input "%(inp)s": %(e)s' %
				{'inp': str(inp),
				'e': str(e)})



curses.wrapper(main)



