import asyncio

from .message import *
from .remoting import *
from .util import *

from PyQt5.QtCore import (Qt, QObject, QAbstractListModel, QModelIndex, QVariant,
    pyqtProperty, pyqtSignal, pyqtSlot, Q_ENUM)

class ChatMemberListModel( QAbstractListModel ):
    def __init__( self, parent=None ):
        super().__init__( parent )
        self._members = []

    def rowCount( self, parent=QModelIndex() ):
        return len( self._members )

    def data( self, index, role=Qt.DisplayRole ):
        print( f"Get data for {index.row()} and {role}" )
        if not index.isValid():
            return QVariant()

        if role == Qt.DisplayRole:
            iRow = index.row()
            return self._members[iRow].screen_name

        return QVariant()

    def add_member( self, member ):
        self.beginInsertRows( QModelIndex(), self.rowCount(), self.rowCount() )
        if member not in self._members:
            self._members.append( member )
        self.endInsertRows()

    def add_members( self, members ):
        print( self.rowCount() )
        self.beginInsertRows( QModelIndex(), self.rowCount(), self.rowCount() + len( members ) - 1 )
        self._members += members
        self.endInsertRows()

    def remove_member_by_name( self, screen_name ):
        remove_idx = None
        for (member_idx, member) in enumerate( self._members ):
            if member.screen_name == screen_name:
                remove_idx = member_idx
                break

        if remove_idx is not None:
            print( f"Removing {screen_name} from index {remove_idx} in main chat member list." )
            self.beginRemoveRows( QModelIndex(), remove_idx, remove_idx )
            del self._members[remove_idx]
            self.endRemoveRows()

    def clear( self ):
        if self.rowCount() > 0:
            #self.beginRemoveRows( QModelIndex(), 0, self.rowCount() - 1 )
            self.beginResetModel()
            self._members.clear()
            self.endResetModel()
            #self.endRemoveRows()
            print( "Cleared" )

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
        self._chat_buffer = ""
        self._server_connection = ServerConnection( self )
        self._datagram_channel = DatagramChannel( self )
        self._exit_acked = None

    @property
    def main_loop( self ):
        return self._main_loop

    @property
    def datagram_channel_loop( self ):
        return self._datagram_channel_thread.loop

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
        return self._chat_buffer

    def write_chat_error( self, error ):
        error = f"<span style='color: #DC322F'><strong>[ERROR]</strong> {error}</span>"
        self.write_to_chat_buffer( error )

    def write_chat_info( self, info ):
        info = f"<span style='color: #586E75'><strong>[INFO]</strong> {info}</span>"
        self.write_to_chat_buffer( info )

    def write_chat_message( self, message, screen_name ):
        message = f"<span style='color: #268BD2'>[{screen_name}]</span> {message}"
        self.write_to_chat_buffer( message )

    def write_to_chat_buffer( self, message ):
        self._chat_buffer += f"<p style='margin-top: 0; margin-bottom: 1em;'>{message}</p>"
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
        self.write_chat_info( "Connecting to membership server" )
        self.clientStatus = AppModel.ClientStatus.Connecting

        try:
            # Connect to the membership server over TCP.
            await self._server_connection.connect( screen_name, server_address, server_port )

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
            open_coro = self._datagram_channel.open( local_host, closed_future )
            await asyncio.wrap_future( asyncio.run_coroutine_threadsafe( open_coro, self.datagram_channel_loop ) )

            _, local_port, *_ = self._datagram_channel.get_local_address()
            print( f"Datagram channel port: {local_port}" )

            # Use the local port info to say hello to the server.
            self._server_connection.send_hello( screen_name, local_host, local_port )
        except Exception as ex:
            self.write_chat_error( str( ex ) )
            # XXX: Might need to cleanup connections here.
            self.clientStatus = AppModel.ClientStatus.Disconnected
            return

        self.write_chat_info( f"Connected to membership server {server_address}:{server_port}." )
        self.clientStatus = AppModel.ClientStatus.Connected

    @pyqtSlot()
    def disconnect_client( self, send_exit=True ):
        create_task( self.disconnect_client_async( send_exit ) )

    async def disconnect_client_async( self, send_exit=True ):
        if send_exit:
            # Tell the server we want to exit and await the acknowledgement.
            self._exit_acked = self.main_loop.create_future()
            self._server_connection.send_exit()
            print( "Awaiting exit acknowledgement" )
            await self._exit_acked
            print( "Exit acknowledged" )

        # Disconnect from the server. Wait for the disconnect to finalize.
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
        closed = await asyncio.wrap_future( asyncio.run_coroutine_threadsafe( close_coro, self.datagram_channel_loop ) )
        if closed:
            await closed

        self.clientStatus = AppModel.ClientStatus.Disconnected

    @pyqtSlot( str )
    def send_chat_message( self, message ):
        print( f"Sending message: {message}" )
        self.write_chat_message( message, self._screen_name )

        send_message_coro = self._datagram_channel.send_message( self._screen_name, message )
        asyncio.run_coroutine_threadsafe( send_message_coro, self.datagram_channel_loop )

    @pyqtSlot()
    def stop_client( self ):
        create_task( self.stop_client_async() )

    async def stop_client_async( self ):
        await self.disconnect_client_async( send_exit=(self._client_status == AppModel.ClientStatus.Connected) )

        print( "Stopping client" )
        self._client_stopped.set_result( None )
        self.clientStoppedChanged.emit()

        print( "Stopping datagram channel loop" )
        self.datagram_channel_loop.call_soon_threadsafe( self.datagram_channel_loop.stop )

    def handle_message( self, message ):
        create_task( self.handle_message_async( message ) )

    async def handle_message_async( self, message ):
        if isinstance( message, ACPT ):
            self._chat_members.clear()
            self._chat_members.add_members( message.members )

            # Update the channel members on the datagram channel, which runs on the datagram channel
            # thread as opposed to the main loop. Do so my scheduling a task on the datagram
            # channel's event loop.
            set_members_coro = self._datagram_channel.set_chat_members( message.members )
            asyncio.run_coroutine_threadsafe( set_members_coro, self.datagram_channel_loop )
        elif isinstance( message, RJCT ):
            self.write_chat_error( f"Cannot connect to server. Screen name {self._screen_name} in use." )
            # NOTE: On a RJCT, we do NOT send EXIT because the server will NOT send an
            # acknowledgement back. If we were to await an acknowledgement during our disconnection
            # logic, our client would wait indefinitely.
            self.disconnect_client( send_exit=False )
        elif isinstance( message, JOIN ):
            self.write_chat_info( f"{message.member.screen_name} has entered the chat." )
            # Don't add the member if that member is our client.
            if message.member.screen_name != self._screen_name:
                self._chat_members.add_member( message.member )

                # Also add the member to the datagram channel's list of members to send messages to.
                add_member_coro = self._datagram_channel.add_chat_member( message.member )
                asyncio.run_coroutine_threadsafe( add_member_coro, self.datagram_channel_loop )
        elif isinstance( message, EXIT ):
            self.write_chat_info( f"{message.screen_name} has left the building!" )
            if message.screen_name == self._screen_name:
                self._exit_acked.set_result( None )
            else:
                self._chat_members.remove_member_by_name( message.screen_name )

                # Also remove the member from the datagram channel's list of members.
                remove_member_coro = self._datagram_channel.remove_chat_member_by_name( message.screen_name )
                asyncio.run_coroutine_threadsafe( remove_member_coro, self.datagram_channel_loop )
        elif isinstance( message, MESG ):
            self.write_chat_message( message.message, message.screen_name )
