import argparse
import asyncio
import functools
import selectors
import socket
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

class ACPT:
    def __init__( self, members ):
        self.members = members

    @classmethod
    def new( cls, data ):
        members = [ChatMember( *member_data.split( " " ) ) for member_data in data.split( ":" )]
        return cls( members )

def parse_message( message ):
    message_type, _, message_data = message.partition( " " )

    if message_type == "ACPT":
        return ACPT.new( message_data )

    return None

class ServerConnection( asyncio.Protocol ):
    def __init__( self, app_model ):
        self._app_model = weakref.proxy( app_model )
        self._transport = None
        self._transport_closed = None
        self._message_chunks = []

    async def connect( self, screen_name, server_address, server_port, loop ):
        validate_screen_name( screen_name )
        validate_port( server_port )
        self._transport_closed = loop.create_future()
        self._transport, _ = await loop.create_connection( lambda: self,
            server_address,
            server_port,
            family=socket.AF_INET )

    def disconnect( self ):
        if self._transport:
            print( "Disconnecting from server." )
            self._transport.close()
            return self._transport_closed

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for server connection. Not connected to server." )
        return self._transport.get_extra_info( "sockname" )

    def send_hello( self, screen_name, local_ip, local_port ):
        self._send_server_message( f"HELO {screen_name} {local_ip} {local_port}\n" )

    def send_exit( self ):
        self._send_server_message( "EXIT\n" )

    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        print( "Disconnected from server" )
        self._transport_closed.set_result( None )
        self._transport = None
        self._transport_closed = None

    def data_received( self, data ):
        print( f"Data received: {data}" )
        for message in self._feed_data( data ):
            print( f"New message: {message}")
            message = parse_message( message )

            if isinstance( message, ACPT ):
                self._app_model.set_chat_members( message.members )

    def eof_received( self ):
        print( f"EOF received" )

    def _send_server_message( self, message ):
        if self._transport:
            self._transport.write( message.encode() )

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

