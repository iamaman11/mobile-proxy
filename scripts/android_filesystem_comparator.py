#!/usr/bin/env python3
"""Shared Android filesystem comparator compatibility contract."""

from __future__ import annotations

from typing import Mapping, Sequence


SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"
PROBE_STATES = frozenset({SUPPORTED, UNSUPPORTED, UNKNOWN})

COMPARATOR_PROBES = {
    "cmp_present": "command -v cmp >/dev/null 2>&1",
    "cmp_exact_invocation": "cmp -s -- /dev/null /dev/null >/dev/null 2>&1",
    "toybox_present": "command -v toybox >/dev/null 2>&1",
    "toybox_cmp_exact_invocation": "toybox cmp -s /dev/null /dev/null >/dev/null 2>&1",
    "busybox_present": "command -v busybox >/dev/null 2>&1",
    "busybox_cmp_exact_invocation": "busybox cmp -s /dev/null /dev/null >/dev/null 2>&1",
}

COMPARATOR_CANDIDATES = (
    ("cmp", "cmp_present", "cmp_exact_invocation"),
    ("toybox_cmp", "toybox_present", "toybox_cmp_exact_invocation"),
    ("busybox_cmp", "busybox_present", "busybox_cmp_exact_invocation"),
)


class ComparatorContractFailure(RuntimeError):
    pass


def select_comparator(probes: Mapping[str, str]) -> tuple[str, str]:
    """Select the first comparator whose exact canonical invocation is proven.

    Presence is supporting evidence, never the success criterion. A present comparator
    whose exact invocation is unsupported cannot block a later compatible fallback.
    UNKNOWN is returned only when no compatible comparator is proven and at least one
    decision-relevant candidate remains unresolved.
    """

    unresolved_candidate = False
    for selected, present_key, invocation_key in COMPARATOR_CANDIDATES:
        try:
            presence = probes[present_key]
            invocation = probes[invocation_key]
        except KeyError as error:
            raise ComparatorContractFailure(
                f"missing comparator probe state: {error.args[0]}"
            ) from error
        if presence not in PROBE_STATES or invocation not in PROBE_STATES:
            raise ComparatorContractFailure(
                f"invalid comparator probe state for {selected}: "
                f"presence={presence!r}, invocation={invocation!r}"
            )

        if invocation == SUPPORTED:
            return selected, SUPPORTED

        if invocation == UNKNOWN and presence != UNSUPPORTED:
            unresolved_candidate = True

    if unresolved_candidate:
        return "UNKNOWN", UNKNOWN
    return "NONE", UNSUPPORTED


def comparison_argv(selected: str, actual: str, expected: str) -> Sequence[str]:
    """Return the exact admitted comparator invocation for two remote paths."""

    if selected == "cmp":
        return ("cmp", "-s", "--", actual, expected)
    if selected == "toybox_cmp":
        return ("toybox", "cmp", "-s", actual, expected)
    if selected == "busybox_cmp":
        return ("busybox", "cmp", "-s", actual, expected)
    raise ComparatorContractFailure(
        f"comparator is not admitted for exact comparison: {selected!r}"
    )
