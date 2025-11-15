$ErrorActionPreference = "Stop"

$OWNER = "collinerasmus"
$REPO = "rdwc-v4"
$OUTDIR = "${REPO}-checks-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Force -Path $OUTDIR | Out-Null

Write-Host "Checking gh CLI authentication..."
try {
    gh auth status 2>&1 | Out-Null
    $GH_AVAILABLE = $true
    Write-Host "✓ gh CLI is authenticated"
} catch {
    $GH_AVAILABLE = $false
    Write-Host "✗ gh CLI not available or not authenticated"
    if (-not $env:GITHUB_TOKEN) {
        Write-Error "ERROR: gh CLI not authenticated and GITHUB_TOKEN not set. Export GITHUB_TOKEN or run 'gh auth login' and re-run."
        exit 1
    }
}

function Call-API {
    param([string]$Path)
    
    if ($GH_AVAILABLE) {
        try {
            return gh api $Path 2>$null
        } catch {
            Write-Warning "gh api call failed for $Path : $_"
            return "{}"
        }
    } else {
        if (-not $env:GITHUB_TOKEN) {
            Write-Error "GITHUB_TOKEN not set"
            return "{}"
        }
        try {
            $headers = @{Authorization = "token $env:GITHUB_TOKEN"}
            $response = Invoke-RestMethod -Uri "https://api.github.com${Path}" -Headers $headers
            return $response | ConvertTo-Json -Depth 100
        } catch {
            Write-Warning "API call failed for $Path : $_"
            return "{}"
        }
    }
}

Write-Host "Collecting repo metadata..."
$repoJson = Call-API "/repos/$OWNER/$REPO"
$repoJson | Out-File "$OUTDIR/repo.json" -Encoding utf8

Write-Host "Collecting authenticated user's repo permissions..."
try {
    $repoObj = $repoJson | ConvertFrom-Json
    if ($repoObj.permissions) {
        $repoObj.permissions | ConvertTo-Json -Depth 10 | Out-File "$OUTDIR/permissions.json" -Encoding utf8
    } else {
        "{}" | Out-File "$OUTDIR/permissions.json" -Encoding utf8
    }
} catch {
    "{}" | Out-File "$OUTDIR/permissions.json" -Encoding utf8
}

Write-Host "Listing collaborators..."
$collabJson = Call-API "/repos/$OWNER/$REPO/collaborators?per_page=100"
$collabJson | Out-File "$OUTDIR/collaborators.json" -Encoding utf8

Write-Host "Listing teams..."
$teamsJson = Call-API "/repos/$OWNER/$REPO/teams"
$teamsJson | Out-File "$OUTDIR/teams.json" -Encoding utf8

Write-Host "Checking GitHub App installation for this repo..."
$installJson = Call-API "/repos/$OWNER/$REPO/installation"
$installJson | Out-File "$OUTDIR/installation.json" -Encoding utf8

Write-Host "Gathering Actions permissions..."
$actionsPermJson = Call-API "/repos/$OWNER/$REPO/actions/permissions"
$actionsPermJson | Out-File "$OUTDIR/actions_permissions.json" -Encoding utf8

Write-Host "Gathering workflows..."
$workflowsJson = Call-API "/repos/$OWNER/$REPO/actions/workflows"
$workflowsJson | Out-File "$OUTDIR/workflows.json" -Encoding utf8

Write-Host "Gathering Actions secrets..."
$secretsJson = Call-API "/repos/$OWNER/$REPO/actions/secrets?per_page=100"
$secretsJson | Out-File "$OUTDIR/actions_secrets.json" -Encoding utf8

Write-Host "Listing branches..."
$branchesJson = Call-API "/repos/$OWNER/$REPO/branches?per_page=100"
$branchesJson | Out-File "$OUTDIR/branches.json" -Encoding utf8

Write-Host "Gathering branch protection for each branch..."
try {
    $branches = $branchesJson | ConvertFrom-Json
    foreach ($branch in $branches) {
        $branchName = $branch.name
        Write-Host "  - checking protection for branch: $branchName"
        $safeBranchName = [Uri]::EscapeDataString($branchName)
        $protectionJson = Call-API "/repos/$OWNER/$REPO/branches/$safeBranchName/protection"
        $protectionJson | Out-File "$OUTDIR/protection_${branchName}.json" -Encoding utf8
    }
} catch {
    Write-Warning "Failed to process branches: $_"
}

Write-Host ""
Write-Host "Done. Results saved to: $OUTDIR"
Write-Host ""
Write-Host "Compressing results folder..."
$zipFile = "${OUTDIR}.zip"
Compress-Archive -Path $OUTDIR -DestinationPath $zipFile -Force
Write-Host "✓ Created archive: $zipFile"
Write-Host ""
Write-Host "Contents collected:"
Get-ChildItem $OUTDIR | ForEach-Object { Write-Host "  - $($_.Name)" }
