"""Base class for smithy-generated pydantic models.

Wired in via `--base-class` in `lambda/scripts/codegen.sh`. Keeps generated
files free of project-specific config while ensuring every generated model
accepts both wire (alias) and Python (snake_case) field names on input.
"""

from pydantic import BaseModel, ConfigDict


class GeneratedBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
