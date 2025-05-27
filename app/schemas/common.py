from typing import List, Dict, Any
from pydantic import BaseModel

class ImportSummary(BaseModel):
    total_rows_processed: int
    successfully_imported_count: int
    skipped_rows_count: int
    errors: List[Dict[str, Any]] # Each dict could be {"row_number": int, "error_message": str, "row_data": dict}

class MessageResponse(BaseModel): # A generic message response schema
    message: str
