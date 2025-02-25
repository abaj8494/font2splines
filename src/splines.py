import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path as MplPath
from fontTools.ttLib import TTFont

##############################################################################
# 1) Helper Functions (unchanged)
##############################################################################

def cffCharStringToPathAndPoints(charString, scale=1.0):
    from fontTools.pens.recordingPen import RecordingPen
    
    pen = RecordingPen()
    charString.draw(pen)  
    recorded_ops = pen.value  

    vertices = []
    codes = []
    anchor_points = []
    control_points = []
    segments = []

    def close_subpath_if_needed():
        if vertices and codes and codes[-1] != MplPath.CLOSEPOLY:
            vertices.append(vertices[-1])
            codes.append(MplPath.CLOSEPOLY)

    current_start = None
    for (method, pts) in recorded_ops:
        if method == "moveTo":
            close_subpath_if_needed()
            x, y = pts[0]
            x *= scale
            y *= scale
            vertices.append((x, y))
            codes.append(MplPath.MOVETO)
            anchor_points.append((x, y))
            current_start = (x, y)

        elif method == "lineTo":
            for (x, y) in pts:
                x *= scale
                y *= scale
                if vertices:
                    seg_vertices = [vertices[-1], (x, y)]
                else:
                    seg_vertices = [(x, y)]
                segments.append(("line", seg_vertices))

                vertices.append((x, y))
                codes.append(MplPath.LINETO)
                anchor_points.append((x, y))

        elif method == "curveTo":
            # cubic segments in groups of 3 points: (c1, c2, end)
            for i in range(0, len(pts), 3):
                c1x, c1y = pts[i]
                c2x, c2y = pts[i+1]
                ex,  ey  = pts[i+2]
                c1x *= scale
                c1y *= scale
                c2x *= scale
                c2y *= scale
                ex  *= scale
                ey  *= scale

                control_points.append((c1x, c1y))
                control_points.append((c2x, c2y))
                anchor_points.append((ex, ey))

                seg_start = vertices[-1] if vertices else (ex, ey)
                seg_vertices = [seg_start, (c1x, c1y), (c2x, c2y), (ex, ey)]
                segments.append(("cubic", seg_vertices))

                vertices.append((c1x, c1y))
                codes.append(MplPath.CURVE4)
                vertices.append((c2x, c2y))
                codes.append(MplPath.CURVE4)
                vertices.append((ex,  ey))
                codes.append(MplPath.CURVE4)

        elif method == "qCurveTo":
            # Quadratic in CFF is less common
            pass

        elif method == "closePath":
            close_subpath_if_needed()

    close_subpath_if_needed()
    path = MplPath(vertices, codes)
    return path, anchor_points, control_points, segments


def ttGlyphToPathAndPoints(ttGlyph, scale=1.0):
    coords = ttGlyph.coordinates
    endPts = ttGlyph.endPtsOfContours
    flags  = ttGlyph.flags

    vertices = []
    codes = []
    anchor_points = []
    control_points = []
    segments = []

    start_index = 0
    for end_index in endPts:
        contour_coords = coords[start_index:end_index+1]
        contour_flags  = flags[start_index:end_index+1]
        start_index = end_index + 1

        if not len(contour_coords):
            continue

        x0, y0 = contour_coords[0]
        x0 *= scale
        y0 *= scale
        vertices.append((x0, y0))
        codes.append(MplPath.MOVETO)
        anchor_points.append((x0, y0))
        current_point = (x0, y0)

        i = 1
        while i < len(contour_coords):
            x1, y1 = contour_coords[i]
            x1 *= scale
            y1 *= scale
            onCurve = bool(contour_flags[i] & 1)

            if onCurve:
                segments.append(("line", [current_point, (x1, y1)]))
                vertices.append((x1, y1))
                codes.append(MplPath.LINETO)
                anchor_points.append((x1, y1))
                current_point = (x1, y1)
                i += 1
            else:
                # Off-curve => QCURVE
                control_points.append((x1, y1))
                if i+1 < len(contour_coords):
                    x2, y2 = contour_coords[i+1]
                    x2 *= scale
                    y2 *= scale
                    onCurve2 = bool(contour_flags[i+1] & 1)
                    if onCurve2:
                        segments.append(("quadratic", [current_point, (x1, y1), (x2, y2)]))
                        vertices.append((x1, y1))
                        codes.append(MplPath.CURVE3)
                        vertices.append((x2, y2))
                        codes.append(MplPath.CURVE3)
                        anchor_points.append((x2, y2))
                        current_point = (x2, y2)
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1

        vertices.append(vertices[-1])
        codes.append(MplPath.CLOSEPOLY)

    path = MplPath(vertices, codes)
    return path, anchor_points, control_points, segments


##############################################################################
# 2) Main Function to Extract + Plot Glyph + Write Analysis
##############################################################################

