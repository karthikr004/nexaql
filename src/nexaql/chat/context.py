"""Optional caller knowledge for the existing NexaQL chat contract."""

from pydantic import BaseModel, Field


class BusinessContextEntry(BaseModel):
    term: str
    definition: str
    sql_hint: str | None = None


class AdditionalContext(BaseModel):
    """Query interpretation hints, never authority to bypass access policies."""

    business_context: list[BusinessContextEntry] = Field(default_factory=list)
    skill_instructions: str | None = None

    def entries(self) -> list[dict]:
        entries = [entry.model_dump(exclude_none=True) for entry in self.business_context]
        if self.skill_instructions and self.skill_instructions.strip():
            entries.append(
                {
                    "term": "Caller-provided skill instructions",
                    "definition": self.skill_instructions,
                }
            )
        return entries
