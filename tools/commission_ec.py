"""
Commissioning: EC Calibration

Exit Codes:
- 0: Success
- 1: Calibration failed
- 2: API error
"""

def set_k_value(client, k_value: float):
    """Set EC K-value via API.
    Returns: {"success": bool, "k_value": float}
    """
    try:
        resp = client.post("/api/ec/k", json_data={"k_value": k_value})
        return {"success": resp.json().get("ok", False), "k_value": k_value}
    except Exception as e:
        return {"success": False, "error": str(e)}
