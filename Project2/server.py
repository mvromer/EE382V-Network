import argparse
import asyncio
import selectors
import sys

class Server:
    def __init__( self, port ):
        self._server = None
        self._members = []
        self._port = port

def parse_command_line( argv ):
    parser = argparse.ArgumentParser( description="EE382V Project 2 Chatter Server" )
    parser.add_argument( "welcome_port",
        metavar="<welcome port>",
        help="Port number clients will use when connecting to the membership server." )

    return parser.parse_args( argv[1:] )

async def main( argv ):
    cli = parse_command_line( argv )
    print( f"Welcome port: {cli.welcome_port}" )
    server = Server( cli.welcome_port )

if __name__ == "__main__":
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop( selector )
    asyncio.set_event_loop( loop )
    asyncio.run( main( sys.argv ) )
