#!/usr/bin/python36

from matrix_client.client import MatrixClient
from datetime import datetime
import curses

import logging

def tsToDt(timestamp: str) -> str:
	"""
	Convert a timestamp string to a human-readable datetime string.
	Courtesy of https://github.com/wklaebe/redpill/blob/master/redpill.py
	
	Arguments:
		timestamp {str} -- Unix-style timestamp
	
	Returns:
		str -- Y-M-D H:M:S
	"""
	return(datetime.fromtimestamp(int(timestamp)/1000).strftime('%Y-%m-%d %H:%M:%S'))


def getEvent(room, eventId):
	for event in room.events:
		if event['event_id'] == eventId:
			return(event)
	else:
		raise IndexError('Event %(eventId)s not found. Do you need to call room.backfill_previous_messages?' %
			{'eventId': str(eventId)})

class OutgoingText:
	"""
	Object for sending outgoing messages.
	Allows for registering a handler to be called on the event ID post-sending.
	TODO: Make this properly asynchronous
	"""

	def __init__(self, text, room, completeHandler, backfill: int=0):
		self.room = room
		self.text = text
		self.eventId = self.send()['event_id']
		if backfill: room.backfill_previous_messages(limit=backfill)
		completeHandler(room, getEvent(room, self.eventId))
	def send(self):
		return(self.room.send_text(self.text))

class MessageQueue:
	def __init__(self, rooms = None):
		if rooms is None: rooms = []
		self.messages = {}
		for room in rooms: self.messages[room] = []

	def addRoom(self, room):
		if room not in self.messages:
			self.messages[room] = []
	
	def put(self, room, message: str):
		self.messages[room].append(message)

	def get(self, room, count: int=10, reverse: bool=False):
		ret = self.messages[room][-count:]
		if reverse is True: ret.reverse()
		return(ret)

class EventManager:
	"""
	Handles incoming events.
	Usage: eventManager.handleEvent(eventId)
	"""

	def __init__(self, displayManager):
		self.displayManager = displayManager
		self.handled = []

	def handleEvent(self, room, event):
		logging.info(event['event_id'])
		if event['event_id'] not in self.handled:
			logging.info(event)
			if event['type'] == 'm.room.message': 
				self.handleMessage(room, event)
			else: 
				raise TypeError('Unknown event type: %(type)s' %
					{'type': str(event['type'])})
			self.handled.append(event['event_id'])

	def handleMessage(self, room, event):
		self.displayManager.printMessage(room, event)
		


class DisplayManager:
	def __init__(self, screen, startRoom = None):
		self.screen = screen
		self.height, self.width = screen.getmaxyx()
		self.currentRoom = startRoom
		if startRoom is not None: rooms = [startRoom]
		else: rooms = None
		self.messageQueue = MessageQueue(rooms)
		
	def changeRoom(self, room):
		self.currentRoom = room
		self.messageQueue.addRoom(room)
		
	def printMessage(self, room, event):
		self.queueMessage(room, event)
		self.printQueue(room)

	def printQueue(self, room):
		self.screen.clear()
		y=0
		for message in self.messageQueue.get(room, count=self.height-1):
			self.screen.addstr(y, 0, message)
			y+=1
		self.screen.refresh()

	def queueMessage(self, room, event):
		if event['content']['msgtype'] == 'm.text':
			message = ('%(timestamp)s - %(sender)s: %(message)s' %
				{'timestamp': tsToDt(str(event['origin_server_ts'])),
				'sender': str(event['sender']),
				'message': str(event['content']['body'])})
			self.messageQueue.put(room, message)
			#self.screen.clear()
			#self.screen.addstr(0,0, message)
			#self.screen.refresh()
			#logging.info(message)
		else:
			raise TypeError('Unknown event content msgtype: %(msgtype)s' %
				{'msgtype': str(event['content']['msgtype'])})
		#else:
		#	raise NotImplementedError('Handling for messages in other rooms is not yet implemented.')



logging.basicConfig(filename='nutmeg.log',level=logging.INFO)
with open('testuser-password', 'r') as passFile:
	PASSWORD = passFile.read().strip()
HOMESERVER = 'matrix.lrizika.com'
USERNAME = 'testuser'
ROOMNAME = 'test2'

def main(stdscr):
	# Clear screen
	stdscr.clear()

	client = MatrixClient('https://%(homeServer)s' %
		{'homeServer': HOMESERVER})

	# Existing user
	token = client.login_with_password(username=USERNAME, password=PASSWORD)

	room = client.join_room('#%(roomName)s:%(homeServer)s' % 
		{'roomName': ROOMNAME,
		'homeServer': HOMESERVER})
	#room.add_listener(print)
	displayManager = DisplayManager(stdscr, startRoom=room)
	eventManager = EventManager(displayManager)
	room.add_listener(eventManager.handleEvent)
	room.backfill_previous_messages(limit=displayManager.height) #TODO: Have this backfill up to max height

	try:
		OutgoingText('Hallo!', room, eventManager.handleEvent, backfill=3)
	except:
		logging.error(room.events)
		raise

	client.start_listener_thread()

	while True:
		stdscr.refresh()
		stdscr.getkey()

curses.wrapper(main)



