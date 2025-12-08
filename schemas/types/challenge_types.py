from typing import TypedDict, Optional, Dict, Any

class challenge_result(TypedDict):
    status: str
    challenge_id: Optional[int]
    level_id: Optional[int]
    flag: Optional[str]
    vmid: Optional[int]