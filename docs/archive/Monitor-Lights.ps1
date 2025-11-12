# RDWC-v4 Lights Monitoring Script (PowerShell)
# Monitors the whitelist protection system and tracks light control events

param(
    [string]$Command = "help",
    [int]$Count = 20,
    [string]$PiHost = "192.168.88.49"
)

$ApiBase = "http://$PiHost`:8080"

function Show-Help {
    Write-Host "🔍 RDWC-v4 Lights Monitoring Script" -ForegroundColor Green
    Write-Host "Usage: ./Monitor-Lights.ps1 -Command <command> [-Count N] [-PiHost IP]"
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Cyan
    Write-Host "  log          Show last N light events (default: 20)"
    Write-Host "  allowed      Show whitelisted reasons"
    Write-Host "  watch        Continuously monitor for new events"
    Write-Host "  blocked      Show only blocked attempts"
    Write-Host "  stats        Show event statistics"
    Write-Host "  hold         Set debugging hold for N seconds"
    Write-Host "  status       Show system status"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  ./Monitor-Lights.ps1 -Command log -Count 10"
    Write-Host "  ./Monitor-Lights.ps1 -Command watch"
    Write-Host "  ./Monitor-Lights.ps1 -Command blocked"
    Write-Host ""
}

function Show-Log {
    param([int]$Count = 20)
    
    Write-Host "📜 Last $Count lights events:" -ForegroundColor Cyan
    
    try {
        $response = Invoke-RestMethod -Uri "$ApiBase/debug/lights_log?last=$Count" -Method Get
        $events = $response.events
        
        Write-Host "Total events in log: $($response.total_events)" -ForegroundColor Yellow
        Write-Host "---"
        
        for ($i = 0; $i -lt $events.Count; $i++) {
            $eventItem = $events[$i]
            $blocked = if ($eventItem.blocked) { "🚫 BLOCKED" } else { "✅ ALLOWED" }
            $reason = if ($eventItem.reason) { $eventItem.reason } else { "unknown" }
            $state = if ($eventItem.final_state) { $eventItem.final_state } else { "unknown" }
            $caller = if ($eventItem.caller) { $eventItem.caller } else { "unknown" }
            $timestamp = if ($eventItem.timestamp) { $eventItem.timestamp } else { "no-time" }
            $cooldown = if ($eventItem.cooldown_remaining) { $eventItem.cooldown_remaining } else { 0 }
            
            Write-Host "$($i+1). $blocked $reason -> $state" -ForegroundColor $(if ($eventItem.blocked) { "Red" } else { "Green" })
            Write-Host "    📞 $caller" -ForegroundColor Gray
            Write-Host "    🕐 $timestamp (cooldown: ${cooldown}s)" -ForegroundColor Gray
            Write-Host ""
        }
    }
    catch {
        Write-Host "❌ Failed to fetch event log: $_" -ForegroundColor Red
    }
}

function Show-Allowed {
    Write-Host "✅ Whitelisted reasons for lights control:" -ForegroundColor Green
    
    try {
        $response = Invoke-RestMethod -Uri "$ApiBase/debug/lights_allowed" -Method Get
        $reasons = $response.allowed_reasons
        
        for ($i = 0; $i -lt $reasons.Count; $i++) {
            Write-Host "$($i+1). $($reasons[$i])" -ForegroundColor Cyan
        }
        Write-Host ""
        Write-Host "Total: $($reasons.Count) allowed reasons" -ForegroundColor Yellow
    }
    catch {
        Write-Host "❌ Failed to fetch allowed reasons: $_" -ForegroundColor Red
    }
}

