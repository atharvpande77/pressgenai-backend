from pydantic import BaseModel, ConfigDict
from typing import Annotated
from uuid import UUID

class CategoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    value: str
    
class CityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str