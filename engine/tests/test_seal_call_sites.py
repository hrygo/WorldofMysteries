"""Every production ``seal()`` call has to name every required argument.

``SpeechUnitSealingService.seal`` takes ``execution`` and ``evidence`` as
required keyword-only arguments: sealing is the last point before bytes
exist, so a caller that has not resolved them must not be allowed to render.
Making them required is only useful if something notices when a caller
forgets one, and for a long time nothing did.

Both production call sites went on passing every other argument while
omitting these two, and the whole suite stayed green through several full
gates — because every test covering those paths returned before reaching the
call (``dependency_unavailable``, ``voice_not_configured``,
``narrative_has_no_character_segment``). A test that exercised the happy
path would have caught it. There is no such test, and there cannot easily be
one: the happy path needs a live provider, a published voice and an admitted
review.

So this asserts the property structurally. It reads the signature and every
call site under ``application/`` and ``infrastructure/``, and fails if one is
missing an argument the signature requires. That holds whether or not any
test ever gets as far as sealing.

Two shapes have to be covered. A direct call names every argument itself. A
forwarding call — ``TurnDeliveryPipeline`` splatting a dict into ``seal()`` —
names some and forwards the rest, so its dict has to supply the remainder.
That indirection is precisely how the original omission stayed invisible: the
call site looked complete, and the two missing arguments were simply absent
from a literal some distance away.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from application.speech_unit import SpeechUnitSealingService

ENGINE_ROOT = Path(__file__).resolve().parents[1]

#: Where a sealing call may legitimately live. Tests are excluded on purpose:
#: they drive the service directly through helpers of their own.
PRODUCTION_PACKAGES = ("application", "infrastructure")


def _required_seal_arguments() -> set[str]:
    signature = inspect.signature(SpeechUnitSealingService.seal)
    return {
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and name != "self"
    }


def _modules():
    for package in PRODUCTION_PACKAGES:
        for path in sorted((ENGINE_ROOT / package).rglob("*.py")):
            yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _direct_calls() -> list[tuple[str, int, set[str]]]:
    """``seal()`` calls that name their arguments outright."""
    found = []
    for path, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "seal":
                continue
            if any(keyword.arg is None for keyword in node.keywords):
                continue
            label = f"{path.relative_to(ENGINE_ROOT).as_posix()}:{node.lineno}"
            found.append((label, node.lineno, {kw.arg for kw in node.keywords}))
    return found


def _forwarding_calls() -> list[tuple[str, int, set[str]]]:
    """``seal()`` calls that splat a dict, and what they name themselves."""
    found = []
    for path, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "seal":
                continue
            if not any(keyword.arg is None for keyword in node.keywords):
                continue
            label = f"{path.relative_to(ENGINE_ROOT).as_posix()}:{node.lineno}"
            found.append((label, node.lineno, {kw.arg for kw in node.keywords if kw.arg}))
    return found


def _forwarded_dicts() -> list[tuple[str, int, set[str]]]:
    """``seal_arguments={...}`` literals, and the keys they set."""
    found = []
    for path, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "seal_arguments":
                    continue
                if not isinstance(keyword.value, ast.Dict):
                    continue
                label = f"{path.relative_to(ENGINE_ROOT).as_posix()}:{node.lineno}"
                found.append(
                    (
                        label,
                        node.lineno,
                        {
                            key.value
                            for key in keyword.value.keys
                            if isinstance(key, ast.Constant)
                        },
                    )
                )
    return found


DIRECT = _direct_calls()
FORWARDING = _forwarding_calls()
FORWARDED = _forwarded_dicts()
REQUIRED = _required_seal_arguments()


def _ids(sites):
    return [label for label, _, _ in sites]


def test_there_is_a_production_seal_call_to_check_at_all():
    """A scan that finds nothing passes while proving nothing.

    If this fails, every other test here is vacuous — and "no call site" is
    itself the condition that let the omission ship unnoticed.
    """
    assert DIRECT or FORWARDING, "no production seal() call site was found"


def test_the_forwarding_shape_is_recognised():
    """Skipping ``**kwargs`` forwarders is only safe because they are checked.

    If the forwarding shape disappeared, the dict test below would be
    asserting against a forwarder that no longer exists.
    """
    assert FORWARDING, "no forwarding seal() call was found to reason about"


@pytest.mark.parametrize(("label", "lineno", "named"), DIRECT, ids=_ids(DIRECT))
def test_every_direct_seal_call_names_every_required_argument(label, lineno, named):
    missing = sorted(REQUIRED - named)
    assert not missing, (
        f"{label} calls seal() without {missing}. Sealing is the last point "
        f"before audio exists; an incomplete call raises TypeError there and "
        f"the turn falls back to subtitles."
    )


@pytest.mark.parametrize(
    ("label", "lineno", "named"), FORWARDED, ids=_ids(FORWARDED)
)
def test_every_forwarded_argument_dict_completes_its_forwarder(label, lineno, named):
    """The forwarded dict is the other half of a call that looks complete.

    An argument missing from this literal is exactly as absent as one missing
    from a direct call, and harder to see: the call site itself is fine.
    """
    assert len(FORWARDING) == 1, (
        "more than one seal() forwarder exists; this scan cannot tell which "
        "dict feeds which one and would judge them against the wrong half"
    )
    supplied_by_forwarder = FORWARDING[0][2]
    missing = sorted(REQUIRED - supplied_by_forwarder - named)
    assert not missing, f"{label} forwards seal() without {missing}."
