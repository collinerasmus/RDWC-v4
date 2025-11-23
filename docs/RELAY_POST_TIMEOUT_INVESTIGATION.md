# Relay POST Timeout Investigation

## Issue Description
Reports of `/relay/set` POST endpoint timeout on feature branches.

## Investigation Summary

### 1. RequestAuditMiddleware Analysis
**Location**: `app/main.py:254-311`

**Findings**:
- Middleware correctly reads body with `await request.body()` (line 279)
- Properly restores body with `request._body = body_bytes` (line 281)
- Pattern follows FastAPI best practices for middleware body handling
- No double-consumption issues detected

**Verdict**: ✅ **No issues found** - Middleware implementation is correct

### 2. Endpoint Handler Analysis
**Location**: `app/main.py:2279-2341`

**Findings**:
- `relay_set_new()` is correctly defined as synchronous (`def`, not `async def`)
- Direct relay function calls through `relays_core`
- No async/await mismatches
- Synchronous handler appropriate for GPIO operations

**Verdict**: ✅ **No issues found** - Handler is properly synchronous

### 3. Relay Core Operations
**Location**: `app/relays_core.py`, `app/relay_guard.py`

**Findings**:
- `set_relay()` performs synchronous operations
- `relay_guard.safe_set()` includes small sleeps (10ms, 5ms) for GPIO settling
- These are blocking but necessary for hardware stability
- Total delay: ~15-25ms maximum under normal conditions

**Verdict**: ✅ **Expected behavior** - GPIO settling delays are required

### 4. Performance Testing
**Test Suite**: `tests/test_relay_endpoint_performance.py`

**Results**:
```
test_relay_set_post_performance        PASSED  (< 2.0s threshold)
test_relay_set_multiple_fast           PASSED  (avg < 0.5s)
test_relay_set_with_mode_check         PASSED  (< 2.0s)
test_middleware_body_consumption       PASSED  (< 2.0s)
test_invalid_relay_name_fast           PASSED  (< 0.5s)
```

**Measured Performance**:
- Single request: ~0.01s (10ms)
- Multiple rapid requests: avg ~0.01s
- Largest body test: ~0.04s (40ms)
- All well below 2-second threshold

**Verdict**: ✅ **No timeout issues** - Endpoint performs excellently

## Root Cause Analysis

### Potential Causes (Ruled Out)
1. ❌ **Middleware body consumption** - Correctly implemented
2. ❌ **Async/sync handler mismatch** - Handler is properly synchronous
3. ❌ **GPIO blocking delays** - Minimal and necessary (10-25ms)
4. ❌ **Performance degradation** - Tests show <50ms response times

### Likely External Factors
1. **Network latency** - Between Pi and client
2. **Load on Pi** - Other processes competing for CPU
3. **GPIO driver delays** - Kernel-level timing under heavy load
4. **Database contention** - SQLite locks from sensor poller

## Recommendations

### 1. Monitor in Production
Add timing metrics to actual Pi deployment:
```bash
# Check endpoint response times on Pi
curl -w "@curl-format.txt" -o /dev/null -s "http://192.168.88.49:8080/relay/set" \
  -H "Content-Type: application/json" \
  -d '{"name":"dosing_grow","on":false}'
```

Create `curl-format.txt`:
```
time_namelookup:  %{time_namelookup}\n
time_connect:     %{time_connect}\n
time_starttransfer: %{time_starttransfer}\n
time_total:       %{time_total}\n
```

### 2. Check System Load
```bash
# Monitor CPU and load during timeout events
top -b -n 1 | head -20
vmstat 1 5
```

### 3. Database Lock Analysis
```bash
# Check if sensor poller is holding locks
lsof /home/pi/RDWC-v4/data/rdwc.db
ps aux | grep sensor_poller
```

### 4. Network Diagnostics
```bash
# Measure network latency to Pi
ping -c 10 192.168.88.49
traceroute 192.168.88.49
```

## Conclusion

**No code-level timeout issues found in the relay POST endpoint.**

- Middleware: ✅ Correct implementation
- Handler: ✅ Proper synchronous definition
- Performance: ✅ <50ms response times in tests
- Body handling: ✅ No double-consumption

**If timeouts persist on Pi:**
1. Measure actual response times with curl timing
2. Check system load and competing processes
3. Monitor GPIO driver behavior under load
4. Verify network latency between client and Pi
5. Check for database lock contention

**Status**: No immediate code fix required. Recommend monitoring and diagnostics on actual Pi deployment.

---
**Investigation Date**: 2025-11-23  
**Test Results**: 5/5 passed, all under performance thresholds  
**Branch**: copilot/continue-fix-midnight-schedule
