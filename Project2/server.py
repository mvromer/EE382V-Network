import argparse
import asyncio
import platform
import selectors
import signal
import socket
import sys
import warnings
import weakref

class HELO:
    def __init__( self, screen_name, ip_address, port ):
        self.screen_name = screen_name
        self.ip_address = ip_address
        self.port = int(port)

    @classmethod
    def new( cls, data ):
        return cls( *data.split( " " ) )

class EXIT:
    @classmethod
    def new( cls, data ):
        return cls()

def parse_message( message ):
    try:
        message_type, _, message_data = message.partition( " " )

        if message_type == "HELO":
            return HELO.new( message_data )
        elif message_type == "EXIT":
            return EXIT.new( message_data )
    except:
        # If the message wasn't anything we recognized or was badly formatted, then we just drop it.
        pass

class Member:
    def __init__( self, screen_name, ip_address, port ):
        self.screen_name = screen_name
        self.ip_address = ip_address
        self.port = port

class MemberConnection( asyncio.Protocol ):
    def __init__( self, server ):
        self._server = weakref.proxy( server )
        self._transport = None
        self._transport_closed = None
        self._message_chunks = []

    @property
    def address( self ):
        return self._transport.get_extra_info( "sockname" ) if self._transport else None

    def disconnect( self ):
        if self._transport:
            self._transport.close()
            return self._transport_closed

    def send_accept( self, members ):
        if self._transport:
            message = f"ACPT {':'.join( f'{member.screen_name} {member.ip_address} {member.port}' for member in members)}\n"
            self._transport.write( message.encode() )

    def send_reject( self, screen_name ):
        if self._transport:
            message = f"RJCT {screen_name}\n"
            self._transport.write( message.encode() )

    def connection_made( self, transport ):
        self._transport = transport
        self._transport_closed = asyncio.get_event_loop().create_future()
        self._server.register_connection( self )

    def connection_lost( self, ex ):
        self._server.unregister_connection( self )
        self._transport_closed.set_result( None )
        self._transport = None
        self._transport_closed = None

    def data_received( self, data ):
        for message in self._feed_data( data ):
            print( f"New message: {message}" )
            message = parse_message( message )
            if message:
                self._server.handle_message( message, self )

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
    def __init__( self ):
        self._transport = None
        self._transport_closed = None

    async def open( self ):
        loop = asyncio.get_running_loop()
        self._transport_closed = loop.create_future()
        self._transport, _ = await loop.create_datagram_endpoint( lambda: self, local_addr=("0.0.0.0", None) )

    async def close( self ):
        if self._transport:
            self._transport.close()
            return self._transport_closed

    def send_join( self, new_member, members ):
        message = f"JOIN {new_member.screen_name} {new_member.ip_address} {new_member.port}\n"
        data = message.encode()
        for member in members:
            self._send_datagram( data, member )

    def send_exit( self, departing_member, members ):
        message = f"EXIT {departing_member.screen_name}\n"
        data = message.encode()
        for member in members:
            self._send_datagram( data, member )

    def connection_lost( self, ex ):
        self._transport_closed.set_result( None )
        self._transport = None
        self._transport_closed = None

    def _send_datagram( self, data, member ):
        if self._transport:
            self._transport.sendto( data, (member.ip_address, member.port) )

class Server:
    def __init__( self, port ):
        self._port = port
        self._server = None
        self._connections = {}
        self._datagram_channel = None
        self._members = []

    async def run( self ):
        # Setup the datagram channel for sending JOIN and EXIT messages to clients.
        self._datagram_channel = DatagramChannel()
        await self._datagram_channel.open()

        # Setup the listening socket for new clients.
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server( lambda: MemberConnection( self ), port=self._port )

        # Windows requires a dirty hack to ensure the keyboard interrupt (Ctrl+C) results in the
        # event loop shutting down, even when it would normally be in an idle state (for instance,
        # when it's waiting for data to be available on a socket). This basically allows the event
        # loop to wake up periodically and respond to any keyboard interrupts that might have
        # occurred.
        #
        # Learned about this workaround from here: https://stackoverflow.com/a/36925722/562685
        #
        if platform.system() == "Windows":
            loop.create_task( self._wakeup() )

        async with self._server:
            await self._server.serve_forever()

    async def shutdown( self ):
        if self._connections:
            await asyncio.gather( *[conn.disconnect() for conn in self._connections] )

        self._server.close()
        await self._server.wait_closed()
        await self._datagram_channel.close()

    def register_connection( self, conn ):
        if conn in self._connections:
            warnings.warn( f"Connection already registered: {conn.address}" )
            return
        self._connections[conn] = None

    def unregister_connection( self, conn ):
        if conn in self._connections:
            member = self._connections[conn]
            if member:
                self._members.remove( member )
            del self._connections[conn]

    def handle_message( self, message, conn ):
        async def handle_message():
            if isinstance( message, HELO ):
                # Ignore this if this connection has already registered itself as a member.
                if self._connections.get( conn, None ):
                    warnings.warn( f"Connection {conn.address} already registered as member. Ignoring HELO." )
                    return

                for member in self._members:
                    if member.screen_name == message.screen_name:
                        conn.send_reject( message.screen_name )
                        await conn.disconnect()
                        break
                else:
                    member = Member( message.screen_name, message.ip_address, message.port )
                    self._connections[conn] = member
                    self._members.append( member )

                    conn.send_accept( self._members )
                    self._datagram_channel.send_join( member, self._members )
            elif isinstance( message, EXIT ):
                # Ignore this if this connection has never registered itself previously.
                if not self._connections.get( conn, None ):
                    warnings.warn( f"Connection {conn.address} never registered as member. Ignoring EXIT." )
                    return

                departing_member = self._connections[conn]
                self._datagram_channel.send_exit( departing_member, self._members )

        self._create_task( handle_message() )

    def _create_task( self, coro ):
        self._server.get_loop().create_task( coro )

    async def _wakeup( self ):
        while True:
            await asyncio.sleep( 1 )

def parse_command_line( argv ):
    parser = argparse.ArgumentParser( description="EE382V Project 2 Chatter Server" )
    parser.add_argument( "welcome_port",
        metavar="<welcome port>",
        help="Port number clients will use when connecting to the membership server." )

    return parser.parse_args( argv[1:] )

def main( argv ):
    # Make sure we pick the Select based event loop since that's the only one on Windows that
    # support UDP transports.
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop( selector )
    asyncio.set_event_loop( loop )

    cli = parse_command_line( argv )
    server = Server( cli.welcome_port )

    try:
        loop.run_until_complete( server.run() )
    except KeyboardInterrupt:
        loop.run_until_complete( server.shutdown() )

if __name__ == "__main__":
    main( sys.argv )
