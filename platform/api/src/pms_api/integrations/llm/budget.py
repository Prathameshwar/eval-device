"""Bound patient prompts before generation; trim only complete older turns.

The trimming rules live in `training_contracts.patient_turn` so the laptop applies the same
budget against the same model. This module keeps the platform's parameter-dict call shape.
"""

from training_contracts.patient_turn import TurnError
from training_contracts.patient_turn import fit_patient_prompt as fit_shared

from pms_api.integrations.llm.runner import ProviderRunner, app_error


async def fit_patient_prompt(client, parameters, settings, *, margin=64):
    try:
        return await fit_shared(
            ProviderRunner(client, parameters, settings),
            parameters["messages"],
            parameters["max_tokens"],
            margin=margin,
        )
    except TurnError as error:
        raise app_error(error) from None
