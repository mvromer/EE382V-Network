import asyncio
import selectors
import sys

async def client():
    pass

class Server:
    def __init__( self ):
        self._server = None

    async def run( self ):
        self._server = await asyncio.start_server( self.handle_client, "localhost", 5000 )

        loop = self._server.get_loop()
        loop.create_task( self._wakeup() )

        async with self._server:
            await self._server.serve_forever()

    async def handle_client( self, reader, writer ):
        data = await reader.readline()
        message = data.decode()
        print( f"Message: {message}" )
        await asyncio.sleep( 10 )
        writer.write( "Reponse".encode() )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def shutdown( self ):
        self._server.close()
        await self._server.wait_closed()

    async def _wakeup( self ):
        while True:
            await asyncio.sleep( 1 )

class Client:
    def __init__( self ):
        pass

    async def run( self ):
        _, writer = await asyncio.open_connection( "localhost", 5000 )
        writer.write( "CHELO message\n".encode() )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def shutdown( self ):
        pass

def client_main():
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop( selector )
    asyncio.set_event_loop( loop )

    client = Client()

    try:
        loop.run_until_complete( client.run() )
    except KeyboardInterrupt:
        print( "Caught interrupt" )
        loop.run_until_complete( client.shutdown() )

def server_main():
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop( selector )
    asyncio.set_event_loop( loop )

    server = Server()

    try:
        loop.run_until_complete( server.run() )
    except KeyboardInterrupt:
        print( "Caught interrupt" )
        loop.run_until_complete( server.shutdown() )

if __name__ == "__main__":
    if sys.argv[1] == "server":
        server_main()
    else:
        client_main()
