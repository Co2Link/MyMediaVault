from uuid import UUID

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TagRead(BaseModel):
    id: UUID
    name: str
