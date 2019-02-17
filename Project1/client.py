import argparse
import asyncio
import selectors
import sys
import threading

from chatter.util import *
from chatter.message import *
from chatter.model import *
from chatter.remoting import *

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlApplicationEngine, qmlRegisterUncreatableType
from quamash import QEventLoop

class ClientApp( QGuiApplication ):
    def __init__( self, arguments ):
        super().__init__( arguments )

    def parse_command_line( self ):
        parser = argparse.ArgumentParser( description="EE382V Project 1 Chatter Client" )
        parser.add_argument( "screen_name",
            metavar="<screen name>",
            help="Screen name to use when connecting to the chat membership server." )

        parser.add_argument( "server_address",
            metavar="<server address>",
            help="IP address or hostname of chat membership server to connect to." )

        parser.add_argument( "server_port",
            metavar="<server port>",
            help="Port on the chat membership server to connect to" )

        # argparse parser wants only the command line arguments. Typically the app arguments, which
        # were initialized from sys.argv, also contain as the first entry the name of the script
        # that was executed. We strip that off before calling the command line parser.
        arguments = self.arguments()
        return parser.parse_args( arguments[1:] )

class DatagramChannelThread( threading.Thread ):
    def __init__( self, datagram_channel_loop ):
        super().__init__()
        self._datagram_channel_loop = datagram_channel_loop

    @property
    def loop( self ):
        return self._datagram_channel_loop

    def run( self ):
        asyncio.set_event_loop( self._datagram_channel_loop )
        print( f"Starting datagram channel loop in thread." )
        self._datagram_channel_loop.run_forever()
        print( "Leaving datagram channel thread." )

def main( argv ):
    # Setup the main event loop that will drive the chat client.
    app = ClientApp( argv )
    main_loop = QEventLoop( app )
    asyncio.set_event_loop( main_loop )

    # Through a brilliant stroke of misfortune, it turns out on Windows the quamash library, which
    # provides the asyncio event loop that interops with Qt, derives from asyncio's ProactorEventLoop,
    # which does NOT support the creation of datagram (UDP) endpoints. If it were possible to change
    # the loop to one based on SelectorEventLoop, then UDP endpoints could be supported, but that's
    # outside my control.
    #
    # To avoid gutting the asynchronous code from the app and starting over with a different socket
    # API, we setup a separate thread to handle UDP traffic with a SelectorEventLoop. We then
    # communicate between the two event loops by submitting coroutines as tasks to the appropriate
    # event loop. It sucks and is ugly but better than rearchitecting late in the game.
    #
    datagram_channel_loop = asyncio.SelectorEventLoop( selectors.SelectSelector() )
    datagram_channel_thread = DatagramChannelThread( datagram_channel_loop )

    # Create the top-level app model state for the chat client.
    app_model = AppModel( main_loop, datagram_channel_thread )

    cli = app.parse_command_line()
    app_model.screenName = cli.screen_name
    app_model.serverAddress = cli.server_address
    app_model.serverPort = cli.server_port

    # Initialize the UI.
    qmlRegisterUncreatableType( AppModel, "Chatter.Client", 1, 0, "AppModel", "AppModel cannot be craeted in QML." )
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty( "appModel", app_model )
    engine.load( "client.qml" )

    with main_loop:
        datagram_channel_thread.start()
        main_loop.run_until_complete( app_model._client_stopped )
        datagram_channel_thread.join()
        print( "Leaving app" )

if __name__ == "__main__":
    main( sys.argv )
