class ChatMember:
    def __init__( self, screen_name, address, port ):
        self.screen_name = screen_name
        self.address = address
        self.port = port

    def __eq__( self, other ):
        if isinstance( other, ChatMember ):
            return self.screen_name == other.screen_name
