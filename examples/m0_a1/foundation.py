"""Disposable renderer and storage probes, not choices for the product."""

import json
import sqlite3
from contextlib import closing
from html import escape
from pathlib import Path

from offline_worker import require


def storage_probe(control, baseline_sha, candidate_sha):
    """Exercise two requests based on the same accepted, real Blender artifact."""
    require(baseline_sha != candidate_sha, "revision artifacts must differ")
    accepted = control / "accepted-rev"
    pending = accepted.with_suffix(".pending")
    accepted.write_text(baseline_sha, encoding="ascii")

    def file_write(base, proposed, interrupted=False):
        # Exclusive app-owned parent and one writer only; not a cross-process CAS.
        if accepted.read_text() != base:
            return False
        pending.write_text(proposed, encoding="ascii")
        if not interrupted:
            pending.replace(accepted)
        return True

    file_requests = [(accepted.read_text(), candidate_sha) for _ in range(2)]
    require(file_write(*file_requests[0]), "current file revision not accepted")
    reopened_file = accepted.read_text()
    require(reopened_file == candidate_sha, "file reopen lost the accepted digest")
    require(not file_write(*file_requests[1]), "previously valid file revision still accepted")
    require(file_write(candidate_sha, baseline_sha, interrupted=True), "file interrupt setup")
    require(
        pending.read_text() == baseline_sha and accepted.read_text() == candidate_sha,
        "interrupted file staging displaced accepted state",
    )

    db = control / "probe.db"

    def connect():
        return closing(sqlite3.connect(db, timeout=0))

    def stored(connection):
        return connection.execute("SELECT id FROM revision").fetchone()[0]

    def update(connection, base, proposed):
        return (
            connection.execute("UPDATE revision SET id=? WHERE id=?", (proposed, base)).rowcount
            == 1
        )

    with connect() as writer, connect() as reader:
        writer.execute("CREATE TABLE revision (id TEXT NOT NULL)")
        writer.execute("INSERT INTO revision VALUES (?)", (baseline_sha,))
        writer.commit()
        request1, request2 = (stored(writer), candidate_sha), (stored(reader), candidate_sha)
        writer.execute("BEGIN IMMEDIATE")
        require(update(writer, *request1), "current writer did not stage its row")
        require(stored(reader) == baseline_sha, "uncommitted database update visible")
        try:
            reader.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            require(error.sqlite_errorcode == sqlite3.SQLITE_BUSY, "unexpected database error")
        else:
            raise RuntimeError("a second database writer was not fenced")
        writer.commit()
    with connect() as reopened:
        reopened_sqlite = stored(reopened)
        require(reopened_sqlite == candidate_sha, "SQLite reopen lost the accepted digest")
        require(not update(reopened, *request2), "previously valid SQLite revision still accepted")
        require(update(reopened, candidate_sha, baseline_sha), "SQLite interrupt setup")
        # Closing without committing discards the interrupted candidate.
    with connect() as recovered:
        require(stored(recovered) == candidate_sha, "interrupted SQLite write changed revision")
    return {
        "sqlite_version": sqlite3.sqlite_version,
        "request_base": baseline_sha,
        "atomic_file": {
            "reopened": reopened_file,
            "stale_rejected": True,
            "after_interruption": accepted.read_text(),
            "cross_process_writer_fencing": False,
        },
        "sqlite": {
            "reopened": reopened_sqlite,
            "stale_rejected": True,
            "after_interruption": candidate_sha,
            "second_writer_blocked": True,
        },
    }


def projection(vertex, mode):
    x, y, z = vertex
    return (x, -y, z) if mode == "top" else (x - y * 0.45, -z + y * 0.4, -y)


def camera(baseline, candidate, mode):
    points = [
        projection(vertex, mode)
        for snapshot in (baseline, candidate)
        for obj in snapshot.values()
        for vertex in obj["vertices"]
    ]
    xs, ys, depths = zip(*points, strict=True)
    left, top, far = min(xs), min(ys), min(depths)
    return [left - 3, top - 3, max(xs) - left + 6, max(ys) - top + 6, far - 1, max(depths) + 1]


def viewer(path, baseline, candidate):
    """Make two local SVG comparisons with shared extents and an explicit frame highlight."""

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

        view = " ".join(f"{value:g}" for value in camera(baseline, candidate, mode)[:4])
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
polygon { fill: #8294a4; stroke: #253440; stroke-width: 0.15 }
polygon[data-part="frame"] { fill: #b28358 }
polygon.selected { fill: #f6bf46 }
button { margin-right: 8px }
</style>
<h1>M0-A1 offline fixture probe</h1>
<p>Fixed synthetic before/after. Not an agent edit or product UI.</p>
<p>Geometry picking is disabled: the SVG projection does not depth-test occlusion.</p>
<button id="view">Switch to top view</button><button id="frame">Highlight frame</button>
<p><output id="selected">No component highlighted</output></p>
"""
        + compare("oblique")
        + compare("top")
        + """<script>
const status = document.getElementById("selected");
function select(part) {
  status.value = `Highlighted: ${part}`;
  for (const face of document.querySelectorAll("[data-part]")) {
    face.classList.toggle("selected", face.dataset.part === part);
  }
}
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


def depth_viewer(path, baseline, candidate):
    """Use the same projection and extents as SVG, with a WebGL depth buffer."""
    views = {mode: camera(baseline, candidate, mode) for mode in ("oblique", "top")}
    data = json.dumps([views, list(baseline.values()), list(candidate.values())])
    template = (Path(__file__).resolve().parent / "depth.html").read_text(encoding="utf-8")
    path.write_text(
        template.replace("/* FIXTURE */", data.replace("<", "\\u003c")), encoding="utf-8"
    )
