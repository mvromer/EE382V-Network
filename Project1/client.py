import argparse
import asyncio
import sys
import warnings

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlApplicationEngine
from quamash import QEventLoop

class AppModel( QObject ):
    screenNameChanged = pyqtSignal()
    serverAddressChanged = pyqtSignal()
    serverPortChanged = pyqtSignal()

    def __init__( self, parent=None ):
        super().__init__( parent )
        self._screenName = None
        self._serverAddress = None
        self._serverPort = None

    @pyqtProperty( "QString", notify=screenNameChanged )
    def screenName( self ):
        return self._screenName

    @screenName.setter
    def screenName( self, screenName ):
        if self._screenName == screenName:
            return
        self._screenName = screenName
        self.screenNameChanged.emit()

    @pyqtProperty( "QString", notify=serverAddressChanged )
    def serverAddress( self ):
        return self._serverAddress

    @serverAddress.setter
    def serverAddress( self, serverAddress ):
        if self._serverAddress == serverAddress:
            return
        self._serverAddress = serverAddress
        self.serverAddressChanged.emit()

    @pyqtProperty( "QString", notify=serverPortChanged )
    def serverPort( self ):
        if self._serverPort is None:
            return ""
        return str( self._serverPort )

    @serverPort.setter
    def serverPort( self, serverPort ):
        # If the given value is a string, which we'd be receiving from a view binding, covert it to
        # an integer first. If the conversion fails, we warn and return. If the given value as an
        # integer is not positive, we warn and return.
        if isinstance( serverPort, str ):
            try:
                serverPort = int( serverPort )
            except:
                warnings.warn( f"Given server port '{serverPort}' is not a valid port number." )
                return

        if serverPort <= 0:
            warnings.warn( f"Given server port '{serverPort}' is not a valid port number." )
            return

        if self._serverPort == serverPort:
            return
        self._serverPort = serverPort
        self.serverPortChanged.emit()

class ClientApp( QGuiApplication ):
    def __init__( self, arguments ):
        super().__init__( arguments )
        self.app_model = AppModel()
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
