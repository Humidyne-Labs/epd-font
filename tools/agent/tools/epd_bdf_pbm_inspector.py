#!/usr/bin/env python3
"""
epd_bdf_pbm_inspector.py (v2.1.0) — Pure-Stdlib BDF 2.1 & PBM (P1/P4) Consistency & Weight Inspector.

Designed for both `epd-font` CLI checks and the `embedded-ops` MCP harness (`epd_inspect_bdf`, `epd_inspect_pbm`).
Zero third-party dependencies (100% Python 3 stdlib).
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Expected enclosed interior hole counts for topological pinhole/counter auditing
STANDARD_EXPECTED_HOLES: dict[int, int] = {
    **{ord(c): 0 for c in "CEFGHIJKLMNSTUVWXYZcfhijklmntuvwxyz12357ΓΕΖΗΙΚΛΜΝΞΠΣΤΥΧΨ"},
    **{ord(c): 1 for c in "0469ADOPQRabdeopqαδρ"},
    **{ord(c): 2 for c in "8BgθϑφΦ"},
}


@dataclass
class BdfGlyph:
    codepoint: int
    name: str
    dwidth: int
    box_w: int
    box_h: int
    ofs_x: int
    ofs_y: int
    rows: list[list[int]]  # 0/1 matrix (box_h x box_w)


def _parse_bdf(bdf_path: Path) -> dict[str, Any]:
    lines = bdf_path.read_text(encoding="utf-8", errors="replace").splitlines()
    ascent = 0
    descent = 0
    pixel_size = 0
    glyphs: dict[int, BdfGlyph] = {}
    cur: dict[str, Any] | None = None
    in_bmp = False

    for raw in lines:
        s = raw.strip()
        if s.startswith("FONT_ASCENT "):
            ascent = int(s.split()[1])
        elif s.startswith("FONT_DESCENT "):
            descent = int(s.split()[1])
        elif s.startswith("PIXEL_SIZE "):
            pixel_size = int(s.split()[1])
        elif s.startswith("STARTCHAR "):
            cur = {"name": s.split(None, 1)[1], "cp": -1, "dwidth": 0, "bbx": (0, 0, 0, 0), "hex": []}
            in_bmp = False
        elif cur is not None:
            if s.startswith("ENCODING "):
                cur["cp"] = int(s.split()[1])
            elif s.startswith("DWIDTH "):
                cur["dwidth"] = int(s.split()[1])
            elif s.startswith("BBX "):
                cur["bbx"] = tuple(int(x) for x in s.split()[1:5])
            elif s == "BITMAP":
                in_bmp = True
            elif s == "ENDCHAR":
                cp = int(cur["cp"])
                bw, bh, ox, oy = cur["bbx"]
                rows: list[list[int]] = []
                if bw > 0 and bh > 0:
                    row_bytes = (bw + 7) // 8
                    tot_bits = row_bytes * 8
                    for h_str in cur["hex"][:bh]:
                        val = int(h_str, 16) if h_str else 0
                        rows.append([1 if ((val >> (tot_bits - 1 - c)) & 1) else 0 for c in range(bw)])
                if cp >= 0:
                    glyphs[cp] = BdfGlyph(
                        codepoint=cp,
                        name=str(cur["name"]),
                        dwidth=int(cur["dwidth"]),
                        box_w=bw,
                        box_h=bh,
                        ofs_x=ox,
                        ofs_y=oy,
                        rows=rows,
                    )
                cur = None
                in_bmp = False
            elif in_bmp:
                cur["hex"].append(s)

    return {"ascent": ascent, "descent": descent, "pixel_size": pixel_size, "glyphs": glyphs}


def _connected_components_4_holes(rows: list[list[int]]) -> list[tuple[int, int, int, int, int]]:
    """
    Return list of interior 4-connected 0-pixel components as (area, x, y, w, h)
    using pure stdlib BFS on a 1px zero-padded grid.
    """
    if not rows or not rows[0]:
        return []
    bh = len(rows)
    bw = len(rows[0])
    ph, pw = bh + 2, bw + 2
    grid = [[0] * pw for _ in range(ph)]
    for r in range(bh):
        for c in range(bw):
            grid[r + 1][c + 1] = rows[r][c]

    visited = [[False] * pw for _ in range(ph)]

    def bfs(sr: int, sc: int) -> tuple[int, int, int, int, int]:
        q: deque[tuple[int, int]] = deque([(sr, sc)])
        visited[sr][sc] = True
        area = 0
        min_r, max_r, min_c, max_c = sr, sr, sc, sc
        while q:
            r, c = q.popleft()
            area += 1
            min_r = min(min_r, r)
            max_r = max(max_r, r)
            min_c = min(min_c, c)
            max_c = max(max_c, c)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < ph and 0 <= nc < pw and not visited[nr][nc] and grid[nr][nc] == 0:
                    visited[nr][nc] = True
                    q.append((nr, nc))
        return area, min_c - 1, min_r - 1, (max_c - min_c + 1), (max_r - min_r + 1)

    # Mark exterior background starting from (0, 0)
    bfs(0, 0)

    holes: list[tuple[int, int, int, int, int]] = []
    for r in range(1, ph - 1):
        for c in range(1, pw - 1):
            if grid[r][c] == 0 and not visited[r][c]:
                holes.append(bfs(r, c))
    return holes


def _connected_components_8_fg(rows: list[list[int]]) -> int:
    """Count 8-connected foreground ink components."""
    if not rows or not rows[0]:
        return 0
    bh, bw = len(rows), len(rows[0])
    visited = [[False] * bw for _ in range(bh)]
    count = 0
    for r in range(bh):
        for c in range(bw):
            if rows[r][c] and not visited[r][c]:
                count += 1
                q: deque[tuple[int, int]] = deque([(r, c)])
                visited[r][c] = True
                while q:
                    cr, cc = q.popleft()
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            nr, nc = cr + dr, cc + dc
                            if 0 <= nr < bh and 0 <= nc < bw and not visited[nr][nc] and rows[nr][nc]:
                                visited[nr][nc] = True
                                q.append((nr, nc))
    return count


def _measure_h_and_v_runs(rows: list[list[int]], cp: int = 0) -> tuple[list[int], list[int]]:
    """Collect horizontal runs (middle 50% rows) and vertical runs (middle 50% cols)."""
    if not rows or not rows[0]:
        return [], []
    bh, bw = len(rows), len(rows[0])
    h_runs: list[int] = []
    r0, r1 = int(0.25 * bh), max(int(0.25 * bh) + 1, int(0.75 * bh))
    for r in range(r0, r1):
        row_r: list[int] = []
        in_r, s = False, 0
        for c in range(bw):
            if rows[r][c] and not in_r:
                s, in_r = c, True
            elif not rows[r][c] and in_r:
                row_r.append(c - s)
                in_r = False
        if in_r:
            row_r.append(bw - s)
        if cp == 0x0048 and len(row_r) == 1 and row_r[0] >= max(3, int(0.65 * bw)):
            continue
        h_runs.extend(row_r)

    v_runs: list[int] = []
    c0, c1 = int(0.25 * bw), max(int(0.25 * bw) + 1, int(0.75 * bw))
    for c in range(c0, c1):
        in_r, s = False, 0
        for r in range(bh):
            if rows[r][c] and not in_r:
                s, in_r = r, True
            elif not rows[r][c] and in_r:
                v_runs.append(r - s)
                in_r = False
        if in_r:
            v_runs.append(bh - s)
    return h_runs, v_runs


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def _resolve_char_queries(char_query: str) -> list[int]:
    if not char_query.strip():
        return []
    cps: list[int] = []
    for tok in char_query.split(","):
        t = tok.strip()
        if not t:
            continue
        if len(t) == 1:
            cps.append(ord(t))
        elif t.upper().startswith("U+"):
            cps.append(int(f"0x{t[2:]}", 0))
        elif t.lower().startswith("0x"):
            cps.append(int(t, 16))
        elif t.isdigit():
            cps.append(int(t))
        else:
            cps.extend(ord(ch) for ch in t)
    return list(dict.fromkeys(cps))


def inspect_bdf(
    bdf_path: str | Path,
    compare_bdf_path: str | Path | None = None,
    char_query: str = "",
) -> dict[str, Any]:
    """
    Inspect a BDF 2.1 bitmap font for stem weight consistency, topology health (pinholes/counters),
    typographic ink density, vertical alignment jitter, advance rhythm, and optional weight contrast.
    """
    bp = Path(bdf_path).expanduser().resolve()
    if not bp.is_file():
        raise FileNotFoundError(f"BDF file not found: {bp}")

    parsed = _parse_bdf(bp)
    glyphs: dict[int, BdfGlyph] = parsed["glyphs"]

    # 1. Stem weight across reference stem letters
    stem_chars = [ord(c) for c in "EFHIKLMNPRTUbdfhiklmnprt1"]
    all_h_meds: list[float] = []
    all_v_meds: list[float] = []
    thin_1px: list[str] = []
    for cp in stem_chars:
        g = glyphs.get(cp)
        if g and g.box_h >= 5:
            hr, vr = _measure_h_and_v_runs(g.rows, cp=cp)
            if hr:
                m_h = float(statistics.median(hr))
                all_h_meds.append(m_h)
                if m_h < 2.0:
                    thin_1px.append(f"{chr(cp)}:{m_h:.1f}")
            if vr:
                all_v_meds.append(float(statistics.median(vr)))
    s_h = sorted(all_h_meds)
    vstem_p10 = round(_percentile(s_h, 10), 2)
    vstem_med = round(_percentile(s_h, 50), 2)
    vstem_p90 = round(_percentile(s_h, 90), 2)
    hbar_med = round(float(statistics.median(all_v_meds)), 2) if all_v_meds else 0.0

    # 2. Topology health (pinholes, plugged counters, merged dots)
    pinholes: list[str] = []
    plugged: list[str] = []
    fragmented: list[str] = []
    for cp, max_h in STANDARD_EXPECTED_HOLES.items():
        if (cp == ord("a") and int(parsed["pixel_size"]) <= 14) or (cp == ord("0") and "mono" in bp.stem.lower()):
            max_h = 2
        g = glyphs.get(cp)
        if not g or g.box_w == 0 or g.box_h == 0:
            continue
        holes = _connected_components_4_holes(g.rows)
        if len(holes) > max_h:
            pinholes.append(f"{chr(cp)}(holes={len(holes)}>{max_h})")
        if max_h > 0 and len(holes) == 0:
            plugged.append(chr(cp))
    for cp in (ord(c) for c in "ij!?:;="):
        g = glyphs.get(cp)
        if g and g.box_w > 0 and g.box_h > 0:
            fg_c = _connected_components_8_fg(g.rows)
            if fg_c < 2:
                fragmented.append(f"{chr(cp)}(fg={fg_c})")

    filled_s_wells: list[str] = []
    for cp in (0x0073, 0x0053):
        g = glyphs.get(cp)
        if not g or g.box_h < 5 or g.box_w < 3:
            continue
        gh, gw = len(g.rows), len(g.rows[0])
        pw, ph = gw + 2, gh + 2
        pgrid = [[0] * pw for _ in range(ph)]
        for rr in range(gh):
            for cc in range(gw):
                pgrid[rr + 1][cc + 1] = g.rows[rr][cc]
        ext = [[False] * pw for _ in range(ph)]
        q: deque[tuple[int, int]] = deque([(0, 0)])
        ext[0][0] = True
        while q:
            rr, cc = q.popleft()
            for nr, nc in ((rr - 1, cc), (rr + 1, cc), (rr, cc - 1), (rr, cc + 1)):
                if 0 <= nr < ph and 0 <= nc < pw and not ext[nr][nc] and pgrid[nr][nc] == 0:
                    ext[nr][nc] = True
                    q.append((nr, nc))
        mid_r = gh // 2
        top_open = 0
        bot_open = 0
        for rr in range(1, max(2, mid_r)):
            on = [cc for cc in range(gw) if g.rows[rr][cc]]
            if on:
                top_open += sum(1 for cc in range(on[0], gw) if ext[rr + 1][cc + 1])
        for rr in range(min(gh - 2, mid_r), max(1, gh - 1)):
            on = [cc for cc in range(gw) if g.rows[rr][cc]]
            if on:
                bot_open += sum(1 for cc in range(on[-1] + 1) if ext[rr + 1][cc + 1])
        if top_open < 2 or bot_open < 2:
            filled_s_wells.append(f"{chr(cp)}(top={top_open},bot={bot_open})")

    # 3. Vertical alignment (caps A-Z, 0-9, Α-Ω and lowercase x-height)
    cap_tops: dict[int, int] = {}
    base_oys: dict[int, int] = {}
    clipped: list[str] = []
    asc, desc = int(parsed["ascent"]), int(parsed["descent"])
    for cp, g in glyphs.items():
        if g.box_h > 0 and ((g.ofs_y + g.box_h > asc) or (g.ofs_y < -desc)):
            clipped.append(f"U+{cp:04X}(bot={g.ofs_y},top={g.ofs_y + g.box_h})")
        if (
            (0x0041 <= cp <= 0x005A)
            or (0x0030 <= cp <= 0x0039)
            or (0x0391 <= cp <= 0x03A9 and cp != 0x03A2)
        ) and g.box_h > 0:
                cap_tops[cp] = g.ofs_y + g.box_h
                base_oys[cp] = g.ofs_y

    cap_mode = Counter(cap_tops.values()).most_common(1)[0][0] if cap_tops else 0
    base_mode = Counter(base_oys.values()).most_common(1)[0][0] if base_oys else 0
    cap_jitter = [f"{chr(cp)}:{v}" for cp, v in sorted(cap_tops.items()) if v != cap_mode]
    base_jitter = [f"{chr(cp)}:{v}" for cp, v in sorted(base_oys.items()) if v != base_mode]

    # 4. Typographic ink density across lowercase a-z
    densities: dict[int, float] = {}
    for cp in range(0x0061, 0x007B):
        g = glyphs.get(cp)
        if g and g.dwidth > 0 and cap_mode > 0:
            ink = sum(sum(r) for r in g.rows)
            densities[cp] = (ink / float(g.dwidth * cap_mode)) * 100.0
    dens_vals = list(densities.values())
    dens_mean = float(statistics.mean(dens_vals)) if dens_vals else 0.0
    dens_std = float(statistics.pstdev(dens_vals)) if len(dens_vals) > 1 else 0.0
    outliers = [
        f"{chr(cp)}:{v:.1f}%"
        for cp, v in sorted(densities.items())
        if dens_std > 0 and abs(v - dens_mean) > 2.5 * dens_std
    ]

    # 5. Advance rhythm
    advs = [g.dwidth for cp, g in glyphs.items() if cp >= 0x0020]
    adv_std = float(statistics.pstdev(advs)) if len(advs) > 1 else 0.0

    result: dict[str, Any] = {
        "bdf_path": str(bp),
        "pixel_size": parsed["pixel_size"],
        "font_ascent": asc,
        "font_descent": desc,
        "glyph_count": len(glyphs),
        "stem_weight": {
            "vstem_p10_px": vstem_p10,
            "vstem_median_px": vstem_med,
            "vstem_p90_px": vstem_p90,
            "vstem_iqr_px": round(vstem_p90 - vstem_p10, 2),
            "hbar_median_px": hbar_med,
            "hbar_to_vstem_ratio": round(hbar_med / max(0.1, vstem_med), 2),
            "thin_1px_glyphs": thin_1px,
        },
        "topology_health": {
            "spurious_pinhole_glyphs": pinholes,
            "plugged_counter_glyphs": plugged,
            "merged_dot_or_fragmented_glyphs": fragmented,
            "filled_or_pinched_s_wells": filled_s_wells,
        },
        "typographic_color": {
            "lowercase_ink_density_pct": round(dens_mean, 2),
            "density_std_pct": round(dens_std, 2),
            "density_outliers": outliers,
        },
        "vertical_alignment": {
            "baseline_ofs_y_mode": base_mode,
            "baseline_jitter_glyphs": base_jitter,
            "cap_height_mode": cap_mode,
            "cap_height_jitter_glyphs": cap_jitter,
            "clipped_glyphs": clipped,
        },
        "advance_rhythm": {
            "is_monospace": adv_std == 0.0,
            "advance_min": min(advs) if advs else 0,
            "advance_median": float(statistics.median(advs)) if advs else 0.0,
            "advance_max": max(advs) if advs else 0,
            "advance_std": round(adv_std, 4),
        },
    }

    # 6. Optional Bold-vs-Normal weight comparison
    if compare_bdf_path:
        cp_path = Path(compare_bdf_path).expanduser().resolve()
        if not cp_path.is_file():
            raise FileNotFoundError(f"Compare BDF not found: {cp_path}")
        other = _parse_bdf(cp_path)["glyphs"]
        other_meds = []
        for cp in stem_chars:
            og = other.get(cp)
            if og and og.box_h >= 5:
                hr, _ = _measure_h_and_v_runs(og.rows, cp=cp)
                if hr:
                    other_meds.append(float(statistics.median(hr)))
        other_med = float(statistics.median(other_meds)) if other_meds else 0.0
        shared = set(glyphs.keys()) & set(other.keys())
        ink_a = sum(sum(sum(r) for r in glyphs[c].rows) for c in shared)
        ink_b = sum(sum(sum(r) for r in other[c].rows) for c in shared)
        result["weight_comparison"] = {
            "compare_bdf": str(cp_path),
            "primary_vstem_median_px": vstem_med,
            "compare_vstem_median_px": round(other_med, 2),
            "vstem_delta_px": round(vstem_med - other_med, 2),
            "vstem_ratio": round(vstem_med / max(0.1, other_med), 2),
            "ink_mass_ratio": round(ink_a / max(1, ink_b), 2),
        }

    # Optional per-character ASCII bitmap inspection
    q_cps = _resolve_char_queries(char_query)
    if q_cps:
        inspected: list[dict[str, Any]] = []
        for cp in q_cps:
            g = glyphs.get(cp)
            if not g:
                inspected.append({"codepoint": f"U+{cp:04X}", "found": False})
                continue
            holes = _connected_components_4_holes(g.rows)
            inspected.append({
                "codepoint": f"U+{cp:04X}",
                "char": chr(cp) if cp >= 0x20 else "",
                "found": True,
                "dwidth": g.dwidth,
                "bbx": [g.box_w, g.box_h, g.ofs_x, g.ofs_y],
                "holes": len(holes),
                "fg_components": _connected_components_8_fg(g.rows),
                "ascii": ["".join("#" if px else "." for px in r) for r in g.rows],
            })
        result["glyphs"] = inspected

    return result


def _parse_pbm(pbm_path: Path) -> tuple[str, int, int, list[list[int]]]:
    data = pbm_path.read_bytes()
    # Tokenize header ignoring '#' comments
    idx = 0
    n = len(data)
    tokens: list[bytes] = []
    while len(tokens) < 3 and idx < n:
        while idx < n and data[idx] in b" \t\r\n":
            idx += 1
        if idx < n and data[idx : idx + 1] == b"#":
            while idx < n and data[idx : idx + 1] not in b"\r\n":
                idx += 1
            continue
        start = idx
        while idx < n and data[idx] not in b" \t\r\n#":
            idx += 1
        if idx > start:
            tokens.append(data[start:idx])
    if len(tokens) < 3:
        raise ValueError(f"Invalid PBM header in {pbm_path}")
    magic = tokens[0].decode("ascii")
    w, h = int(tokens[1]), int(tokens[2])

    rows: list[list[int]] = []
    if magic == "P1":
        rest = re.sub(rb"#[^\r\n]*", b" ", data[idx:]).decode("ascii", errors="ignore")
        bits = [int(ch) for ch in rest if ch in ("0", "1")]
        for r in range(h):
            rows.append(bits[r * w : (r + 1) * w])
    elif magic == "P4":
        # Skip exactly one whitespace byte after height token
        if idx < n and data[idx] in b" \t\r\n":
            idx += 1
        row_bytes = (w + 7) // 8
        payload = data[idx:]
        for r in range(h):
            off = r * row_bytes
            row_bits: list[int] = []
            for c in range(w):
                b_val = payload[off + (c >> 3)] if off + (c >> 3) < len(payload) else 0
                row_bits.append(1 if ((b_val >> (7 - (c & 7))) & 1) else 0)
            rows.append(row_bits)
    else:
        raise ValueError(f"Unsupported PBM magic {magic!r} in {pbm_path}")
    return magic, w, h, rows


def inspect_pbm(
    pbm_path: str | Path,
    crop_x: int = 0,
    crop_y: int = 0,
    crop_w: int = 0,
    crop_h: int = 0,
    render_ascii: bool = True,
    max_ascii_cols: int = 120,
) -> dict[str, Any]:
    """Inspect a P1 or P4 PBM bi-level image for run-lengths, white pinholes, and ASCII preview."""
    pp = Path(pbm_path).expanduser().resolve()
    if not pp.is_file():
        raise FileNotFoundError(f"PBM file not found: {pp}")
    magic, w, h, rows = _parse_pbm(pp)

    # Run-length histograms across full image
    h_runs: list[int] = []
    v_runs: list[int] = []
    ink_px = 0
    row_ink: list[int] = []
    for r in range(h):
        r_sum = sum(rows[r])
        ink_px += r_sum
        row_ink.append(r_sum)
        in_r, s = False, 0
        for c in range(w):
            if rows[r][c] and not in_r:
                s, in_r = c, True
            elif not rows[r][c] and in_r:
                h_runs.append(c - s)
                in_r = False
        if in_r:
            h_runs.append(w - s)
    for c in range(w):
        in_r, s = False, 0
        for r in range(h):
            if rows[r][c] and not in_r:
                s, in_r = r, True
            elif not rows[r][c] and in_r:
                v_runs.append(r - s)
                in_r = False
        if in_r:
            v_runs.append(h - s)

    tot_hr = max(1, len(h_runs))
    holes = _connected_components_4_holes(rows)
    tiny_specks = [
        {"x": x, "y": y, "w": bw, "h": bh, "area": area}
        for area, x, y, bw, bh in holes
        if area <= 3
    ]

    # Row-projection bands
    bands: list[dict[str, int]] = []
    in_b, bs, b_ink = False, 0, 0
    for r, cnt in enumerate(row_ink):
        if cnt > 0 and not in_b:
            in_b, bs, b_ink = True, r, cnt
        elif cnt > 0 and in_b:
            b_ink += cnt
        elif cnt == 0 and in_b:
            bands.append({"y_start": bs, "y_end": r - 1, "height": r - bs, "ink_px": b_ink})
            in_b = False
    if in_b:
        bands.append({"y_start": bs, "y_end": h - 1, "height": h - bs, "ink_px": b_ink})

    out: dict[str, Any] = {
        "pbm_path": str(pp),
        "format": magic,
        "width": w,
        "height": h,
        "ink_pixels": ink_px,
        "ink_coverage_pct": round((ink_px / max(1, w * h)) * 100.0, 2),
        "run_histogram": {
            "run_1px_pct": round(sum(1 for x in h_runs if x == 1) / tot_hr * 100.0, 2),
            "run_2px_pct": round(sum(1 for x in h_runs if x == 2) / tot_hr * 100.0, 2),
            "run_3plus_px_pct": round(sum(1 for x in h_runs if x >= 3) / tot_hr * 100.0, 2),
            "median_h_run": float(statistics.median(h_runs)) if h_runs else 0.0,
            "median_v_run": float(statistics.median(v_runs)) if v_runs else 0.0,
        },
        "fg_components_8conn": _connected_components_8_fg(rows),
        "enclosed_holes_count": len(holes),
        "pinhole_specks_1_to_3px": tiny_specks,
        "line_bands": bands,
    }

    if render_ascii and h > 0 and w > 0:
        x0 = max(0, crop_x)
        y0 = max(0, crop_y)
        x1 = min(w, x0 + (crop_w if crop_w > 0 else min(max_ascii_cols, w - x0)))
        y1 = min(h, y0 + (crop_h if crop_h > 0 else (h - y0)))
        out["ascii_crop"] = {"x": x0, "y": y0, "w": max(0, x1 - x0), "h": max(0, y1 - y0)}
        out["ascii"] = ["".join("#" if rows[r][c] else "." for c in range(x0, x1)) for r in range(y0, y1)]

    return out
