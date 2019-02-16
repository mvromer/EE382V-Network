import asyncio
import socket
import weakref

from .message import *
from .util import *

class ServerConnection( asyncio.Protocol ):
    def __init__( self, app_model ):
        self._app_model = weakref.proxy( app_model )
        self._transport = None
        self._transport_closed = None
        self._message_chunks = []

    async def connect( self, screen_name, server_address, server_port ):
        validate_screen_name( screen_name )
        validate_port( server_port )
        self._transport_closed = self._app_model.main_loop.create_future()
        self._transport, _ = await self._app_model.main_loop.create_connection( lambda: self,
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

    def connection_lost( self, ex ):
        print( "Disconnected from server." )
        self._transport_closed.set_result( None )
        self._transport = None
        self._transport_closed = None

    def data_received( self, data ):
        print( f"TCP data received: {data}" )
        for message in self._feed_data( data ):
            print( f"New message: {message}")
            self._app_model.handle_message( parse_message( message ) )

    def eof_received( self ):
        print( f"EOF received." )

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

    async def open( self, local_host, closed_future ):
        self._transport_closed = closed_future
        self._transport, _ = await self._app_model.datagram_channel_loop.create_datagram_endpoint( lambda: self,
            (local_host, None) )

    async def close( self ):
        if self._transport:
            print( "Closing datagram channel." )
            self._transport.close()
            return self._transport_closed

    def get_local_address( self ):
        if not self._transport:
            raise RuntimeError( "Cannot get local address used for datagram channel. datagram channel not open." )
        return self._transport.get_extra_info( "sockname" )

    async def set_chat_members( self, members ):
        print( "Resetting datagram member list" )
        self._chat_members = members

    async def add_chat_member( self, member ):
        print( f"{self._chat_members}")
        if member not in self._chat_members:
            self._chat_members.append( member )
            print( f"Adding member {member.screen_name} to datagram member list" )

    async def remove_chat_member_by_name( self, screen_name ):
        remove_idx = None
        for (member_idx, member) in enumerate( self._chat_members ):
            if member.screen_name == screen_name:
                remove_idx = member_idx
                break

        if remove_idx is not None:
            print( f"Removing {screen_name} from index {remove_idx} in datagram member list." )
            del self._chat_members[remove_idx]

    async def send_message( self, screen_name, message ):
        data = f"MESG {screen_name}: {message}\n".encode()
        for member in self._chat_members:
            if member.screen_name != screen_name:
                print( f"Sending '{message}' to {member.screen_name}:{member.address}:{member.port}." )
                self._send_datagram( data, member )

    def connection_lost( self, ex ):
        print( "Closed datagram channel." )
        future_loop = self._transport_closed.get_loop()
        future_loop.call_soon_threadsafe( self._transport_closed.set_result, None )
        self._transport = None
        self._transport_closed = None

    def datagram_received( self, data, addr ):
        print( f"UDP data received from {addr}: {data}" )
        # Decode the bytes into our message and pull everything but the trailing newline.
        message = data.decode()[:-1]
        handle_message_coro = self._app_model.handle_message_async( parse_message( message ) )
        asyncio.run_coroutine_threadsafe( handle_message_coro, self._app_model.main_loop )

    def _send_datagram( self, data, member ):
        if self._transport:
            self._transport.sendto( data, (member.address, int(member.port)) )
