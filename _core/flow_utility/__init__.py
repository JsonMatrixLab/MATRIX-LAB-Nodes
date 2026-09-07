from collections.abc import Mapping

from ..flow_blocker import is_blocked_output
from ..lists_batch import ListBatchContract, dispatch_batch
from ..types_contract import validate_socket_value


_RUNTIME_KEY = "__flow_runtime__"
_OPERATION_ENTRY_POINT = "execute_utility_operation"
_REQUIRED_RUNTIME_KEYS = (
    "resolved_blocks",
    "input_socket_types",
    "required_input_names",
    "output_socket_types",
    "batch_policy",
    "payload_items",
    "input_is_list",
    "output_is_list",
)


class FlowUtilityError(ValueError):
    """A local refusal while composing a compiled utility operation."""


def _runtime_from(inputs):
    if not isinstance(inputs, Mapping):
        raise FlowUtilityError("compiled utility inputs must be a mapping")
    if _RUNTIME_KEY not in inputs:
        raise FlowUtilityError(
            f"compiled utility inputs are missing compiler-owned {_RUNTIME_KEY}"
        )

    runtime = inputs[_RUNTIME_KEY]
    if not isinstance(runtime, Mapping):
        raise FlowUtilityError(f"{_RUNTIME_KEY} must be a mapping")

    missing = tuple(key for key in _REQUIRED_RUNTIME_KEYS if key not in runtime)
    if missing:
        raise FlowUtilityError(
            "compiled utility runtime is missing required key(s): "
            + ", ".join(missing)
        )
    return runtime


def _operation_provider(provider):
    if isinstance(provider, Mapping):
        if _OPERATION_ENTRY_POINT not in provider:
            return None
        return provider[_OPERATION_ENTRY_POINT]
    return getattr(provider, _OPERATION_ENTRY_POINT, None)


def _resolve_operation(resolved_blocks):
    if not isinstance(resolved_blocks, Mapping):
        raise FlowUtilityError("resolved_blocks must be a mapping of block id to provider")

    candidates = []
    for block_id, provider in resolved_blocks.items():
        if type(block_id) is not str or not block_id:
            raise FlowUtilityError("every resolved operation block id must be a non-empty string")
        operation = _operation_provider(provider)
        if operation is not None:
            candidates.append((block_id, operation))

    if not candidates:
        raise FlowUtilityError(
            "utility operation resolution failed: no resolved block provides "
            f"{_OPERATION_ENTRY_POINT}"
        )
    if len(candidates) != 1:
        names = ", ".join(sorted(block_id for block_id, _ in candidates))
        raise FlowUtilityError(
            "utility operation resolution failed: exactly one resolved block must "
            f"provide {_OPERATION_ENTRY_POINT}; found {len(candidates)}: {names}"
        )

    block_id, operation = candidates[0]
    if not callable(operation):
        raise FlowUtilityError(
            f"resolved block {block_id} provides non-callable {_OPERATION_ENTRY_POINT}"
        )
    return block_id, operation


def _socket_contract(runtime):
    input_types = runtime["input_socket_types"]
    if not isinstance(input_types, Mapping):
        raise FlowUtilityError("input_socket_types must be a mapping")
    if any(
        type(name) is not str
        or not name
        or type(socket_type) is not str
        or not socket_type
        for name, socket_type in input_types.items()
    ):
        raise FlowUtilityError(
            "input_socket_types must map non-empty input names to socket labels"
        )

    required_names = runtime["required_input_names"]
    if (
        not isinstance(required_names, (tuple, list))
        or any(type(name) is not str or not name for name in required_names)
        or not set(required_names).issubset(input_types)
    ):
        raise FlowUtilityError(
            "required_input_names must be declared non-empty input names"
        )

    output_types = runtime["output_socket_types"]
    if not isinstance(output_types, (tuple, list)) or not output_types:
        raise FlowUtilityError("output_socket_types must be a non-empty sequence")
    if any(type(socket_type) is not str or not socket_type for socket_type in output_types):
        raise FlowUtilityError(
            "output_socket_types must contain only non-empty socket labels"
        )
    return dict(input_types), tuple(required_names), tuple(output_types)


def _validate_payload_items(payload_items, input_types, required_names):
    if type(payload_items) is not tuple:
        raise FlowUtilityError(
            "payload_items must be the compiler-separated immutable item tuple"
        )

    declared_names = set(input_types)
    required_names = set(required_names)
    for position, item in enumerate(payload_items):
        if not isinstance(item, Mapping):
            raise FlowUtilityError(f"payload item {position} must be an input mapping")
        actual_names = set(item)
        missing = sorted(required_names - actual_names)
        extra = sorted(actual_names - declared_names)
        if missing or extra:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("unexpected " + ", ".join(extra))
            raise FlowUtilityError(
                f"payload item {position} does not match input_socket_types: "
                + "; ".join(details)
            )
        for name, value in item.items():
            validate_socket_value(input_types[name], value)


def _validate_operation_result(block_id, result, output_types):
    if type(result) is not tuple or len(result) != len(output_types):
        raise FlowUtilityError(
            f"operation block {block_id} must return one result per output socket "
            f"as a tuple; expected {len(output_types)}"
        )

    for socket_type, value in zip(output_types, result):
        if not is_blocked_output(value):
            validate_socket_value(socket_type, value)
    return result


async def execute_compiled_node(node_id, provider, route, inputs):
    """Execute one compiler-resolved utility operation with explicit batch policy."""
    del node_id, provider, route
    runtime = _runtime_from(inputs)
    block_id, operation = _resolve_operation(runtime["resolved_blocks"])
    input_types, required_names, output_types = _socket_contract(runtime)
    _validate_payload_items(runtime["payload_items"], input_types, required_names)

    contract = ListBatchContract(
        batch_policy=runtime["batch_policy"],
        input_is_list=runtime["input_is_list"],
        output_is_list=runtime["output_is_list"],
    )
    contract.validate_output_count(len(output_types))
    policy = contract.batch_policy
    if policy == "map" and not all(runtime["output_is_list"]):
        raise FlowUtilityError(
            "map policy returns one list per output socket; every output_is_list flag "
            "must be true"
        )

    def run_item(item):
        return _validate_operation_result(block_id, operation(item), output_types)

    def run_batch(items):
        return _validate_operation_result(block_id, operation(items), output_types)

    if policy in {"exactly-one", "map"}:
        dispatched = dispatch_batch(
            runtime["payload_items"],
            contract,
            map_item=run_item,
        )
    else:
        dispatched = dispatch_batch(
            runtime["payload_items"],
            contract,
            handle_batch=run_batch,
        )

    if policy == "exactly-one":
        return dispatched[0]
    if policy == "map":
        return tuple(
            [result[position] for result in dispatched]
            for position in range(len(output_types))
        )
    return dispatched
