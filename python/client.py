#!/usr/bin/python36

from matrix_client.client import MatrixClient
import datetime
import curses
from curses import textpad

import logging


#
# Utility Functions
#
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
	return(newText)


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
		self.eventId = room.send_text(text)['event_id']
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
			logging.info('Handling event: '+event['event_id'])
			if event['type'] == 'm.room.message': 
				self.handleMessage(room, event)
			else:
				logging.error('Unknown event type: %(type)s' %
					{'type': str(event['type'])})
			self.handled.append(event['event_id'])
		else:
			logging.info('Already handled event: '+event['event_id'])
		self.displayManager.screen.move(oldY, oldX)
		self.displayManager.screen.refresh()

	def handleMessage(self, room, event):
		self.displayManager.messageDisplay.printMessage(room, event)
		
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
		messageX = 10
		messageWidth = self.width - messageX
		self.messageScreen = curses.newwin(messageHeight, messageWidth, messageY, messageX)
		self.messageDisplay = MessageDisplay(self.messageScreen, messageY, messageX)#, self.messageQueue)
		if startRoom is not None: self.changeRoom(startRoom)
		
	def changeRoom(self, room):
		self.currentRoom = room
		#self.messageQueue.addRoom(room)
		self.currentRoom.update_room_name()
		self.currentRoom.update_room_topic()
		self.currentRoom.update_aliases()
		self.statusDisplay.printRoomHeader(room)

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

	def printStatus(self, status):
		logging.info('Status: '+status)
		self.screen.clear()
		self.screen.addstr(0,0,status,curses.color_pair(1))
		self.screen.refresh()
	
	def printRoomHeader(self, room):
		status = ('%(user)s - %(roomName)s - %(topic)s' %
			{'user': str(getUser(room, room.client.user_id).get_display_name()),
			'roomName': str(room.display_name),
			'topic': str(room.topic)})
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

	def printJoining(self, room, server):
		status = ('Joining #%(roomName)s:%(homeServer)s...' % 
			{'roomName': room,
			'homeServer': server})
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
		self.printQueue(room)

	def printQueue(self, room):
		self.screen.clear()
		self.screen.refresh()
		y=self.height + self.y
		queue = list(reversed(self.messageQueue[room]))[self.offset:self.height+self.offset]
		# TODO: Load more messages if queue is too short
		for message in queue:#.get(room, count=self.height):
			y -= message.printHeight
			if y+message.printHeight<=self.y: break
			message.pad.refresh(max(0, self.y-y),0, max(y, self.y),self.x, max(y+message.printHeight-1, self.y),self.width+self.x)
			#logging.info((max(0, self.y-y),0, max(y, self.y),self.x, max(y+message.printHeight-1, self.y),self.width+self.x))
			
	def queueMessage(self, room, event):
		if room not in self.messageQueue: self.messageQueue[room] = []
		
		messagePad = curses.newpad(self.height, self.width)
		self.messageQueue[room].append(Message(messagePad, room, event))
		#else:
		#	raise NotImplementedError('Handling for messages in other rooms is not yet implemented.')

