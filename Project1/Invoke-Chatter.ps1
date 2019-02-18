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

    # Get the Python executable in the virtual environment so that we can open up UPD access to it.
    $virtualEnvPath = pipenv --venv
    $virtualEnvName = Split-Path -Path $virtualEnvPath -Leaf
    $virtualEnvPython = Get-Item -Path "$virtualEnvPath\Scripts\python.exe" -ErrorAction Ignore
    if( -not $virtualEnvPython ) {
        throw ("Python not found in the named virtual environment under $virtualEnvPython. " +
            "Make sure the virtual environment was created properly.")
    }

    # Open up inbound UDP access to the virtual environment's Python interpreter so that the client
    # runs properly.
    $ruleName = "Chatter Client - $virtualEnvName"
    $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction Ignore
    if( -not $rule ) {
        Write-Host -ForegroundColor Yellow "Creating new firewall rule to allow UDP traffic to virtual environment's Python."
        Write-Host -ForegroundColor Yellow "New rule will have the display name '$ruleName'"

        Start-Process powershell.exe -Verb RunAs -ArgumentList "-Command & { New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Program '$virtualEnvPython' -Action Allow -Protocol UDP }"
    }

    pipenv run python client.py $ScreenName $ServerAddress $ServerPort
}
finally {
    Pop-Location
}
