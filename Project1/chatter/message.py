from .member import *

class ACPT:
    def __init__( self, members ):
        self.members = members

    @classmethod
    def new( cls, data ):
        members = [ChatMember( *member_data.split( " " ) ) for member_data in data.split( ":" )]
        return cls( members )

class RJCT:
    def __init__( self, screen_name ):
        self.screen_name = screen_name

    @classmethod
    def new( cls, data ):
        return cls( screen_name=data )

class JOIN:
    def __init__( self, member ):
        self.member = member

    @classmethod
    def new( cls, data ):
        return cls( ChatMember( *data.split( " " ) ) )

class EXIT:
    def __init__( self, screen_name ):
        self.screen_name = screen_name

    @classmethod
    def new( cls, data ):
        return cls( screen_name=data )

class MESG:
    def __init__( self, screen_name, message ):
        self.screen_name = screen_name
        self.message = message

    @classmethod
    def new( cls, data ):
        screen_name, _, message = data.partition( ": " )
        return cls( screen_name, message )

def parse_message( message ):
    message_type, _, message_data = message.partition( " " )

    if message_type == "ACPT":
        return ACPT.new( message_data )
    elif message_type == "RJCT":
        return RJCT.new( message_data )
    elif message_type == "JOIN":
        return JOIN.new( message_data )
    elif message_type == "EXIT":
        return EXIT.new( message_data )
    elif message_type == "MESG":
        return MESG.new( message_data )
