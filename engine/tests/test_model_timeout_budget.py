"""Timeout layering between the model transport and the authorized budget.

A turn is bounded twice: ``AuthorizedExecutionBudget`` wraps context
preparation, one model call and validation, while ``ModelEndpointConfig``
bounds the HTTP call alone.  The inner bound only means anything if it is
actually inside the outer one.  When the provider timeout defaults above the
budget it can never fire, and a slow endpoint surfaces as a generic stage
timeout instead of the transport verdict that names the real cause.
"""

from __future__ import annotations

import pytest

from ai.authorized_live_execution import AuthorizedExecutionBudget
from ai.openai_compatible import ModelEndpointConfig, ModelTransportError

ENV = {"WOM_MODEL_BASE_URL": "http://127.0.0.1:9/v1", "WOM_MODEL_NAME": "test-model"}


def test_the_default_provider_timeout_sits_inside_the_stage_budget() -> None:
    config = ModelEndpointConfig.from_env(ENV)
    budget = AuthorizedExecutionBudget(output_tokens=512)

    assert config is not None
    assert config.timeout_seconds < budget.timeout_seconds


def test_an_operator_can_still_widen_the_provider_timeout() -> None:
    config = ModelEndpointConfig.from_env({**ENV, "WOM_MODEL_TIMEOUT": "12.5"})

    assert config is not None
    assert config.timeout_seconds == 12.5


def test_an_unparseable_provider_timeout_is_a_configuration_error() -> None:
    with pytest.raises(ModelTransportError) as excinfo:
        ModelEndpointConfig.from_env({**ENV, "WOM_MODEL_TIMEOUT": "soon"})

    assert excinfo.value.code == "invalid_model_endpoint"


@pytest.mark.parametrize("raw", ["0", "-1", "601", "nan", "inf"])
def test_a_timeout_outside_the_bounded_range_is_refused(raw: str) -> None:
    with pytest.raises(ModelTransportError):
        ModelEndpointConfig.from_env({**ENV, "WOM_MODEL_TIMEOUT": raw})
