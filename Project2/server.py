import argparse
import asyncio
import platform
import selectors
import signal
import sys

class HELO:
    def __init__( self, screen_name, client_ip, client_port ):
        self.screen_name = screen_name
        self.client_ip = client_ip
        self.client_port = client_port

    @classmethod
    def new( cls, data ):
        return cls( *data.split( " " ) )

def parse_message( message ):
    message_type, _, message_data = message.partition( " " )

    if message_type == "HELO":
        return HELO.new( message_data )

class Member:
    pass

class Server:
    def __init__( self, port ):
        self._port = port
        self._server = None
        self._members = []

    async def run( self ):
        self._server = await asyncio.start_server( self._on_client_connected, port=self._port )

        # Windows requires a dirty hack to ensure the keyboard interrupt (Ctrl+C) results in the
        # event loop shutting down, even when it would normally be in an idle state (for instance,
        # when it's waiting for data to be available on a socket). This basically allows the event
        # loop to wake up periodically and respond to any keyboard interrupts that might have
        # occurred.
        #
        # Learned about this workaround from here: https://stackoverflow.com/a/36925722/562685
        #
        if platform.system() == "Windows":
            loop = self._server.get_loop()
            loop.create_task( self._wakeup() )

        async with self._server:
            print( "Starting server" )
            await self._server.serve_forever()

    async def shutdown( self ):
        print( "Shutting down server" )
        self._server.close()
        await self._server.wait_closed()
        print( "Server closed" )

    async def _on_client_connected( self, reader, writer ):
        print( "Client connected" )
        message = await reader.readline()
        print( f"Read: {message}" )
        writer.close()
        await writer.wait_closed()

    def _handle_message( self, message ):
        if isinstance( message, HELO ):
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
