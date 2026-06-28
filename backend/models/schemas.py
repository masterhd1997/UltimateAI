from pydantic import BaseModel
from typing import Optional
class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    result: Optional[str] = None