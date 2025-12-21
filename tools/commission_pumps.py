"""
Commissioning: Dosing Pumps Calibration

Exit Codes:
- 0: Success
- 1: Calibration failed
- 2: API error
"""

def discover_pumps(client):
    """Discover available dosing pumps via API.
    Returns: {"success": bool, "pumps": dict}
    """
    try:
        resp = client.get("/calib/dose/pumps")
        data = resp.json()
        return {"success": True, "pumps": data.get("pumps", {})}
    except Exception as e:
        return {"success": False, "error": str(e)}
