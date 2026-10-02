param(
    [Parameter(Mandatory=$true)]
    [ValidateRange(0,14)]
    [int]$Phase
)

$phaseMap = @{
    0  = "bootstrap"
    1  = "foundation"
    2  = "database"
    3  = "download-engine"
    4  = "platform-adapters"
    5  = "queue-worker"
    6  = "frontend"
    7  = "library-history-dedup"
    8  = "storage-drive"
    9  = "batch"
    10 = "editor"
    11 = "release"
    12 = "discover"
    13 = "similarity"
    14 = "automation"
}

$slug = $phaseMap[$Phase]
$num = "{0:D2}" -f $Phase
$branch = "phase/$num-$slug"
$prompt = "prompts/phase-$num-$slug.md"

Write-Host "Phase: $num-$slug"
Write-Host "Suggested branch: $branch"
Write-Host "Prompt: $prompt"

$existing = git branch --list $branch
if (-not $existing) {
    Write-Host "`nCreate branch with:"
    Write-Host "git checkout -b $branch"
} else {
    Write-Host "`nBranch already exists. Switch with:"
    Write-Host "git checkout $branch"
}

if (Test-Path $prompt) {
    Write-Host "`nOpening prompt..."
    Start-Process notepad.exe $prompt
}
