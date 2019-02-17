#!/bin/bash

function usage
{
    echo "Usage: chatter-client.sh <screen name> <server address> <server port>"
    echo
    echo "Driver for Chatter chat client. Requires Python 3.7 installed in order to run."
    echo "Client's screen name is given by <screen name>. The host name or IPv4 address of the"
    echo "membership server is given by <server address>. The port on which the membership server"
    echo "is listening is given by <server port>."
    echo
}

PYTHON=`which python3`
if [ -z "$PYTHON" ]; then
    PYTHON=`which python`

    if [ -z "$PYTHON" ]; then
        echo "Missing Python. Must install Python 3.7 to run this client."
        exit 1
    fi
fi

PIP=`which pip`
