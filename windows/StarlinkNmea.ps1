param(
    [string]$PythonPath = "python",
    [string]$ScriptPath = "$PSScriptRoot\..\starlink_nmea.py",
    [string]$Mode = "tcp",
    [string]$Host = "0.0.0.0",
    [int]$Port = 10110,
    [string]$DishHost = "",
    [int]$Interval = 1,
    [switch]$Verbose
)

$argsList = @(
    $ScriptPath,
    "--mode", $Mode,
    "--host", $Host,
    "--port", $Port,
    "--interval", $Interval
)

if ($DishHost -ne "") {
    $argsList += @("--dish-host", $DishHost)
}

if ($Verbose) {
    $argsList += "--verbose"
}

& $PythonPath @argsList
