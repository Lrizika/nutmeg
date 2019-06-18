#!/usr/bin/python36
try:
	from .control import Controller
	from .input import Parser
except ImportError:
	from control import Controller
	from input import Parser
from matrix_client.client import MatrixClient, CACHE
from matrix_client.errors import MatrixHttpLibError
import curses
from curses import textpad

import logging
from logging.handlers import RotatingFileHandler

LOGFILE = 'logs/nutmeg.log'

def startLog(file):
	log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s')

	my_handler = RotatingFileHandler(file, mode='a', maxBytes=1*1024*1024, 
									backupCount=10, encoding=None, delay=0)
	my_handler.setFormatter(log_formatter)
	my_handler.setLevel(logging.DEBUG)

	app_log = logging.getLogger('root')
	app_log.setLevel(logging.DEBUG)

	app_log.addHandler(my_handler)
	app_log.critical('***********************************')
	app_log.critical('Nutmeg started, logging initialized')
	return(app_log)

def main(screen):
	app_log = startLog(LOGFILE)

	with open('testuser-password', 'r') as passFile:
		PASSWORD = passFile.read().strip()
	HOMESERVER = 'lrizika.com'
	USERNAME = 'testuser'
	ROOMNAME = '#test4:lrizika.com'
	app_log.info('Building Controller...')
	controller = Controller(screen, HOMESERVER, username=USERNAME, password=PASSWORD)
	inputParser = Parser(controller)
	controller.stateManager.joinRoom(ROOMNAME)
	while(True):
		out = inputParser.inputBox.textbox.edit(inputParser.getListener())
		inputParser.inputBox.clear()
		inputParser.parse(out)

if __name__ == '__main__':
	curses.wrapper(main)


