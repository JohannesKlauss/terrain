"""Disposable renderer and storage probes, not choices for the product."""

import sqlite3
from contextlib import closing
from html import escape

from offline_worker import require


def storage_probe(control, baseline_sha):
    """Compare interrupted writes and writer semantics using the real baseline digest."""
    accepted = control / "accepted-rev"
    pending = accepted.with_suffix(".pending")
    accepted.write_text(baseline_sha, encoding="ascii")
    pending.write_text("candidate", encoding="ascii")
    require(accepted.read_text() == baseline_sha, "pending file displaced accepted state")
    pending.replace(accepted)
    require(accepted.read_text() == "candidate", "atomic replacement not visible")

    with (
        closing(sqlite3.connect(control / "probe.db", timeout=0)) as writer,
        closing(sqlite3.connect(control / "probe.db", timeout=0)) as reader,
    ):
        writer.execute("CREATE TABLE revision (id TEXT NOT NULL)")
        writer.execute("INSERT INTO revision VALUES (?)", (baseline_sha,))
        writer.commit()
        writer.execute("BEGIN IMMEDIATE")
        changed = writer.execute("UPDATE revision SET id=? WHERE id=?", ("candidate", baseline_sha))
        require(changed.rowcount == 1, "current writer did not stage its row")
        require(
            reader.execute("SELECT id FROM revision").fetchone() == (baseline_sha,),
            "uncommitted database update visible",
        )
        try:
            reader.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            require(error.sqlite_errorcode == sqlite3.SQLITE_BUSY, "unexpected database error")
        else:
            raise RuntimeError("a second database writer was not fenced")
        writer.rollback()
        require(
            reader.execute("SELECT id FROM revision").fetchone() == (baseline_sha,),
            "database rollback lost the baseline",
        )
        stale = writer.execute("UPDATE revision SET id=? WHERE id=?", ("wrong", "stale"))
        require(stale.rowcount == 0, "stale database update was not rejected")
    return {
        "sqlite_version": sqlite3.sqlite_version,
        "atomic_file": "staging preserves accepted bytes before replace; no writer fencing tested",
        "sqlite": "exclusive write reservation, old value visible, rollback, stale predicate",
    }


def viewer(path, baseline, candidate):
    """Make two local SVG comparisons with shared extents and stable component picking."""

    def projection(vertex, mode):
        x, y, z = vertex
        return (x, -y, z) if mode == "top" else (x - y * 0.45, -z + y * 0.4, -y)

    def compare(mode):
        def scene(items):
            triangles = []
            for obj in items.values():
                for face in obj["triangles"]:
                    projected = [projection(obj["vertices"][index], mode) for index in face]
                    depth = sum(v[2] for v in projected)
                    points = " ".join(f"{x:g},{y:g}" for x, y, _ in projected)
                    component = escape(obj["id"], quote=True)
                    triangles.append(
                        (depth, f'<polygon data-part="{component}" points="{points}"/>')
                    )
            return "".join(polygon for _, polygon in sorted(triangles))

        points = [
            projection(vertex, mode)
            for snapshot in (baseline, candidate)
            for obj in snapshot.values()
            for vertex in obj["vertices"]
        ]
        xs, ys, _ = zip(*points, strict=True)
        left, top = min(xs), min(ys)
        view = f"{left - 3:g} {top - 3:g} {max(xs) - left + 6:g} {max(ys) - top + 6:g}"
        return (
            f'<section class="pair" id="{mode}"{" hidden" if mode == "top" else ""}>'
            + "".join(
                f'<figure><figcaption>{name}</figcaption><svg viewBox="{view}" '
                f'aria-label="{name} {mode} view">{scene(items)}</svg></figure>'
                for name, items in (("Baseline", baseline), ("Candidate", candidate))
            )
            + "</section>"
        )

    path.write_text(
        """<!doctype html>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>M0-A1 offline fixture probe</title>
<style>
body { font: 16px system-ui; margin: 24px; background: #162028; color: #f3f5f6 }
figure { display: inline-block; width: min(43%, 520px); margin: 0 16px 0 0 }
svg { width: 100%; background: #253440; margin-top: 8px }
polygon { fill: #8294a4; stroke: #253440; stroke-width: 0.15; cursor: pointer }
polygon[data-part="frame"] { fill: #b28358 }
polygon.selected { fill: #f6bf46 }
button { margin-right: 8px }
</style>
<h1>M0-A1 offline fixture probe</h1>
<p>Fixed synthetic before/after. Not an agent edit or product UI.</p>
<button id="view">Switch to top view</button><button id="frame">Select frame</button>
<p><output id="selected">No component selected</output></p>
"""
        + compare("oblique")
        + compare("top")
        + """<script>
const status = document.getElementById("selected");
function select(part) {
  status.value = `Selected: ${part}`;
  for (const face of document.querySelectorAll("[data-part]")) {
    face.classList.toggle("selected", face.dataset.part === part);
  }
}
document.addEventListener("click", (event) => {
  const face = event.target.closest("[data-part]");
  if (face) select(face.dataset.part);
});
document.getElementById("frame").onclick = () => select("frame");
document.getElementById("view").onclick = (event) => {
  const top = document.getElementById("top");
  top.hidden = !top.hidden;
  document.getElementById("oblique").hidden = !top.hidden;
  event.target.textContent = top.hidden ? "Switch to top view" : "Switch to oblique view";
};
</script>
""",
        encoding="utf-8",
    )
