from typing import TypedDict, Optional, Dict, Any

class Vm_result(TypedDict):
    status: str
    vmid: Optional[int]
    info: Optional[Dict[str, Any]]

# class Vm_Info(TypedDict):

    