def plotOmegaFromFont(font_path, unicode_val=0x03A9, scale=1.0, report_file="out.txt"):
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    if not cmap:
        raise RuntimeError("No usable cmap found in this font.")

    glyph_name = cmap.get(unicode_val)
    if glyph_name is None:
        raise RuntimeError(f"No glyph for U+{unicode_val:X} in this font.")
    print(f"Glyph name for U+{unicode_val:X}: {glyph_name}")

    path = None
    anchor_points = []
    control_points = []
    segments = []

    if 'glyf' in font:
        glyph = font['glyf'][glyph_name]
        path, anchor_points, control_points, segments = ttGlyphToPathAndPoints(glyph, scale=scale)
    elif 'CFF ' in font:
        cff = font['CFF '].cff
        topDict = cff.topDictIndex[0]
        charString = topDict.CharStrings[glyph_name]
        path, anchor_points, control_points, segments = cffCharStringToPathAndPoints(charString, scale=scale)
    else:
        raise RuntimeError("No 'glyf' or 'CFF ' table found in font. Not supported here.")

    # Plot
    fig, ax = plt.subplots(figsize=(6,6))
    patch = patches.PathPatch(path, facecolor='black', edgecolor='none', alpha=0.15)
    ax.add_patch(patch)
    outline_patch = patches.PathPatch(path, facecolor='none', edgecolor='black', linewidth=1.0)
    ax.add_patch(outline_patch)

    if anchor_points:
        ax.scatter([p[0] for p in anchor_points], [p[1] for p in anchor_points],
                   color='red', marker='o', label='On-curve points')
    if control_points:
        ax.scatter([p[0] for p in control_points], [p[1] for p in control_points],
                   color='blue', marker='x', label='Off-curve controls')

    xs = [v[0] for v in path.vertices]
    ys = [v[1] for v in path.vertices]
    if xs and ys:
        margin = 100
        ax.set_xlim(min(xs)-margin, max(xs)+margin)
        ax.set_ylim(min(ys)-margin, max(ys)+margin)

    ax.set_aspect('equal', 'box')
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc='best')
    plt.title(f"Glyph U+{unicode_val:X} from {font_path}\nAnchors (red), Controls (blue)")
    plt.show()

    # Analysis
    num_subpaths = sum(code == MplPath.MOVETO for code in path.codes)
    num_line_segments = sum(1 for (stype, _) in segments if stype == "line")
    num_quad_segments = sum(1 for (stype, _) in segments if stype == "quadratic")
    num_cubic_segments = sum(1 for (stype, _) in segments if stype == "cubic")

    with open(report_file, "w") as f:
        f.write(f"Analysis for U+{unicode_val:X} in font: {font_path}\n")
        f.write(f"Glyph name: {glyph_name}\n\n")

        f.write("=== Basic Point Counts ===\n")
        f.write(f"Total on-curve (anchor) points: {len(anchor_points)}\n")
        f.write(f"Total off-curve control points: {len(control_points)}\n\n")

        f.write("=== Path / Segment Summary ===\n")
        f.write(f"Number of subpaths: {num_subpaths}\n")
        f.write(f"Number of line segments (degree 1): {num_line_segments}\n")
        f.write(f"Number of quadratic segments (degree 2): {num_quad_segments}\n")
        f.write(f"Number of cubic segments (degree 3): {num_cubic_segments}\n\n")

        f.write("=== Detailed Segments ===\n")
        for i, (stype, pts) in enumerate(segments, start=1):
            if stype == "line":
                degree = 1
            elif stype == "quadratic":
                degree = 2
            elif stype == "cubic":
                degree = 3
            else:
                degree = None
            
            f.write(f"Segment {i}: type={stype}, degree={degree}, points={pts}\n")

    print(f"Analysis written to '{report_file}'.")


##############################################################################
# 3) argparse-based CLI
##############################################################################

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract and analyze a glyph from a font, then plot/annotate it.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--font", "-f", 
        required=True,
        help="Path to the TTF/OTF font file."
    )
    parser.add_argument(
        "--unicode", "-u",
        required=True,
        help="Unicode codepoint in hex (e.g. 0x03A9 or 03A9)."
    )
    parser.add_argument(
        "--report", "-r",
        default="out.txt",
        help="Output filename for analysis text."
    )
    parser.add_argument(
        "--scale", "-s",
        type=float,
        default=1.0,
        help="Scale factor for glyph coordinates."
    )
    
    args = parser.parse_args()

    # Convert unicode string to int (hex)
    # e.g. if user passes '03A9' or '0x03A9'
    unicode_str = args.unicode.strip().lower()
    if unicode_str.startswith("0x"):
        unicode_val = int(unicode_str, 16)
    else:
        unicode_val = int("0x" + unicode_str, 16)

    plotOmegaFromFont(
        font_path=args.font,
        unicode_val=unicode_val,
        scale=args.scale,
        report_file=args.report
    )

