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

$python = Get-Command python -ErrorAction Ignore
if( -not $python ) {
    throw "Missing Python. Must install Python 3.7 to run this client."
}

$pip = Get-Command pip -ErrorAction Ignore
if( -not $pip ) {
    & $python -m ensurepip
}

$pipenv = Get-Command pipenv -ErrorAction Ignore
if( -not $pipenv ) {
    pip install pipenv
}

Push-Location $PSScriptRoot
try {
    pipenv run python client.py $ScreenName $ServerAddress $ServerPort
}
finally {
    Pop-Location
}
