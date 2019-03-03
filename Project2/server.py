import argparse
import asyncio
import platform
import selectors
import signal
import sys
import warnings
import weakref

class HELO:
    def __init__( self, screen_name, client_ip, client_port ):
        self.screen_name = screen_name
        self.client_ip = client_ip
        self.client_port = client_port

    @classmethod
    def new( cls, data ):
        return cls( *data.split( " " ) )

class EXIT:
    @classmethod
    def new( cls, data ):
        return cls()

def parse_message( message ):
    try:
        message_type, _, message_data = message.partition( " " )

        if message_type == "HELO":
            return HELO.new( message_data )
        elif message_type == "EXIT":
            return EXIT.new( message_data )
    except:
        # If the message wasn't anything we recognized or was badly formatted, then we just drop it.
        pass

class Member:
    pass

class MemberConnection( asyncio.Protocol ):
    def __init__( self, server ):
        self._server = weakref.proxy( server )
        self._transport = None
        self._message_chunks = []
        self._conn_id = None

    def connection_made( self, transport ):
        self._conn_id = transport.get_extra_info( "sockname" )
        print( f"Connection made: {self._conn_id}" )
        self._server.register_connection( self._conn_id )

    def connection_lost( self, ex ):
        print( "Connection lost" )
        self._server.unregister_connection( self._conn_id )

    def data_received( self, data ):
        print( "Data received" )
        for message in self._feed_data( data ):
            print( f"New message: {message}")
            message = parse_message( message )
            if message:
                self._server.create_task( self._server.handle_message( message, self._conn_id ) )

    def _feed_data( self, data ):
        # We keep feeding chunks until one contains at least one newline character. The presence of
        # a newline indicates that at least one complete message has arrived. In this case, we want
        # to find the last newline in the current chunk and preserve everything after it as the
        # start of the next message that has yet to be completed.
        #
        # For everything before the last newline, this gets concatenated with the other message
        # chunks previously stored. The concatenated string is then split across newline boundaries
        # (since it may be the rare case there are mutliple messages buffered up), and each portion
        # corresponds to a protocol message that needs parsing.
        #
        chunk = data.decode()
        left_chunk, newline, right_chunk = chunk.rpartition( "\n" )

        if newline:
            # There was a newline in the latest chunk. The one we partitioned on is either at the
            # beginning of our chunk (in which case left_chunk is empty), it's at the end of our
            # chunk (in which case right_chunk is empty), or it's somewhere in the middle.

            if left_chunk:
                # There is content prior to the newline we partitioned on. The preceding content
                # needs to be appened to the list of chunks that will be concatenated and parsed.
                self._message_chunks.append( left_chunk )

            # Concatenate all of our message chunks into one large string. Split the string on
            # message boundaries (newlines) and yield each message found.
            for message in "".join( self._message_chunks ).split( "\n" ):
                yield message

            # Discard the chunks we've exhausted in terms of messages that can be parsed.
            self._message_chunks = []

            if right_chunk:
                # There is content following the newline we partitioned on. This content forms the
                # first chunk save in the new set of message chunks.
                self._message_chunks.append( right_chunk )
        else:
            # There was no newline in the current chunk. Add it to our list of message chunks.
            self._message_chunks.append( chunk )

class Server:
    def __init__( self, port ):
        self._port = port
        self._server = None
        self._connections = {}
        self._members = []

    async def run( self ):
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server( lambda: MemberConnection( self ), port=self._port )

        # Windows requires a dirty hack to ensure the keyboard interrupt (Ctrl+C) results in the
        # event loop shutting down, even when it would normally be in an idle state (for instance,
        # when it's waiting for data to be available on a socket). This basically allows the event
        # loop to wake up periodically and respond to any keyboard interrupts that might have
        # occurred.
        #
        # Learned about this workaround from here: https://stackoverflow.com/a/36925722/562685
        #
        if platform.system() == "Windows":
            loop.create_task( self._wakeup() )

        async with self._server:
            print( "Starting server" )
            await self._server.serve_forever()

    async def shutdown( self ):
        print( "Shutting down server" )
        self._server.close()
        await self._server.wait_closed()
        print( "Server closed" )

    def create_task( self, coro ):
        self._server.get_event_loop().create_task( coro )

    def register_connection( self, conn_id ):
        if conn_id in self._connections:
            warnings.warn( f"Connection already registered: {conn_id}" )
            return

        self._connections[conn_id] = Member()

    def unregister_connection( self, conn_id ):
        if conn_id in self._connections:
            del self._connections[conn_id]

    async def handle_message( self, message, conn_id ):
        if isinstance( message, HELO ):
            pass
        elif isinstance( message, EXIT ):
            pass

    async def _wakeup( self ):
        while True:
            await asyncio.sleep( 1 )

def parse_command_line( argv ):
    parser = argparse.ArgumentParser( description="EE382V Project 2 Chatter Server" )
    parser.add_argument( "welcome_port",
        metavar="<welcome port>",
        help="Port number clients will use when connecting to the membership server." )

    return parser.parse_args( argv[1:] )

def main( argv ):
    # Make sure we pick the Select based event loop since that's the only one on Windows that
    # support UDP transports.
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop( selector )
    asyncio.set_event_loop( loop )

    cli = parse_command_line( argv )
    server = Server( cli.welcome_port )

    try:
        loop.run_until_complete( server.run() )
    except KeyboardInterrupt:
        print( "Caught KI" )
        loop.run_until_complete( server.shutdown() )

if __name__ == "__main__":
    main( sys.argv )
