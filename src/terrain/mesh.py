from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh


@dataclass(frozen=True)
class MeshRules:
    expected_extents: tuple[float, float, float] | None = None
    expected_components: int | None = 1
    allowed_degenerate: int = 0
    tolerance: float = 0.03
    baseline_notes: tuple[str, ...] = ()


def load_mesh(path):
    loaded = trimesh.load(path, process=True)
    if isinstance(loaded, trimesh.Scene):
        return trimesh.util.concatenate(tuple(loaded.geometry.values()))
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"unsupported mesh content: {path}")
    return loaded


def measure_mesh(mesh):
    if mesh.is_empty:
        return {
            "empty": True,
            "extents_mm": [0.0, 0.0, 0.0],
            "bounds_mm": [],
            "volume_mm3": 0.0,
            "components": 0,
            "triangles": 0,
            "degenerate_triangles": 0,
        }

    with np.errstate(divide="ignore", invalid="ignore"):
        volume = float(mesh.volume)
    return {
        "empty": False,
        "extents_mm": mesh.extents.tolist(),
        "bounds_mm": mesh.bounds.tolist(),
        "volume_mm3": volume,
        "components": len(mesh.split(only_watertight=False)),
        "triangles": len(mesh.faces),
        "degenerate_triangles": int(np.count_nonzero(mesh.area_faces <= 1e-10)),
    }


def geometry_errors(mesh, metrics):
    if metrics["empty"]:
        return ["mesh is empty"]

    errors = []
    if not mesh.is_watertight:
        errors.append("mesh is not watertight/manifold")
    if not mesh.is_winding_consistent:
        errors.append("mesh winding is inconsistent")
    if not np.isfinite(metrics["volume_mm3"]) or metrics["volume_mm3"] <= 0:
        errors.append("mesh volume is not positive")
    return errors


def contract_errors(metrics, rules):
    errors = []
    if rules.expected_components is not None and metrics["components"] != rules.expected_components:
        actual_components = metrics["components"]
        errors.append(f"expected {rules.expected_components} components, found {actual_components}")
    if rules.expected_extents is not None and not np.allclose(
        metrics["extents_mm"], rules.expected_extents, atol=rules.tolerance, rtol=0
    ):
        actual_extents = tuple(metrics["extents_mm"])
        errors.append(f"expected extents {rules.expected_extents}, found {actual_extents}")
    if metrics["degenerate_triangles"] > rules.allowed_degenerate:
        errors.append(
            f"found {metrics['degenerate_triangles']} zero-area triangles; "
            f"allowed {rules.allowed_degenerate}"
        )
    return errors


def validation_warnings(metrics, rules):
    warnings = list(rules.baseline_notes)
    degenerate = metrics["degenerate_triangles"]
    if 0 < degenerate <= rules.allowed_degenerate:
        warnings.insert(
            0,
            f"{degenerate} zero-area triangles retained within template budget "
            f"{rules.allowed_degenerate}",
        )
    return warnings


def inspect_mesh(path, rules=MeshRules()):
    path = Path(path)
    try:
        mesh = load_mesh(path)
    except (OSError, ValueError, TypeError) as error:
        return {
            "path": str(path),
            "valid": False,
            "errors": [f"unable to load mesh: {error}"],
            "warnings": list(rules.baseline_notes),
        }

    metrics = measure_mesh(mesh)
    errors = geometry_errors(mesh, metrics) + contract_errors(metrics, rules)
    return {
        "path": str(path),
        "valid": not errors,
        "errors": errors,
        "warnings": validation_warnings(metrics, rules),
        "metrics": {key: value for key, value in metrics.items() if key != "empty"},
    }
