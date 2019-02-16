import asyncio
import string

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
