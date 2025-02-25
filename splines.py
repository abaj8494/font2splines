import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path as MplPath
from fontTools.ttLib import TTFont

##############################################################################
# 1) Helper Functions
##############################################################################

def cffCharStringToPathAndPoints(charString, scale=1.0):
    """
    Convert a CFF (Type 2) charString into:
      - A Matplotlib Path
      - A list of on-curve (anchor) points
      - A list of off-curve control points

    We also return a list of path "segments" so we can analyze line vs curve.
    Each segment is represented as (segment_type, list_of_vertices),
      where segment_type is 'line'/'cubic' etc.
    """
    from fontTools.pens.recordingPen import RecordingPen
    
    pen = RecordingPen()
    charString.draw(pen)  # 'draw' calls moveTo/lineTo/curveTo/closePath, etc.
    recorded_ops = pen.value  # list of (methodName, pointsList) tuples

    vertices = []
    codes = []

    anchor_points = []
    control_points = []

    # We'll keep a list of segments for analysis:
    # e.g. [("line", [(x0,y0), (x1,y1)]), ("cubic", [...])]
    segments = []

    def close_subpath_if_needed():
        if vertices and codes and codes[-1] != MplPath.CLOSEPOLY:
            vertices.append(vertices[-1])
            codes.append(MplPath.CLOSEPOLY)

    current_start = None  # track start of the current "stroke" for segment

    for (method, pts) in recorded_ops:
        if method == "moveTo":
            # close the previous subpath if needed
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
                # line from the previous vertex to (x, y)
                # gather 2 points for the segment
                if vertices:
                    seg_vertices = [vertices[-1], (x, y)]
                else:
                    seg_vertices = [(x, y)]
                segments.append(("line", seg_vertices))

                vertices.append((x, y))
                codes.append(MplPath.LINETO)
                anchor_points.append((x, y))

        elif method == "curveTo":
            # each set of 3 points => (control1, control2, end)
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

                # two control points + one anchor
                control_points.append((c1x, c1y))
                control_points.append((c2x, c2y))
                anchor_points.append((ex, ey))

                # build the segment for analysis
                if vertices:
                    seg_start = vertices[-1]
                else:
                    seg_start = (ex, ey)  # fallback
                seg_vertices = [seg_start, (c1x, c1y), (c2x, c2y), (ex, ey)]
                segments.append(("cubic", seg_vertices))

                # build path
                vertices.append((c1x, c1y))
                codes.append(MplPath.CURVE4)
                vertices.append((c2x, c2y))
                codes.append(MplPath.CURVE4)
                vertices.append((ex,  ey))
                codes.append(MplPath.CURVE4)

        elif method == "qCurveTo":
            # Quadratic curves in CFF are less common, but let's handle if present
            # Each group is (control1, ..., controlN, end)
            # We'll just handle them as multiple segments if needed
            pass

        elif method == "closePath":
            close_subpath_if_needed()

    # If the charstring never explicitly closed the last subpath:
    close_subpath_if_needed()

    path = MplPath(vertices, codes)
    return path, anchor_points, control_points, segments


def ttGlyphToPathAndPoints(ttGlyph, scale=1.0):
    """
    Convert a TrueType glyph ('glyf') to:
      - A Matplotlib Path
      - A list of on-curve anchor points
      - A list of off-curve control points
      - A list of "segments" for analysis (line/quadratic)

    We do a simplified approach to consecutive off-curves.
    """
    coords = ttGlyph.coordinates
    endPts = ttGlyph.endPtsOfContours
    flags = ttGlyph.flags

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

        # MoveTo first point
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
                # On-curve => line segment from current_point to (x1,y1)
                segments.append(("line", [current_point, (x1, y1)]))

                vertices.append((x1, y1))
                codes.append(MplPath.LINETO)
                anchor_points.append((x1, y1))
                current_point = (x1, y1)
                i += 1
            else:
                # Off-curve => QCURVE to next on-curve
                control_points.append((x1, y1))
                cpx, cpy = x1, y1
                if i + 1 < len(contour_coords):
                    x2, y2 = contour_coords[i+1]
                    x2 *= scale
                    y2 *= scale
                    onCurve2 = bool(contour_flags[i+1] & 1)
                    if onCurve2:
                        # Quadratic from current_point -> control -> (x2,y2)
                        # This is one segment
                        segments.append(("quadratic", [current_point, (cpx, cpy), (x2, y2)]))

                        # Build path: matplotlib uses CURVE3 in pairs
                        vertices.append((cpx, cpy))
                        codes.append(MplPath.CURVE3)
                        vertices.append((x2, y2))
                        codes.append(MplPath.CURVE3)

                        anchor_points.append((x2, y2))
                        current_point = (x2, y2)
                        i += 2
                    else:
                        # Next is off-curve => advanced logic needed
                        i += 1
                else:
                    i += 1

        # Close the contour
        vertices.append(vertices[-1])
        codes.append(MplPath.CLOSEPOLY)

    path = MplPath(vertices, codes)
    return path, anchor_points, control_points, segments


