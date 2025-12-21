"""
Commissioning: pH Calibration

Exit Codes:
- 0: Success
- 1: Calibration failed
- 2: API error
"""

def check_capabilities(client):
    """Check pH calibration capabilities via API.
    Returns: {"success": bool, "capabilities": list}
    """
    try:
        resp = client.get("/calib/ph/caps")
        return {"success": True, "capabilities": resp.json().get("caps", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}