class DatagramChannel( asyncio.DatagramProtocol ):
    def __init__( self, app_model ):
        self._app_model = weakref.proxy( app_model )
        self._transport = None
        self._transport_closed = None
        self._chat_members = []

    async def open( self, local_host, closed_future, loop ):
        self._transport_closed = closed_future
        self._transport, _ = await loop.create_datagram_endpoint( lambda: self, (local_host, None) )

    async def close( self ):
        if self._transport:
            print( "Closing datagram channel" )
            self._transport.close()
            return self._transport_closed

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for datagram channel. datagram channel not open." )
        return self._transport.get_extra_info( "sockname" )

    async def set_chat_members( self, members ):
        self._chat_members = members

    async def send_message( self, message ):
        pass

    def connection_made( self, transport ):
        pass

    def connection_lost( self, ex ):
        print( "Closed datagram channel" )
        future_loop = self._transport_closed.get_loop()
        future_loop.call_soon_threadsafe( self._transport_closed.set_result, None )
        self._transport = None
        self._transport_closed = None

    def datagram_received( self, data, addr ):
        print( f"Received data from {addr}: {data}" )

    def error_received( self, ex ):
        print( f"Error received: {ex}" )

    def _send_datagram_message( self, message ):
        pass

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

    def add_members( self, members ):
        self.beginInsertRows( QModelIndex(), self.rowCount(), self.rowCount() + len( members ) - 1 )
        self._members += members
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

    def __init__( self, main_loop, datagram_channel_thread, parent=None ):
        super().__init__( parent )
        self._client_stopped = main_loop.create_future()
        self._main_loop = main_loop
        self._datagram_channel_thread = datagram_channel_thread
        self._screen_name = None
        self._server_address = None
        self._server_port = None
        self._client_status = AppModel.ClientStatus.Disconnected
        self._chat_members = ChatMemberListModel()
        self._chatBuffer = ""
        self._server_connection = ServerConnection( self )
        self._datagram_channel = DatagramChannel( self )

    @pyqtProperty( bool, notify=clientStoppedChanged )
    def clientStopped( self ):
        return self._client_stopped.done()

    @pyqtProperty( "QString", notify=screenNameChanged )
    def screenName( self ):
        return self._screen_name

    @screenName.setter
    def screenName( self, screenName ):
        if self._screen_name == screenName:
            return
        self._screen_name = screenName
        self.screenNameChanged.emit()

    @pyqtProperty( "QString", notify=serverAddressChanged )
    def serverAddress( self ):
        return self._server_address

    @serverAddress.setter
    def serverAddress( self, serverAddress ):
        if self._server_address == serverAddress:
            return
        self._server_address = serverAddress
        self.serverAddressChanged.emit()

    @pyqtProperty( "QString", notify=serverPortChanged )
    def serverPort( self ):
        if self._server_port is None:
            return ""
        return str( self._server_port )

    @serverPort.setter
    def serverPort( self, serverPort ):
        if self._server_port == serverPort:
            return
        self._server_port = serverPort
        self.serverPortChanged.emit()

    @pyqtProperty( ClientStatus, notify=clientStatusChanged )
    def clientStatus( self ):
        return self._client_status

    @clientStatus.setter
    def clientStatus( self, clientStatus ):
        if self._client_status == clientStatus:
            return
        self._client_status = clientStatus
        self.clientStatusChanged.emit( clientStatus )

    @pyqtProperty( ChatMemberListModel, constant=True )
    def chatMembers( self ):
        return self._chat_members

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
            # IP used for the server connection for our UDP datagram channel since we know it's at
            # least visible to the server.
            local_host, *_ = self._server_connection.get_local_address()
            print( f"Connected to server on local address {local_host}." )

            # Here be dragons: This is where things start to get gnarly (though it's still cleaner
            # than it could've otherwise turned out). The datagram channel needs to be opened on the
            # datagram channel loop, which lives on our datagram channel thread. So we use the
            # asyncio.run_coroutine_threadsafe function to safely schedule our open method on the
            # correct event loop.
            #
            # That function returns a concurrent.futures.Future object, which is NOT the same as an
            # asyncio.Future object. Namely, you can't await it. HOWEVER, you can wrap it using
            # asyncio.wrap_future to get an asyncio.Future object, which we can then await on our
            # main loop.
            #
            # This way our main loop can asynchronously wait for the datagram channel loop to
            # establish our datagram channel. Once the open call has completed, we can then safely
            # get the port the OS gave us for that channel.
            #
            # All this because quamash's QEventLoop on Windows doesn't support creating UDP
            # endpoints. :sob:
            #
            # NOTE: The future we await on to know when the datagram channel is fully closed MUST be
            # created on the same thread as the main loop. This is because asyncio.Future objects
            # are NOT thread safe.
            #
            closed_future = self._main_loop.create_future()
            open_coro = self._datagram_channel.open( local_host, closed_future, self._datagram_channel_thread.loop )
            loop = self._datagram_channel_thread.loop
            await asyncio.wrap_future( asyncio.run_coroutine_threadsafe( open_coro, loop ) )

            _, local_port, *_ = self._datagram_channel.get_local_address()
            print( f"datagram channel port: {local_port}" )

            # Use the local port info to say hello to the server.
            self._server_connection.send_hello( screen_name, local_host, local_port )
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

        # Here be more dragons: We need to close our datagram channel on the datagram channel thread.
        # We do  this by scheduling the channel's close coroutine onto the datagram channel loop.
        # We have to use wrap_future to get a Future object that we can await on our main loop
        # (which is where this disconnect_client_async coroutine will run).
        #
        # The result of awaiting this future is the return value of the channel's close coroutine.
        # If the channel actually needed closing, that coroutine returns a DIFFERENT future, namely
        # the one we passed into the channel's open coroutine. The main loop uses this second future
        # as the one it awaits to ensure the channel is fully closed before continuing.
        #
        close_coro = self._datagram_channel.close()
        loop = self._datagram_channel_thread.loop
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

        print( "Stopping datagram channel loop" )
        self._datagram_channel_thread.loop.call_soon_threadsafe( self._datagram_channel_thread.loop.stop )

    def set_chat_members( self, members ):
        self._chat_members.clear()
        self._chat_members.add_members( members )

        # Update the channel members on the datagram channel, which runs on the datagram channel
        # thread as opposed to the main loop. Do so my scheduling a task on the datagram channel's
        # event loop.
        set_members_coro = self._datagram_channel.set_chat_members( members )
        asyncio.run_coroutine_threadsafe( set_members_coro, self._datagram_channel_thread.loop )

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
        print( f"Starting datagram channel loop in thread: {asyncio.get_event_loop()}" )
        self._datagram_channel_loop.run_forever()
        print( "Leaving datagram channel thread" )

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
