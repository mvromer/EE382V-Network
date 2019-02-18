# Chatter Client
This client implementation requires Python 3.7 to run. Please ensure you have Python 3.7 installed
and that it is the version of Python that is first available on your path.

## Repository
This project is also hosted on GitHub at the following location:
https://github.com/mvromer/EE382V-Network

## Prerequisites
The client itself basically requires the following:

* Python 3.7
* PyQt 5.11 (available via PyPi)
* Quamash 0.6.1 (also available via PyPi)

### Install Pip
To install packages from PyPi, you must install Pip, Python's package manager. With newer versions
of Python on most platforms, this can be easily done like so:

```
python -m ensurepip
```

This may require administrative rights to run dependin on where you have Python installed. On some
environments (notably Ubuntu), Pip must be installed via a package using your operating system's
package manager. If this is the case for you, please install Pip via whatever is the most approriate
means for your environment.

### Install PyQt and Quamash
Once Pip is installed, the PyQt and Quamash libraries can be installed with the following commands:

```
pip install PyQt5==5.11.3
pip install Quamash==0.6.1
```

### Windows Specific Setup
On Windows, you **MUST** create a firewall rule that allows inbound UDP traffic. It can either be a
global rule that allows ALL inbound UDP traffic or a rule that provides finer grained access.
Failure to create a rule will cause the client to hang when it tries to disconnect from the server
because it will wait indefinitely for a UDP message from the server acknowledging the client's
request to exit. In this case, the client process will need to be killed.

The important thing is that the rule needs to allow inbound UDP traffic for the Python interpreter's
executable running the client, so please keep this in mind if creating a fine-grained firewall rule.

As will be described later one, the Windows driver provided will attempt to automate the creation of
the necessary firewall rules.

## Basic Usage
Once all the prerequisites are in place, this client can be run from within the same directory as
this readme with the following command:

```
python client.py <screen name> <server host> <server port>
```

Once the client is loaded, clicking the `Connect` button will cause the client to connect to the
server join its chat room. Clicking `Disconnect` will disconnect the client from the server. Chat
messages can be entered in the text field at the bottom of the window. The client can be exited by
clicking the close button (OS dependent) within the client's title bar.

## Running in an Isolated Environment
The above works well if you have a Python environment you don't mind installing directly into.
However, this project also allows for running the client in an isolated Python environment. This
is enabled through a Python package called Pipenv (https://pipenv.readthedocs.io/en/latest/).

**NOTE:** This is the preferred way of running the client as it provides for the greatest
reproducability.

Pipenv is responsible for creating an isolated virtual Python environment for a project and
installing its dependencies into that environment. The project's code is then run within that
virtual environment, providing it isolation from any other Python environments on the system.

In order to run the client within its isolated environment, do **not** install the PyQt5 and
Quamash dependencies listed above. Instead, install Pipenv into your Python 3.7 environment like so:

```
pip install pipenv
```

This project provides a Pipfile which is used by Pipenv to setup the project's virtual environment.
Manual steps for creating the environment via Pipenv and running the client are provided below. They
will work on all platforms.

Alternatively, I have attempted to make some runtime drivers to make the setup of the virtual
environment and execution of the client more automated. If possible it is **highly** recommended
you run the client via one of the drivers.

## Runtime Drivers
These drivers already assume you have Python 3.7 installed on your path. Additional requirements
are specified for the OS-specific notes.

### Windows Driver
The Windows driver is provided as a PowerShell script. It only requires Python 3.7 is available on
your path. It will do the extra work of ensuring Pip is installed and performing the following on
an as-needed basis:

* Installing Pipenv
* Creating the client's virtual Python environment
* Creating a Windows Firewall rule for allowing inbound UDP traffic to the Python interpreter in the
  client's virtual environment.
* Installing the client's dependencies within the virtual environment.
* Running the client.

The driver can be called within the same directory as this readme with the following command:

```
.\Invoke-Chatter.ps1 <screen name> <server host> <server port>
```

### Linux Driver
Given each major Linux distribution has different ways of acquiring Python 3.7 and Pip, no single
driver is provided. Instead, you must essentially follow the manual steps provided below, which
involve ensuring Python 3.7, Pip, and Pipenv are installed and available from your path. Afterward,
the Pipenv commands are called to setup the virtual environment and run the client.

I am also working on a Docker container that will hopefully make running the client simpler on a
Linux environment. However, that will not be available immediately at the time this project is
submitted.

## Manual Setup (If all else fails)
First ensure Python 3.7 is installed and available from your path. Then you need to ensure Pip is
installed. On most platforms, Pip can be installed via the following (assuming `python` is name of
your Python 3.7 interpreter available on your path):

```
python -m ensurepip
```

Some platforms (notably Ubuntu) require you installing Pip as a separate package from your
distribution's package manager. If that's the case, you will need to install Pip via the most
appropriate method for your environment.

Once Pip is installed, you can install Pipenv like so:

```
pip install pipenv
```

Depending on where you installed Python 3.7, you may need to run the above either in an elevated
prompt (like on Windows) or run it via `sudo` (on a Linux system).

Once Pipenv is installed, the client's virual environment can then be created and the client run
with the following commands (execute them from the same directory containing this readme):

```
pipenv install --skip-lock
pipenv run python client.py <screen name> <server host> <server port>
```

Subsequent runs only need the `pipenv run` command.
