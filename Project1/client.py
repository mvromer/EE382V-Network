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
        self._transport_closed = None

    async def connect( self, screen_name, server_address, server_port, loop ):
        validate_screen_name( screen_name )
        validate_port( server_port )
        self._transport_closed = loop.create_future()
        self._transport, _ = await loop.create_connection( lambda: self, server_address, server_port )

    def disconnect( self ):
        if self._transport:
            print( "Disconnecting from server." )
            self._transport.close()
            return self._transport_closed

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for server connection. Not connected to server." )
        return self._transport.get_extra_info( "sockname" )

    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        print( "Disconnected from server" )
        self._transport_closed.set_result( None )
        self._transport = None
        self._transport_closed = None

    def data_received( self, data ):
        print( f"Data received: {data}" )

    def eof_received( self ):
        print( f"EOF received" )

class MessageChannel( asyncio.DatagramProtocol ):
    def __init__( self, app_model ):
        self._app_model = weakref.proxy( app_model )
        self._transport = None
        self._transport_closed = None

    async def open( self, local_host, closed_future, loop ):
        self._transport_closed = closed_future
        self._transport, _ = await loop.create_datagram_endpoint( lambda: self, (local_host, None) )

    async def close( self ):
        if self._transport:
            print( "Closing message channel" )
            self._transport.close()
            return self._transport_closed

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for message channel. Message channel not open." )
        return self._transport.get_extra_info( "sockname" )

    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        print( "Closed message channel" )
        future_loop = self._transport_closed.get_loop()
        future_loop.call_soon_threadsafe( self._transport_closed.set_result, None )
        self._transport = None
        self._transport_closed = None

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

    clientStoppedChanged = pyqtSignal()
    screenNameChanged = pyqtSignal()
    serverAddressChanged = pyqtSignal()
    serverPortChanged = pyqtSignal()
    clientStatusChanged = pyqtSignal( ClientStatus, arguments=["clientStatus"] )
    chatBufferChanged = pyqtSignal()

    def __init__( self, main_loop, message_channel_thread, parent=None ):
        super().__init__( parent )
        self._client_stopped = main_loop.create_future()
        self._main_loop = main_loop
        self._message_channel_thread = message_channel_thread
        self._screenName = None
        self._serverAddress = None
        self._serverPort = None
        self._clientStatus = AppModel.ClientStatus.Disconnected
        self._chatMembers = ChatMemberListModel()
        self._chatBuffer = ""
        self._server_connection = ServerConnection( self )
        self._message_channel = MessageChannel( self )

    @pyqtProperty( bool, notify=clientStoppedChanged )
    def clientStopped( self ):
        return self._client_stopped.done()

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
    def connect_client( self ):
        # Trim all the connection parameters.
        screen_name = self.screenName.strip()
        server_address = self.serverAddress.strip()
        server_port = self.serverPort.strip()

        # Asynchronously connect our client.
        create_task( self.connect_client_async( screen_name, server_address, server_port ) )

    async def connect_client_async( self, screen_name, server_address, server_port ):
        self.append_info( "Connecting to membership server" )
        self.clientStatus = AppModel.ClientStatus.Connecting

        try:
            # Connect to the membership server over TCP.
            await self._server_connection.connect( screen_name, server_address, server_port, self._main_loop )

            # Use catch-all to properly handle both IPv4 and IPv6 address tuples. Use the local host
            # IP used for the server connection for our UDP message channel since we know it's at
            # least visible to the server.
            local_host, *_ = self._server_connection.get_local_address()
            print( f"Connected to server on local address {local_host}." )

            # Here be dragons: This is where things start to get gnarly (though it's still cleaner
            # than it could've otherwise turned out). The message channel needs to be opened on the
            # message channel loop, which lives on our message channel thread. So we use the
            # asyncio.run_coroutine_threadsafe function to safely schedule our open method on the
            # correct event loop.
            #
            # That function returns a concurrent.futures.Future object, which is NOT the same as an
            # asyncio.Future object. Namely, you can't await it. HOWEVER, you can wrap it using
            # asyncio.wrap_future to get an asyncio.Future object, which we can then await on our
            # main loop.
            #
            # This way our main loop can asynchronously wait for the message channel loop to
            # establish our message channel. Once the open call has completed, we can then safely
            # get the port the OS gave us for that channel.
            #
            # All this because quamash's QEventLoop on Windows doesn't support creating UDP
            # endpoints. :sob:
            #
            # NOTE: The future we await on to know when the message channel is fully closed MUST be
            # created on the same thread as the main loop. This is because asyncio.Future objects
            # are NOT thread safe.
            #
            closed_future = self._main_loop.create_future()
            open_coro = self._message_channel.open( local_host, closed_future, self._message_channel_thread.loop )
            loop = self._message_channel_thread.loop
            await asyncio.wrap_future( asyncio.run_coroutine_threadsafe( open_coro, loop ) )

            _, port_channel, *_ = self._message_channel.get_local_address()
            print( f"Message channel port: {port_channel}" )
        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.append_error( str( ex ) )
            return

        self.append_info( f"Connected to membership server {server_address}:{server_port}." )
        self.clientStatus = AppModel.ClientStatus.Connected

    @pyqtSlot()
    def disconnect_client( self ):
        create_task( self.disconnect_client_async() )

    async def disconnect_client_async( self ):
        # Only await if we're actually disconnecting. We might not be if we never connected.
        disconnected = self._server_connection.disconnect()
        if disconnected:
            await disconnected

        # Here be more dragons: We need to close our message channel on the message channel thread.
        # We do  this by scheduling the channel's close coroutine onto the message channel loop.
        # We have to use wrap_future to get a Future object that we can await on our main loop
        # (which is where this disconnect_client_async coroutine will run).
        #
        # The result of awaiting this future is the return value of the channel's close coroutine.
        # If the channel actually needed closing, that coroutine returns a DIFFERENT future, namely
        # the one we passed into the channel's open coroutine. The main loop uses this second future
        # as the one it awaits to ensure the channel is fully closed before continuing.
        #
        close_coro = self._message_channel.close()
        loop = self._message_channel_thread.loop
        closed = await asyncio.wrap_future( asyncio.run_coroutine_threadsafe( close_coro, loop ) )
        if closed:
            print( f"Future: {closed}" )
            await closed

        self.clientStatus = AppModel.ClientStatus.Disconnected

    @pyqtSlot( str )
    def send_chat_message( self, message ):
        print( f"Sending message: {message}" )
        self.append_info( message )

    @pyqtSlot()
    def stop_client( self ):
        create_task( self.stop_client_async() )

    async def stop_client_async( self ):
        await self.disconnect_client_async()

        print( "Stopping client" )
        self._client_stopped.set_result( None )
        self.clientStoppedChanged.emit()

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
    app_model = AppModel( main_loop, message_channel_thread )

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
        main_loop.run_until_complete( app_model._client_stopped )
        message_channel_thread.join()
        print( "Leaving app" )

if __name__ == "__main__":
    main( sys.argv )
