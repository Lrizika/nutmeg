"""
Constants to specify various things.
These could be magic numbers (and are strings), but this is clearer.
"""


# Editor modes
class MODES(str):
    pass
MODES.EDIT = MODES('EDIT')
MODES.VISUAL = MODES('VISUAL')

# Message types
# Usually these are returned as ('message', MTYPE)
class MTYPE(str):
	pass
MTYPE.MESSAGE = MTYPE('MESSAGE') # For regular chat messages
MTYPE.HELP = MTYPE('HELP') # For help messages
MTYPE.OUTPUT = MTYPE('OUTPUT') # For command output
MTYPE.ERROR = MTYPE('ERROR') # For errors



