from dataclasses import dataclass

from terrain.mesh import MeshRules

PARTS = ("e_floor", "a_wall", "doorway", "l_corner")
GENRES = ("plain", "mork_borg", "cyberpunk", "expanse")
AUXILIARY_PARTS = ("clip", "coupon", "assembly")


@dataclass(frozen=True)
class PartContract:
    extents: tuple[float, float, float] | None
    components: int
    degenerate_budget: int
    baseline_notes: tuple[str, ...] = ()

    def rules(self) -> MeshRules:
        return MeshRules(
            expected_extents=self.extents,
            expected_components=self.components,
            allowed_degenerate=self.degenerate_budget,
            baseline_notes=self.baseline_notes,
        )


E_FLOOR_BASELINE = (
    "Official E template and generated plain STL both report 49 open edges to openscad-mcp 0.6.1; "
    "trimesh welded topology is watertight. Verify the artifact in the target slicer.",
)


CONTRACTS = {
    "e_floor": PartContract((50.8, 50.8, 7.0), 1, 20, E_FLOOR_BASELINE),
    "a_wall": PartContract((50.8, 12.7, 25.4), 1, 0),
    "doorway": PartContract((50.8, 12.7, 25.4), 1, 0),
    "l_corner": PartContract((11.5381, 11.5381, 25.4), 1, 0),
    "clip": PartContract((13.2, 19.5, 3.5), 1, 0),
    "coupon": PartContract((40.6, 25.4, 7.0), 3, 40, E_FLOOR_BASELINE),
    "assembly": PartContract((113.16, 114.32, 32.41), 7, 80, E_FLOOR_BASELINE),
}


@dataclass(frozen=True)
class ModelSpec:
    part: str
    genre: str
    seed: int


def mvp_specs(seed: int) -> list[ModelSpec]:
    models = [ModelSpec(part, genre, seed) for part in PARTS for genre in GENRES]
    models.extend(ModelSpec(part, "plain", seed) for part in ("clip", "coupon"))
    models.extend(ModelSpec("assembly", genre, seed) for genre in GENRES)
    return models


def named_spec(part: str, genre: str, seed: int) -> ModelSpec:
    if part not in PARTS + AUXILIARY_PARTS:
        raise ValueError(f"unknown part: {part}")
    if genre not in GENRES:
        raise ValueError(f"unknown genre: {genre}")
    return ModelSpec(part, genre, seed)


def part_contract(part: str) -> PartContract:
    try:
        return CONTRACTS[part]
    except KeyError as error:
        raise ValueError(f"unknown part: {part}") from error