##############################################################################
# 2) Main Function to Plot Omega + Output Analysis
##############################################################################

def plotOmegaFromFont(font_path, unicode_val=0x03A9, scale=1.0, report_file="omega_analysis.txt"):
    """Plot the glyph for `unicode_val` (default: U+03A9) from `font_path`,
    including on/off-curve points, and write an analysis report to a text file.
    """
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
    segments = []  # (segment_type, [points...])

    if 'glyf' in font:
        # TrueType outlines
        glyf_table = font['glyf']
        glyph = glyf_table[glyph_name]
        path, anchor_points, control_points, segments = ttGlyphToPathAndPoints(glyph, scale=scale)
    elif 'CFF ' in font:
        # CFF (PostScript) outlines
        cff = font['CFF '].cff
        topDict = cff.topDictIndex[0]
        charString = topDict.CharStrings[glyph_name]
        path, anchor_points, control_points, segments = cffCharStringToPathAndPoints(charString, scale=scale)
    else:
        raise RuntimeError("No 'glyf' or 'CFF ' table found in font. Not supported here.")

    # 2A) Plot the shape
    fig, ax = plt.subplots(figsize=(6,6))

    # Outline fill (light)
    patch = patches.PathPatch(path, facecolor='black', edgecolor='none', alpha=0.15)
    ax.add_patch(patch)

    # Outline stroke
    outline_patch = patches.PathPatch(path, facecolor='none', edgecolor='black', linewidth=1.0)
    ax.add_patch(outline_patch)

    # On-curve (anchor) points in red
    if anchor_points:
        ax.scatter([p[0] for p in anchor_points],
                   [p[1] for p in anchor_points],
                   color='red', marker='o', label='On-curve points')

    # Off-curve control points in blue
    if control_points:
        ax.scatter([p[0] for p in control_points],
                   [p[1] for p in control_points],
                   color='blue', marker='x', label='Off-curve controls')

    # Set axes
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
    plt.title(f"Omega (U+{unicode_val:X}) from {font_path}\nAnchors (red) & Controls (blue)")
    plt.show()

    # 2B) Analyze segments and write to a text file
    #     We'll count how many lines, quadratics, cubics, subpaths, etc.

    # Count subpaths by scanning the Path codes for MOVETO
    # Each MOVETO typically starts a new subpath.
    num_subpaths = sum(code == MplPath.MOVETO for code in path.codes)

    num_line_segments = sum(1 for (stype, _) in segments if stype == "line")
    num_quad_segments = sum(1 for (stype, _) in segments if stype == "quadratic")
    num_cubic_segments = sum(1 for (stype, _) in segments if stype == "cubic")
    
    # We'll also label degrees: line => degree 1, quadratic => 2, cubic => 3
    # TrueType "curve3" => degree 2, CFF "curve4" => degree 3
    # The code above lumps them as "quadratic" or "cubic."

    with open(report_file, "w") as f:
        f.write(f"Omega (U+{unicode_val:X}) Analysis for font: {font_path}\n")
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
# 3) Run the code
##############################################################################

if __name__ == "__main__":
    # Example usage
    font_path = "MathJax_Main-Bold.otf"  # Or TTF if you have a TrueType version
    plotOmegaFromFont(font_path, unicode_val=0x03A9, scale=1.0,
                      report_file="omega_analysis.txt")