class Message:
	def __init__(self, pad, room, event):
		self.event = event
		self.room = room
		self.pad = pad
		self.height, self.width = pad.getmaxyx()
		self.build()
		try:
			self.printHeight = getLastChar(self.pad)[0]+1
		except IndexError:
			self.printHeight = 0

	def build(self):
		if self.event['content']['msgtype'] == 'm.text':
			self.buildText()
		elif self.event['content']['msgtype'] == 'm.emote':
			self.buildEmote()
		else:
			logging.warning('Unknown event content msgtype "%(msgtype)s" while building message for event: %(event)s' %
				{'msgtype': str(self.event['content']['msgtype']),
				'event': str(self.event)})
			self.buildBroken()

	def buildText(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s: %(message)s' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'message': str(self.event['content']['body'])})
		self.pad.addstr(0,0,message,curses.A_NORMAL)
		self.pad.addstr(0,0,timestamp,curses.color_pair(1)) # Just overwrite the timestamp with the dim version
		logging.info('Built message: '+message)

	def buildEmote(self):
		timestamp = tsToDt(str(self.event['origin_server_ts'])) + ' -'
		message = ('%(timestamp)s %(sender)s %(message)s' %
			{'timestamp': timestamp,
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'message': str(self.event['content']['body'])})
		self.pad.addstr(0,0,message,curses.A_BOLD)
		self.pad.addstr(0,0,timestamp,curses.color_pair(1)) # Just overwrite the timestamp with the dim version
		logging.info('Built message: '+message)

	def buildBroken(self):
		message = ('%(timestamp)s: Something went wrong displaying message %(eventId)s from %(sender)s. Check the logs for more info.' %
			{'timestamp': tsToDt(str(self.event['origin_server_ts'])),
			'sender': str(getUser(self.room, self.event['sender']).get_display_name()),
			'eventId': str(self.event['event_id'])})
		self.pad.addstr(0,0,message)
		logging.info('Built message: '+message)
		
class Controller:
	def __init__(self, client, eventManager):
		self.client = client
		self.currentRoom = None
		self.offset = 0
		self.rooms = []
		self.eventManager = eventManager

	def joinRoom(self, roomId):
		room = self.client.join_room(roomId)
		self.currentRoom = room
		if room not in self.rooms:
			room.add_listener(self.eventManager.handleEvent)
			room.backfill_previous_messages(limit=self.eventManager.displayManager.messageDisplay.height+10)
		self.rooms.append(room)
		self.eventManager.displayManager.changeRoom(room)
		self.client.stop_listener_thread()
		self.client.start_listener_thread()

	def changeOffset(self, amount):
		self.offset += amount
		if self.offset < 0: self.offset = 0
		self.eventManager.displayManager.messageDisplay.offset = self.offset
		self.eventManager.displayManager.messageDisplay.printQueue(self.currentRoom)

	def setOffset(self, num):
		self.offset = num
		self.eventManager.displayManager.messageDisplay.offset = self.offset
		self.eventManager.displayManager.messageDisplay.printQueue(self.currentRoom)

	def inputListener(self, keystroke):
		#logging.info(keystroke)
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


logging.basicConfig(filename='nutmeg.log',level=logging.INFO)

def main(stdscr):
	logging.info('curses.wrapper initialized successfully. has_colors: %(hasColours)s, can_change_color: %(changeColours)s' %
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
	HOMESERVER = 'matrix.lrizika.com'
	USERNAME = 'testuser'
	ROOMNAME = 'test2'

	displayManager.statusDisplay.printConnecting(HOMESERVER)

	client = MatrixClient('https://%(homeServer)s' %
		{'homeServer': HOMESERVER})

	displayManager.statusDisplay.printLoggingIn(USERNAME, HOMESERVER)

	# Existing user
	token = client.login_with_password(username=USERNAME, password=PASSWORD)

	displayManager.statusDisplay.printJoining(ROOMNAME, HOMESERVER)

	controller = Controller(client, EventManager(displayManager))
	
	controller.joinRoom('#%(roomName)s:%(homeServer)s' % 
		{'roomName': ROOMNAME,
		'homeServer': HOMESERVER})

	#tbox = displayManager.inputBox
	while True:
		#logging.info((0,0, tbox.y,tbox.x, tbox.y+tbox.height,tbox.x+tbox.width))
		#out = displayManager.inputBox.textbox.edit(0,0, tbox.y,tbox.x, tbox.y+tbox.height-1,tbox.x+tbox.width-1, controller.inputListener)
		out = displayManager.inputBox.textbox.edit(controller.inputListener)
		out = stripAutoNewlines(out, displayManager.inputBox.width)
		controller.setOffset(0)
		displayManager.inputBox.clear()
		if out:
			OutgoingText(out, controller.currentRoom, controller.eventManager.handleEvent, backfill=3)

curses.wrapper(main)



