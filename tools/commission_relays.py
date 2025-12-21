"""
Commissioning: Relay Verification

Exit Codes:
- 0: Success
- 1: Hardware failure
- 2: API error
"""

def get_relay_status(client):
    """Get relay status via API.
    Returns: dict with mode, estop, relays keys.
    """
    try:
        resp = client.get("/api/relays/status")
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
