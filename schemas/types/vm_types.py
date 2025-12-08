from typing import TypedDict, Optional, Dict, Any

class vm_result(TypedDict):
    status: str
    vmid: Optional[int]
    info: Optional[Dict[str, Any]]

