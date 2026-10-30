import json
import os

from openai import OpenAI

from .rca_engine import RCAResult


class LLMRCA:

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL")

        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        if not self.model:
            raise RuntimeError(
                "OPENAI_MODEL is not configured."
            )

        base_url = os.getenv(
            "OPENAI_BASE_URL"
        )

        if base_url:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=base_url
            )
        else:
            self.client = OpenAI(
                api_key=self.api_key
            )

    def analyze(self, incident) -> RCAResult:

        prompt = self._build_prompt(
            incident
        )

        response = self.client.chat.completions.create(
            model=self.model,

            temperature=0,

            response_format={
                "type": "json_object"
            },

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an ML pipeline root-cause "
                        "analysis system. "
                        "Analyze only the supplied evidence. "
                        "Do not invent missing information. "
                        "Return a concise structured diagnosis. "
                        "Do not modify or execute code."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        content = (
            response.choices[0]
            .message.content
        )

        result = json.loads(content)

        return RCAResult(
            failure_type=result[
                "failure_type"
            ],

            root_cause=result[
                "root_cause"
            ],

            evidence=result[
                "evidence"
            ],

            repair_target=result[
                "repair_target"
            ],

            suggested_action=result[
                "suggested_action"
            ],

            confidence=float(
                result["confidence"]
            ),

            method="llm"
        )

    def _build_prompt(self, incident):

        return f"""
Analyze the following ML pipeline incident.

Failure type detected:
{incident.failure_type}

Pipeline stage:
{incident.stage}

Exception type:
{incident.exception_type}

Error message:
{incident.error_message}

Pipeline configuration:
{json.dumps(
    incident.pipeline_config,
    indent=2
)}

Runtime context:
{json.dumps(
    incident.context,
    indent=2
)}

Return ONLY valid JSON using this structure:

{{
  "failure_type": "...",
  "root_cause": "...",
  "evidence": [
    "...",
    "..."
  ],
  "repair_target": "...",
  "suggested_action": "...",
  "confidence": 0.0
}}

Rules:

1. Use only the provided evidence.
2. Do not invent files, columns or parameters.
3. Do not generate executable code.
4. Separate observed evidence from the inferred root cause.
5. Confidence must be between 0 and 1.
"""