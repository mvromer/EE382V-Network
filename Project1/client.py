import argparse
import asyncio
import string
import sys
import warnings

from PyQt5.QtCore import (Qt, QObject, QAbstractListModel, QModelIndex, QVariant,
    pyqtProperty, pyqtSignal, pyqtSlot, Q_ENUM)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlApplicationEngine, qmlRegisterUncreatableType
from quamash import QEventLoop

def is_valid_screen_name( screen_name ):
    return all( c not in string.whitespace for c in screen_name )

class ChatMember:
    def __init__( self, screen_name, address, port ):
        self.screenName = screen_name
        self.address = address
        self.port = port

class ChatMemberListModel( QAbstractListModel ):
    def __init__( self, parent=None ):
        super().__init__( parent )
        self._members = []

    def rowCount( self, parent=QModelIndex() ):
        return len( self._members )

    def data( self, index, role=Qt.DisplayRole ):
        if not index.isValid():
            return QVariant()

        if role == Qt.DisplayRole:
            iRow = index.row()
            return self._members[iRow].screenName

        return QVariant()

    def add_member( self, member ):
        self.beginInsertRows( QModelIndex(), self.rowCount(), self.rowCount() )
        self._members.append( member )
        self.endInsertRows()

    def clear( self ):
        if self.rowCount() > 0:
            self.beginRemoveRows( QModelIndex(), 0, self.rowCount() - 1 )
            self._members = []
            self.endRemoveRows()

class AppModel( QObject ):
    class ClientStatus:
        Connected, Connecting, Disconnected = range( 3 )

    Q_ENUM( ClientStatus )

    screenNameChanged = pyqtSignal()
    serverAddressChanged = pyqtSignal()
    serverPortChanged = pyqtSignal()
    clientStatusChanged = pyqtSignal( ClientStatus, arguments=["clientStatus"] )
    chatBufferChanged = pyqtSignal()

    def __init__( self, parent=None ):
        super().__init__( parent )
        self._screenName = None
        self._serverAddress = None
        self._serverPort = None
        self._clientStatus = AppModel.ClientStatus.Disconnected
        self._chatMembers = ChatMemberListModel()
        self._chatBuffer = ""

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
        if self._serverPort == serverPort:
            return
        self._serverPort = serverPort
        self.serverPortChanged.emit()

    @pyqtProperty( ClientStatus, notify=clientStatusChanged )
    def clientStatus( self ):
        return self._clientStatus

    @clientStatus.setter
    def clientStatus( self, clientStatus ):
        if self._clientStatus == clientStatus:
            return
        self._clientStatus = clientStatus
        self.clientStatusChanged.emit( clientStatus )

    @pyqtProperty( ChatMemberListModel, constant=True )
    def chatMembers( self ):
        return self._chatMembers

    @pyqtProperty( "QString", notify=chatBufferChanged )
    def chatBuffer( self ):
        return self._chatBuffer

    def append_error( self, message ):
        message = f"<span style='color: #DC322F'><strong>[ERROR]</strong> {message}</span>"
        self.append_message( message )

    def append_info( self, message ):
        message = f"<span style='color: #586E75'><strong>[INFO]</strong> {message}</span>"
        self.append_message( message )

    def append_message( self, message, error=False ):
        self._chatBuffer += f"<p style='margin-top: 0; margin-bottom: 1em;'>{message}</p>"
        self.chatBufferChanged.emit()

    @pyqtSlot()
    def connect_to_server( self ):
        # Trim all the connection parameters.
        screen_name = self.screenName.strip()
        server_address = self.serverAddress.strip()
        server_port = self.serverPort.strip()

        # Screen names can't have spaces in them, otherwise they'd balls up the protocol.
        if not is_valid_screen_name( screen_name ):
            self.append_error( f"Invalid screen name {screen_name}. Screen name cannot have spaces." )
            return

        # Try to convert the port to an integer and validate that it's positive.
        try:
            server_port = int( server_port )
        except:
            self.append_error( f"Invalid server port number {server_port}." )
            return

        if server_port <= 0:
            self.append_error( f"Invalid server port number {server_port}." )
            return

        self.append_info( "Connecting to membership server" )
        self.clientStatus = AppModel.ClientStatus.Connecting
        self.clientStatus = AppModel.ClientStatus.Connected

    @pyqtSlot()
    def disconnect_from_server( self ):
        print( "Disconnecting from membership server" )
        self.clientStatus = AppModel.ClientStatus.Disconnected

    @pyqtSlot( str )
    def send_chat_message( self, message ):
        print( f"Sending message: {message}" )
        self.append_info( message )

class ClientApp( QGuiApplication ):
    def __init__( self, arguments ):
        super().__init__( arguments )
        self.app_model = AppModel()
        self._parse_command_line()

    def _parse_command_line( self ):
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
        cli = parser.parse_args( arguments[1:] )
        self.app_model.screenName = cli.screen_name
        self.app_model.serverAddress = cli.server_address
        self.app_model.serverPort = cli.server_port

class ChatClientProtocol( asyncio.Protocol ):
    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        pass

    def data_received( self, data ):
        pass

    def eof_received( self, data ):
        pass

def main( argv ):
    app = ClientApp( argv )
    qmlRegisterUncreatableType( AppModel, "Chatter.Client", 1, 0, "AppModel", "AppModel cannot be craeted in QML." )
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty( "appModel", app.app_model )
    engine.load( "client.qml" )
    loop = QEventLoop( app )
    asyncio.set_event_loop( loop )

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main( sys.argv )
