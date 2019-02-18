<#
.SYNOPSIS
Runs the chat client.

.PARAMETER ScreenName
Desired screen name.

.PARAMETER ServerAddress
Host name or IPv4 address of the membership server to connect to.

.PARAMETER ServerPort
Remote port on membership server to connect to initially.

#>
[CmdletBinding()]
param(
    [Parameter( Mandatory )]
    [string] $ScreenName,

    [Parameter( Mandatory )]
    [string] $ServerAddress,

    [Parameter( Mandatory )]
    [string] $ServerPort
)

$ErrorActionPreference = "Stop"

# Make sure we have Python.
$python = Get-Command python -ErrorAction Ignore
if( -not $python ) {
    throw "Missing Python. Must install Python 3.7 to run this client."
}

# Make sure we have the required version of Python.
$installedVersion = & $python -c "from sys import version_info as v; print( '%s.%s' % (v.major, v.minor) )"
if( $installedVersion -ne "3.7" ) {
    throw ("Wrong version of Python found (version found: $installedVersion). " +
        "Ensure Python 3.7 is the first available version on the path.")
}

# Make sure we have pip.
$pip = Get-Command pip -ErrorAction Ignore
if( -not $pip ) {
    & $python -m ensurepip
}

# Make sure we have pipenv.
$pipenv = Get-Command pipenv -ErrorAction Ignore
if( -not $pipenv ) {
    pip install pipenv
}

Push-Location $PSScriptRoot
try {
    pipenv install --skip-lock
    pipenv run python client.py $ScreenName $ServerAddress $ServerPort
}
finally {
    Pop-Location
}
