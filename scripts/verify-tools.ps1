$ErrorActionPreference = "Continue"

function Check-Cmd($name, $args = @("--version")) {
    Write-Host "`n== $name =="
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "MISSING: $name" -ForegroundColor Red
        return $false
    }
    try {
        & $name @args
        return $true
    } catch {
        Write-Host "FOUND but version check failed: $name" -ForegroundColor Yellow
        return $false
    }
}

$results = @{}
$results["git"] = Check-Cmd "git"
$results["python"] = Check-Cmd "python"
$results["node"] = Check-Cmd "node"
$results["npm"] = Check-Cmd "npm"
$results["ffmpeg"] = Check-Cmd "ffmpeg" @("-version")
$results["ffprobe"] = Check-Cmd "ffprobe" @("-version")
$results["docker"] = Check-Cmd "docker"

Write-Host "`n=== Summary ==="
$results.GetEnumerator() | Sort-Object Name | ForEach-Object {
    $status = if ($_.Value) { "OK" } else { "MISSING/FAILED" }
    Write-Host "$($_.Name): $status"
}

Write-Host "`nRequired before media phases: git, python, node/npm, ffmpeg, ffprobe."
Write-Host "Docker is optional for early local development."
