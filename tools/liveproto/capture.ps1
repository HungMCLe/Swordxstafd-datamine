# Capture Sword x Staff game traffic on this PC with Windows' built-in pktmon, then convert it to pcapng.
# Must run elevated (pktmon needs admin). Only the game ports are recorded; nothing else is touched.
#
#   powershell -ExecutionPolicy Bypass -File tools\liveproto\capture.ps1 -Seconds 120 -OutDir C:\cap
#
# Then:  python tools\liveproto\parse.py C:\cap\game.pcapng C:\cap\streams.json
#        python tools\liveproto\gproto.py decode C:\cap\streams.json C:\cap\decoded.json
param(
    [int]$Seconds = 120,
    [string]$OutDir = (Join-Path $PSScriptRoot "..\..\out\liveproto")
)
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "pktmon needs an elevated shell. Run this from an administrator PowerShell."
    exit 1
}
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
$etl = Join-Path $OutDir "game.etl"
$pcap = Join-Path $OutDir "game.pcapng"
pktmon stop 2>$null | Out-Null
pktmon filter remove | Out-Null
pktmon filter add -p 8033 | Out-Null   # planes server, primary host
pktmon filter add -p 9033 | Out-Null   # planes server, backup host
pktmon start --capture --pkt-size 0 -f $etl | Out-Null
$stop = Join-Path $OutDir "stop.txt"
Remove-Item -Force -ErrorAction SilentlyContinue $stop
Write-Host "Capturing game traffic for up to $Seconds seconds. Do things in the game now (open the Arena, view opponents...)."
Write-Host "It stops early when a file named stop.txt appears in $OutDir."
for ($i = $Seconds; $i -gt 0; $i--) {
    Write-Host -NoNewline "`r$i s left   "
    Start-Sleep -Seconds 1
    if (Test-Path $stop) { Write-Host "`nstop.txt seen, finishing."; break }
}
pktmon stop | Out-Null
pktmon filter remove | Out-Null
pktmon etl2pcap $etl -o $pcap | Out-Null
"done $(Get-Date -Format s)" | Out-File (Join-Path $OutDir "done.txt")
Write-Host "`nWrote $pcap"
