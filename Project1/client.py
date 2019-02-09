import argparse
import asyncio
import sys

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlApplicationEngine
from quamash import QEventLoop

class ClientApp( QGuiApplication ):
    def __init__( self, arguments ):
        super().__init__( arguments )
        self.cli = self._parse_command_line()

    def _parse_command_line( self ):
        parser = argparse.ArgumentParser( description="EE382V Project 1 Chatter Client" )
        parser.add_argument( "screen_name",
            metavar="<screen name>",
            help="Screen name to use when connecting to the chat membership server." )

        parser.add_argument( "server_host",
            metavar="<server host>",
            help="IP address or hostname of chat membership server to connect to." )

        parser.add_argument( "server_port",
            type=int,
            metavar="<server port>",
            help="Port on the chat membership server to connect to" )

        arguments = self.arguments()
        return parser.parse_args( arguments[1:] )

class ClientMembershipProtocol( asyncio.Protocol ):
    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        pass

    def data_received( self, data ):
        pass

    def eof_received( self, data ):
        pass

def main():
    app = ClientApp( sys.argv )
    engine = QQmlApplicationEngine( "client.qml" )
    loop = QEventLoop( app )
    asyncio.set_event_loop( loop )

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
