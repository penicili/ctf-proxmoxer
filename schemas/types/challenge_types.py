from typing import TypedDict, Optional, Dict, Any

class ChallengeResultType(TypedDict):
    status: str
    challenge_id: Optional[int]
    level_id: Optional[int]
    flag: Optional[str]
    vmid: Optional[int]