function Show-Blocked {
    Write-Host "🚫 Blocked light control attempts:" -ForegroundColor Red
    
    try {
        $response = Invoke-RestMethod -Uri "$ApiBase/debug/lights_log?last=50" -Method Get
        $blockedEvents = $response.events | Where-Object { $_.blocked -eq $true }
        
        if ($blockedEvents.Count -eq 0) {
            Write-Host "✅ No blocked attempts found!" -ForegroundColor Green
        }
        else {
            for ($i = 0; $i -lt $blockedEvents.Count; $i++) {
                $eventItem = $blockedEvents[$i]
                $reason = if ($eventItem.reason) { $eventItem.reason } else { "unknown" }
                $caller = if ($eventItem.caller) { $eventItem.caller } else { "unknown" }
                $timestamp = if ($eventItem.timestamp) { $eventItem.timestamp } else { "no-time" }
                Write-Host "$($i+1). BLOCKED: `"$reason`" by $caller at $timestamp" -ForegroundColor Red
            }
        }
    }
    catch {
        Write-Host "❌ Failed to fetch blocked events: $_" -ForegroundColor Red
    }
}

function Show-Stats {
    Write-Host "📊 Light control event statistics:" -ForegroundColor Cyan
    
    try {
        $response = Invoke-RestMethod -Uri "$ApiBase/debug/lights_log?last=100" -Method Get
        $events = $response.events
        
        if ($events.Count -eq 0) {
            Write-Host "No events found" -ForegroundColor Yellow
            return
        }
        
        $blockedCount = ($events | Where-Object { $_.blocked -eq $true }).Count
        $allowedCount = $events.Count - $blockedCount
        
        Write-Host "Total events: $($events.Count)" -ForegroundColor White
        Write-Host "✅ Allowed: $allowedCount ($([math]::Round($allowedCount/$events.Count*100, 1))%)" -ForegroundColor Green
        Write-Host "🚫 Blocked: $blockedCount ($([math]::Round($blockedCount/$events.Count*100, 1))%)" -ForegroundColor Red
        Write-Host ""
        
        # Count by reason
        $reasonCounts = $events | Group-Object -Property reason | Sort-Object -Property Count -Descending
        Write-Host "Top reasons:" -ForegroundColor Cyan
        foreach ($group in $reasonCounts[0..9]) {
            Write-Host "  $($group.Name): $($group.Count)" -ForegroundColor Gray
        }
    }
    catch {
        Write-Host "❌ Failed to fetch statistics: $_" -ForegroundColor Red
    }
}

function Watch-Events {
    Write-Host "👀 Watching for new light control events (Ctrl+C to stop)..." -ForegroundColor Yellow
    $lastCount = 0
    
    try {
        while ($true) {
            $response = Invoke-RestMethod -Uri "$ApiBase/debug/lights_log?last=1" -Method Get -ErrorAction SilentlyContinue
            $currentCount = $response.total_events
            
            if ($currentCount -gt $lastCount) {
                Write-Host "🔔 New event detected at $(Get-Date):" -ForegroundColor Green
                $eventItem = $response.events[-1]
                $blocked = if ($eventItem.blocked) { "🚫 BLOCKED" } else { "✅ ALLOWED" }
                $reason = if ($eventItem.reason) { $eventItem.reason } else { "unknown" }
                $state = if ($eventItem.final_state) { $eventItem.final_state } else { "unknown" }
                $caller = if ($eventItem.caller) { $eventItem.caller } else { "unknown" }
                Write-Host "  $blocked $reason -> $state by $caller" -ForegroundColor $(if ($eventItem.blocked) { "Red" } else { "Green" })
                Write-Host ""
            }
            
            $lastCount = $currentCount
            Start-Sleep -Seconds 2
        }
    }
    catch {
        Write-Host "❌ Monitoring stopped: $_" -ForegroundColor Red
    }
}

function Set-Hold {
    param([int]$Seconds = 10)
    
    Write-Host "🛑 Setting lights hold for $Seconds seconds..." -ForegroundColor Yellow
    
    try {
        $body = @{ seconds = $Seconds } | ConvertTo-Json
        $response = Invoke-RestMethod -Uri "$ApiBase/debug/lights_hold" -Method Post -Body $body -ContentType "application/json"
        Write-Host "✅ Hold set successfully:" -ForegroundColor Green
        $response | ConvertTo-Json -Depth 3 | Write-Host
    }
    catch {
        Write-Host "❌ Failed to set hold: $_" -ForegroundColor Red
    }
}

function Show-Status {
    Write-Host "📊 RDWC System Status:" -ForegroundColor Cyan
    
    try {
        $response = Invoke-RestMethod -Uri "$ApiBase/health" -Method Get
        
        Write-Host "System OK: $($response.ok)" -ForegroundColor $(if ($response.ok) { "Green" } else { "Red" })
        Write-Host "Uptime: $([math]::Round($response.uptime_s, 0))s" -ForegroundColor Gray
        
        if ($response.relay_states.lights) {
            $lights = $response.relay_states.lights
            $state = if ($lights.state) { "ON" } else { "OFF" }
            $reason = if ($lights.last_reason) { $lights.last_reason } else { "unknown" }
            $since = if ($lights.seconds_since_change) { $lights.seconds_since_change } else { 0 }
            Write-Host "Lights: $state (reason: $reason, ${since}s ago)" -ForegroundColor $(if ($lights.state) { "Yellow" } else { "Gray" })
        }
        
        if ($response.antiflap_active -and $response.antiflap_active.Count -gt 0) {
            Write-Host "Anti-flap active: $($response.antiflap_active -join ', ')" -ForegroundColor Red
        }
        else {
            Write-Host "Anti-flap: OK" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "❌ Failed to fetch system status: $_" -ForegroundColor Red
    }
}

# Main command handling
switch ($Command.ToLower()) {
    "log" { Show-Log -Count $Count }
    "allowed" { Show-Allowed }
    "watch" { Watch-Events }
    "blocked" { Show-Blocked }
    "stats" { Show-Stats }
    "hold" { Set-Hold -Seconds $Count }
    "status" { Show-Status }
    default { Show-Help }
}