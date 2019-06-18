import datetime
import matrix_client.room
import matrix_client.user

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

def buildTypeTree(cls:type) -> dict:
	"""
	Return a tree of subclasses of a class
	
	Arguments:
		cls (type): Class from which to return descendants
	
	Returns:
		dict: Dict of all subclasses

	Example: 
		buildTypeTree(MainClass) returns: 
		{
			MainClass.SubClass1: {
				MainClass.SubClass1.SubClass11: {},
				MainClass.SubClass1.SubClass12: {}
			},
			MainClass.SubClass2: {}
		}
	"""

	typeTree = {}
	for subclass in cls.__subclasses__():
		typeTree[subclass] = buildTypeTree(subclass)
	return(typeTree)

def checkStructure(item:dict, structure:dict) -> bool:
	"""
	Checks if a dict's structure matches a given structure definition.
		Yes, this is basically just reinventing a schema library.
	
	Args:
		item (dict): Item to check structure of
		structure (dict): Structure required
			Format:
			{
				'key': type,
				'key2': {
					'key3': 'RequiredValue'
				}
			}
	
	Returns:
		bool: Whether the structure matches
	"""

	for key in structure:
		# If we're missing a key, structure's wrong
		if key not in item: return(False)

		if isinstance(structure[key], type):
			# If a value is supposed to be a given type and isn't, structure's wrong
			if not isinstance(item[key], structure[key]): return(False)
		elif isinstance(structure[key], dict):
			# If a value is a dictionary, we recurse down instead
			if not checkStructure(item[key], structure[key]): return(False)
		else:
			# If a value has a required value, check if that's equal
			if item[key] != structure[key]: return(False)
	
	# If every key is correct, we're good
	return(True)

def tsToDt(timestamp: str) -> str:
	"""
	Convert a timestamp string to a human-readable string.
	Returns timestamps from today as H:M:S, and earlier as Y-M-D
	
	Arguments:
		timestamp (str): Unix-style timestamp
	
	Returns:
		str: Y-M-D or H:M:S
	"""
	dt = datetime.datetime.fromtimestamp(int(timestamp)/1000)
	if datetime.datetime.today().date() == dt.date():
		return(dt.strftime('%H:%M:%S'))
	return(dt.strftime('%Y-%m-%d'))
	#return(dt.strftime('%Y-%m-%d %H:%M:%S'))

def nowToTs() -> str:
	"""
	Returns the current time as a Matrix-compatible timestamp.
	
	Returns:
		str: Timestamp
	"""
	dtTs = datetime.datetime.timestamp(datetime.datetime.now())
	ts = str(dtTs*1000)
	return(ts)

def getEvent(room: matrix_client.room.Room, eventId: str) -> dict:
	"""
	Gets an event from a room by event ID.
	
	Arguments:
		room (matrix_client.room.Room): Room in which to look for the event
		eventId (str): Matrix event ID
	
	Raises:
		KeyError: If the event is not found in the room's events.
			Usually this is because it's not been backfilled in yet.
	
	Returns:
		dict: The event dict
	"""

	for event in room.events:
		if event['event_id'] == eventId:
			return(event)
	else:
		raise KeyError('Event %(eventId)s not found. Do you need to call room.backfill_previous_messages?' %
			{'eventId': str(eventId)})

def getMember(room: matrix_client.room.Room, userId: str) -> matrix_client.user.User:
	"""
	Gets a member of a room by user ID.
	
	Arguments:
		room (matrix_client.room.Room): Room from which to retrieve the member
		userId (str): Matrix user ID
	
	Raises:
		KeyError: If the user is not found

	Returns:
		matrix_client.user.User
	"""

	for member in room.get_joined_members():
		if member.user_id == userId:
			return(member)
	else:
		raise KeyError('User %(userId)s not found in room %(roomName)s (%(roomId)s).' %
			{'userId': str(userId),
			'roomName': str(room.display_name),
			'roomId': str(room.room_id)})

def getLastChar(window) -> tuple:
	"""
	Returns the last filled character in a window object.
	
	Arguments:
		window (curses.window): The window to check

	Raises:
		IndexError
	
	Returns:
		tuple (y,x): The (y,x) of the last filled character, relative to the window
	"""

	height, width = window.getmaxyx()
	for y in range(height, -1, -1):
		for x in range(width, -1, -1):
			if window.instr(y,x,1) != b' ':
				return(y,x)
	raise IndexError('No filled characters in window.')
def getLastChar2(window) -> tuple:
	"""
	Returns the last filled character in a window object.
	
	Arguments:
		window (curses.window): The window to check

	Raises:
		IndexError
	
	Returns:
		tuple (y,x): The (y,x) of the last filled character, relative to the window
	"""
	lastYX = None
	height, width = window.getmaxyx()
	for y in range(height):
		for x in range(width):
			if window.instr(y,x,1) != b' ':
				lastYX = (y,x)
	if lastYX is None: raise IndexError('No filled characters in window.')
	return(lastYX)

def stripAutoNewlines(text: str, interval: int) -> str:
	"""
	Removes newlines that are automatically added by Textpads on linewrap
	
	Arguments:
		text (str): Input string
		interval (int): Interval at which to remove newlines. 
			Usually equal to the Textpad's window width
			That is, window.getmaxyx()[1]

	Returns:
		str: Stripped string
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
	Modified from matrix_client.room.backfill_previous_messages

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