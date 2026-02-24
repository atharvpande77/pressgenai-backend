from pydantic import BaseModel
from typing import Annotated

class CategoryItem(BaseModel):
    id: str
    name: str
    value: str
    
class CityItem(BaseModel):
    id: str
    name: str