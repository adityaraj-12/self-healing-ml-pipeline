from datetime import datetime, timezone
from uuid import uuid4

from .incident import Incident


class IncidentBuilder:

    def build(
        self,
        detection,
        exception,
        stage,
        config,
        context
    ):
        return Incident(
            incident_id=f"INC-{uuid4().hex[:8].upper()}",

            timestamp=datetime.now(
                timezone.utc
            ).isoformat(),

            failure_type=detection[
                "failure_type"
            ],

            confidence=detection[
                "confidence"
            ],

            stage=stage,

            exception_type=type(
                exception
            ).__name__,

            error_message=str(exception),

            severity="high",

            pipeline_config=config.get(
                "model",
                {}
            ),

            context=context
        )