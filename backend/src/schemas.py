from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .domain import Slot

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=90)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r'^[A-Z0-9][A-Z0-9-]{1,23}$')]
Narrative = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=400)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Credentials(Input):
    username: Text
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class BlockInput(Input):
    code: Code
    name: Text
    cultivar: Text
    area_ha: float = Field(gt=0, le=500, multiple_of=0.01)
    sensor: Code
    east_m: int = Field(ge=0, le=999)
    north_m: int = Field(ge=0, le=999)
    width_m: int = Field(gt=0, le=500)
    height_m: int = Field(gt=0, le=500)

    @model_validator(mode='after')
    def fit_site(self):
        if self.east_m + self.width_m > 1000 or self.north_m + self.height_m > 1000:
            raise ValueError('地块边界超出勘测范围')
        return self


class SampleInput(Input):
    block_id: int = Field(gt=0)
    sensor: Code
    observed_day: date
    slot: Slot
    temp_c: float = Field(ge=-30, le=60)
    rh_pct: float = Field(ge=0, le=100)
    source: Text


class RunInput(Input):
    window_end: date


class DecisionInput(Input):
    approve: bool
    reason: Narrative


class ScheduleInput(Input):
    code: Code
    block_id: int = Field(gt=0)
    starts_at: AwareDatetime


class ReplanInput(Input):
    starts_at: AwareDatetime
    reason: Narrative


class CompletionInput(Input):
    completed_at: AwareDatetime


class ReasonInput(Input):
    reason: Narrative


class HarvestInput(Input):
    round_id: int = Field(gt=0)
    observed_at: AwareDatetime
    brix: float = Field(ge=0, le=45, multiple_of=0.1)
    berry_count: int = Field(ge=20, le=500)
    note: Narrative
