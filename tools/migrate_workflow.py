"""Migrate saved ComfyUI workflows to MATRIX LAB's normalized node IDs.

The migration is deliberately narrow: it changes registered class identities in
UI or API graphs and leaves every input, widget, link, prompt, and other string
untouched. Retired finish nodes are reported because replacing them requires a
separate semantic decision.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping


IDENTITY_MIGRATIONS = {
    "MATRIX_SaveClean": "MATRIX_MetadataKiller",
    "MATRIXLAB_PromptDirector": "MATRIX_AutoPrompter",
    "MATRIXLAB_ImageBatchLoader": "MATRIX_ImageBatchLoader",
    "MATRIXLAB_Resolution": "MATRIX_Resolution",
    "MATRIXLAB_AIInfluencerResolution": "MATRIX_AIInfluencerResolution",
    "MATRIXLAB_AIInfluencerResolution2K4K": "MATRIX_AIInfluencerResolution2K4K",
    "MATRIXLAB_EasyCrop": "MATRIX_EasyCrop",
    "MATRIXSpectralSampler": "MATRIX_SpectralSampler",
}
RETIRED_NODE_IDS = frozenset({"MATRIX_CameraLook", "MATRIX_Renoise"})


@dataclass(frozen=True)
class MigrationReport:
    format: str
    migrated_nodes: Mapping[str, int]
    replaced_identity_fields: int
    retired_nodes: Mapping[str, int]


def _record_identity(value: Any, counts: Counter[str]) -> Any:
    if isinstance(value, str) and value in IDENTITY_MIGRATIONS:
        counts[value] += 1
        return IDENTITY_MIGRATIONS[value]
    return value


def _identity(value: Any, location: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"malformed workflow: {location} must be a string")


def _report(format_name: str, migrated: Counter[str], fields: int,
            retired: Counter[str]) -> MigrationReport:
    return MigrationReport(
        format=format_name,
        migrated_nodes={key: migrated[key] for key in IDENTITY_MIGRATIONS if migrated[key]},
        replaced_identity_fields=fields,
        retired_nodes={key: retired[key] for key in sorted(RETIRED_NODE_IDS) if retired[key]},
    )


def migrate_workflow(document: Any) -> tuple[Any, MigrationReport]:
    """Return a migrated deep copy and a deterministic migration report.

    Supported shapes are a UI graph with a top-level ``nodes`` list, a direct
    API prompt mapping, and the common ``{"prompt": <API mapping>}`` envelope.
    """
    result = deepcopy(document)
    migrated: Counter[str] = Counter()
    retired: Counter[str] = Counter()
    replaced_fields = 0

    if isinstance(result, dict) and isinstance(result.get("nodes"), list):
        for node in result["nodes"]:
            if not isinstance(node, dict):
                continue
            node_type = _identity(node.get("type"), "UI node.type")
            if node_type in RETIRED_NODE_IDS:
                retired[node_type] += 1
            replacement = _record_identity(node_type, migrated)
            if replacement != node_type:
                node["type"] = replacement
                replaced_fields += 1

            properties = node.get("properties")
            if isinstance(properties, dict) and "Node name for S&R" in properties:
                search_name = properties["Node name for S&R"]
                replacement = _record_identity(search_name, Counter())
                if replacement != search_name:
                    properties["Node name for S&R"] = replacement
                    replaced_fields += 1
        return result, _report("ui", migrated, replaced_fields, retired)

    api = result.get("prompt") if isinstance(result, dict) and "prompt" in result else result
    if not isinstance(api, dict):
        raise ValueError("unsupported workflow JSON: expected a UI graph or API prompt mapping")

    for node in api.values():
        if not isinstance(node, dict):
            continue
        class_type = _identity(node.get("class_type"), "API node.class_type")
        if class_type in RETIRED_NODE_IDS:
            retired[class_type] += 1
        replacement = _record_identity(class_type, migrated)
        if replacement != class_type:
            node["class_type"] = replacement
            replaced_fields += 1
    return result, _report("api", migrated, replaced_fields, retired)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="source UI or API workflow JSON")
    parser.add_argument("--output", required=True, type=Path, help="new migrated workflow JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.input.resolve()
    output = args.output.resolve()
    if source == output:
        raise SystemExit("refusing to overwrite the input workflow")
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")
    if not source.is_file():
        raise SystemExit(f"input workflow does not exist: {source}")

    try:
        document = json.loads(source.read_text(encoding="utf-8"))
        migrated, report = migrate_workflow(document)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"could not migrate workflow: {exc}") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(migrated, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise SystemExit(f"refusing existing output: {output}") from exc
    print(json.dumps(asdict(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
