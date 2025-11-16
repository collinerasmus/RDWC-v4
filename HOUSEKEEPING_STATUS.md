All tests passing on Windows.
- Fixed commissioning_readiness import path issue by adding repo root to sys.path.
- Adjusted frontend_logs API to honor RDWC_DB env dynamically.
- Modified pH dosing lock acquisition to non-blocking to avoid deadlock and satisfy test expectations (returns 409 busy when locked).

Ready for UI review.
Timestamp: 2025-11-16T15:25:00Z