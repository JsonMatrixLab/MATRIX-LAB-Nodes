"""Explicit executor-list flags and payload-batch dispatch."""

from __future__ import annotations


_BATCH_POLICIES = frozenset(("exactly-one", "map", "batch", "reduce"))


class ListsBatchError(ValueError):
    """A node violated its declared list or batch cardinality."""


class ListBatchContract:
    """Transport-neutral cardinality declaration for one node."""

    __slots__ = ("batch_policy", "input_is_list", "output_is_list")

    def __init__(
        self,
        *,
        batch_policy,
        input_is_list=False,
        output_is_list=(False,),
    ):
        if not isinstance(batch_policy, str) or batch_policy not in _BATCH_POLICIES:
            raise ListsBatchError(
                "batch policy must be exactly-one, map, batch, or reduce"
            )
        if type(input_is_list) is not bool:
            raise ListsBatchError("input_is_list must be a bool")
        try:
            output_flags = tuple(output_is_list)
        except (TypeError, ValueError) as error:
            raise ListsBatchError(
                "output_is_list must contain one bool flag per output"
            ) from error
        if any(type(flag) is not bool for flag in output_flags):
            raise ListsBatchError("output_is_list flags must be bool")

        self.batch_policy = batch_policy
        self.input_is_list = input_is_list
        self.output_is_list = output_flags

    def validate_output_count(self, output_count):
        if (
            type(output_count) is not int
            or output_count < 0
            or len(self.output_is_list) != output_count
        ):
            raise ListsBatchError(
                "declare exactly one OUTPUT_IS_LIST flag per output; "
                f"received {len(self.output_is_list)} flags for {output_count!r} outputs"
            )
        return output_count

    def v1_list_flags(self):
        """Return V1's node-wide input flag and positional output flags."""
        return {
            "INPUT_IS_LIST": self.input_is_list,
            "OUTPUT_IS_LIST": self.output_is_list,
        }

    def v3_list_flags(self):
        """Return transport-neutral values at the positions V3 schemas require."""
        return {
            "is_input_list": self.input_is_list,
            "outputs": tuple(
                {"is_output_list": flag} for flag in self.output_is_list
            ),
        }


def dispatch_batch(
    items,
    contract,
    *,
    map_item=None,
    handle_batch=None,
):
    """Apply one explicit payload-batch policy without selecting item zero."""
    if not isinstance(contract, ListBatchContract):
        raise ListsBatchError("contract must be a ListBatchContract")
    try:
        payload = items if isinstance(items, tuple) else tuple(items)
    except (TypeError, ValueError) as error:
        raise ListsBatchError("batch payload must be an iterable of items") from error
    if not payload:
        raise ListsBatchError("batch payload must not be empty")

    policy = contract.batch_policy
    if policy in ("exactly-one", "map"):
        if not callable(map_item):
            raise ListsBatchError(f"{policy} policy requires a map_item handler")
        if policy == "exactly-one" and len(payload) != 1:
            raise ListsBatchError(
                f"exactly one item is required; received a batch of {len(payload)}"
            )
        return tuple(map_item(item) for item in payload)

    if not callable(handle_batch):
        raise ListsBatchError(f"{policy} policy requires a handle_batch handler")
    return handle_batch(payload)


__all__ = [
    "ListsBatchError",
    "ListBatchContract",
    "dispatch_batch",
]
