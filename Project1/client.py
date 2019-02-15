import argparse
import asyncio
import functools
import selectors
import string
import sys
import threading
import warnings
import weakref

from PyQt5.QtCore import (Qt, QObject, QAbstractListModel, QModelIndex, QVariant,
    pyqtProperty, pyqtSignal, pyqtSlot, Q_ENUM)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlApplicationEngine, qmlRegisterUncreatableType
from quamash import QEventLoop

def create_task( coro ):
    # This is a workaround for adding coroutines as tasks to a quamash QEventLoop. The problem is
    # for whatever reason a QEventLoop is registered as the currently running loop when the
    # asyncio.get_running_loop function is called. This is called by asyncio.create_task which
    # results in a RuntimeError being raised.
    #
    # However, asyncio.get_event_loop will return the QEventLoop instance. Once we have the loop
    # instance, we can use the create_task method on it to concurrently schedule the given coroutine
    # on the event loop.
    #
    return asyncio.get_event_loop().create_task( coro )

def validate_screen_name( screen_name ):
    if not all( c not in string.whitespace for c in screen_name ):
        raise ValueError( f"Invalid screen name {screen_name}. Screen name cannot have spaces." )

def validate_port( port ):
    # Try to convert the port to an integer and validate that it's positive.
    port = int( port )
    if port <= 0:
        raise ValueError( f"Invalid server port number {port}." )

class ServerConnection( asyncio.Protocol ):
    def __init__( self, app_model ):
        self._app_model = weakref.proxy( app_model )
        self._transport = None

    async def connect( self, screen_name, server_address, server_port ):
        validate_screen_name( screen_name )
        validate_port( server_port )

        loop = asyncio.get_event_loop()
        self._transport, _ = await loop.create_connection( self.get_protocol_instance, server_address, server_port )

    def get_protocol_instance( self ):
        return self

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for server connection. Not connected to server." )
        return self._transport.get_extra_info( "sockname")

    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        self._transport = None

    def data_received( self, data ):
        print( f"Data received: {data}" )

    def eof_received( self ):
        print( f"EOF received" )

class MessageChannel( asyncio.DatagramProtocol ):
    def __init__( self, app_model ):
        self._app_model = weakref.proxy( app_model )
        self._transport = None

    async def open( self, local_host ):
        loop = asyncio.get_event_loop()
        self._transport = await loop.create_datagram_endpoint( self.get_protocol_instance, (local_host, None) )

    def get_protocol_instance( self ):
        return self

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for message channel. Message channel not open." )
        return self._transport.get_extra_info( "sockname")

    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        self._transport = None

    def datagram_received( self, data, addr ):
        print( f"Received data from {addr}: {data}" )

    def error_received( self, ex ):
        print( f"Error received: {ex}" )

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

    def __init__( self, message_channel_thread, parent=None ):
        super().__init__( parent )
        self._message_channel_thread = message_channel_thread
        self._screenName = None
        self._serverAddress = None
        self._serverPort = None
        self._clientStatus = AppModel.ClientStatus.Disconnected
        self._chatMembers = ChatMemberListModel()
        self._chatBuffer = ""
        self._server_connection = ServerConnection( self )
        self._message_channel = MessageChannel( self )

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

        # Schedule to connect to the server in the background so that we aren't blocking the UI.
        create_task( self.connect_to_server_async( screen_name, server_address, server_port ) )

    async def connect_to_server_async( self, screen_name, server_address, server_port ):
        self.append_info( "Connecting to membership server" )
        self.clientStatus = AppModel.ClientStatus.Connecting

        try:
            # Connect to the membership server over TCP.
            await self._server_connection.connect( screen_name, server_address, server_port )

            # Use catch-all to properly handle both IPv4 and IPv6 address tuples. Use the local host
            # IP used for the server connection since we know it's at least visible to the server.
            # Use it to setup our UDP message channel.
            local_host, *_ = self._server_connection.get_local_address()
            print( f"Connected to server on local address {local_host}." )
            #await self._message_channel.open( local_host )
            #_, port_channel, *_ = self._message_channel.get_local_address()
            #print( f"Message channel port: {port_channel}" )
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.append_error( str( ex ) )
            return

        self.append_info( f"Connected to membership server {server_address}:{server_port}." )
        self.clientStatus = AppModel.ClientStatus.Connected

    @pyqtSlot()
    def disconnect_from_server( self ):
        print( "Disconnecting from membership server" )
        self.clientStatus = AppModel.ClientStatus.Disconnected

    @pyqtSlot( str )
    def send_chat_message( self, message ):
        print( f"Sending message: {message}" )
        self.append_info( message )

    @pyqtSlot()
    def stop_message_channel_loop( self ):
        print( "Stopping message channel loop" )
        self._message_channel_thread.loop.call_soon_threadsafe( self._message_channel_thread.loop.stop )

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

class MessageChannelThread( threading.Thread ):
    def __init__( self, message_channel_loop ):
        super().__init__()
        self._message_channel_loop = message_channel_loop

    @property
    def loop( self ):
        return self._message_channel_loop

    def run( self ):
        asyncio.set_event_loop( self._message_channel_loop )
        print( f"Starting message channel loop in thread: {asyncio.get_event_loop()}" )
        self._message_channel_loop.run_forever()
        print( "Leaving message channel thread" )

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
    message_channel_loop = asyncio.SelectorEventLoop( selectors.SelectSelector() )
    message_channel_thread = MessageChannelThread( message_channel_loop )

    # Create the top-level app model state for the chat client.
    app_model = AppModel( message_channel_thread )

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
        message_channel_thread.start()
        main_loop.run_forever()
        message_channel_thread.join()
        print( "Leaving app" )

if __name__ == "__main__":
    main( sys.argv )
