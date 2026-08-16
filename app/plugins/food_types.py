"""Explicit public input types used by Food MCP tools."""

from typing import Annotated, Literal, NotRequired, TypedDict

from pydantic import ConfigDict, Field

Status = Literal["eaten", "uncertain", "excluded"]
SearchLimit = Annotated[int, Field(ge=1, le=200)]
SearchOffset = Annotated[int, Field(ge=0)]


class ReceiptItem(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    item: str
    record_id: NotRequired[str]
    receipt_line: NotRequired[str]
    restaurant: NotRequired[str]
    quantity: NotRequired[float]
    portion_text: NotRequired[str]
    status: NotRequired[Status]
    nutrition_id: NotRequired[str]
    nutrition_multiplier: NotRequired[float]
    notes: NotRequired[str]


class RecordCorrection(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")

    receipt_id: str | None
    order_id: str | None
    email_message_id: str | None
    receipt_line: str | None
    purchase_timestamp_utc: str | None
    purchase_date_local: str | None
    consumption_timestamp_utc: str | None
    consumption_date_local: str | None
    meal_slot: str | None
    restaurant: str
    item: str
    quantity: float
    portion_text: str | None
    status: Status
    nutrition_id: str | None
    nutrition_multiplier: float
    notes: str | None
    apple_health_reference: str | None
    apple_health_sample_uuid: str | None
    apple_health_synced_at: str | None
