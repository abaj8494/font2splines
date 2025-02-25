import re
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches

def load_segments_from_analysis(analysis_file):
    """
    Parse `analysis_file` to extract the segments after the
    '=== Detailed Segments ===' marker.

    Returns a list of (segment_type, [(x0,y0), (x1,y1), ...]) tuples.
    """
    segments = []
    parsing_segments = False

    # Regex to match lines like:
    #   Segment 1: type=cubic, degree=3, points=[(30.0, 43.0), (30.0, -12.0), ...]
    segment_re = re.compile(
        r"Segment\s+\d+:\s+type=(\w+),\s+degree=\d+,\s+points=\[(.*)\]"
    )

    with open(analysis_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            if line.startswith("=== Detailed Segments ==="):
                parsing_segments = True
                continue

            if parsing_segments:
                if line.startswith("Segment "):
                    match = segment_re.match(line)
                    if match:
                        seg_type = match.group(1)  # "cubic", "line", "quadratic", ...
                        points_str = match.group(2)
                        # The points are in Python tuple syntax, so we can safely parse with eval
                        points = eval("[" + points_str + "]")  # yields a list of (x, y) pairs
                        segments.append((seg_type, points))

                # else it might be a blank line or other info after segments
    return segments

def build_path_from_segments(segments):
    """
    Create a Matplotlib Path from the analysis segments.

    We handle 'line', 'cubic', and (if present) 'quadratic'.
    Multiple subpaths are created whenever a segment's start
    doesn't match the previous segment's end.
    """
    vertices = []
    codes = []

    current_pos = None  # the last endpoint we drew to

    for seg_type, pts in segments:
        if not pts:
            continue

        seg_start = pts[0]

        # If we have NO current_pos yet (i.e. first segment), or
        # if the new segment's start != current_pos => new subpath
        if current_pos is None or seg_start != current_pos:
            vertices.append(seg_start)
            codes.append(Path.MOVETO)
            current_pos = seg_start

        # Now add the rest of the points according to seg_type
        if seg_type == "line":
            # Typically 2 points: (start, end). If more, treat them as consecutive lines
            for p in pts[1:]:
                vertices.append(p)
                codes.append(Path.LINETO)
                current_pos = p

        elif seg_type == "cubic":
            # Typically 4 points: [start, c1, c2, end].
            # If more, handle them in groups of 3 after the initial 'start'.
            i = 1
            while i < len(pts):
                # We expect at least 3 points: c1, c2, end
                if i+2 < len(pts):
                    c1 = pts[i]
                    c2 = pts[i+1]
                    e  = pts[i+2]
                    vertices.append(c1)
                    codes.append(Path.CURVE4)
                    vertices.append(c2)
                    codes.append(Path.CURVE4)
                    vertices.append(e)
                    codes.append(Path.CURVE4)
                    current_pos = e
                    i += 3
                else:
                    # if there's a mismatch or partial leftover, skip or break
                    break

        elif seg_type == "quadratic":
            # If your analysis has "quadratic" segments, handle them similarly:
            # e.g. [start, control, end], repeated
            i = 1
            while i < len(pts):
                if i+1 < len(pts):
                    ctrl = pts[i]
                    end  = pts[i+1]
                    vertices.append(ctrl)
                    codes.append(Path.CURVE3)
                    vertices.append(end)
                    codes.append(Path.CURVE3)
                    current_pos = end
                    i += 2
                else:
                    break

        else:
            # unknown type => skip
            pass

    return Path(vertices, codes)

def plot_from_analysis(analysis_file, xlim=None, ylim=None):
    """Load segments from analysis, build a Path with multiple subpaths, plot it."""
    segments = load_segments_from_analysis(analysis_file)
    if not segments:
        print("No segments found or file missing 'Detailed Segments'.")
        return

    glyph_path = build_path_from_segments(segments)

    fig, ax = plt.subplots()
    patch = patches.PathPatch(glyph_path, facecolor='none', lw=2, edgecolor='blue')
    ax.add_patch(patch)

    # Plot red dots at each vertex, for debugging
    vx, vy = zip(*glyph_path.vertices)
    ax.plot(vx, vy, 'ro', markersize=6)

    ax.set_aspect('equal', 'box')

    # Auto or user-specified axis range
    if xlim is None:
        minx, maxx = min(vx), max(vx)
        ax.set_xlim(minx - 50, maxx + 50)
    else:
        ax.set_xlim(xlim)

    if ylim is None:
        miny, maxy = min(vy), max(vy)
        ax.set_ylim(miny - 50, maxy + 50)
    else:
        ax.set_ylim(ylim)

    ax.set_title(f"Glyph from {analysis_file}")
    plt.show()

if __name__ == "__main__":
    # Example usage: read "analysis.txt" and plot it
    # If your file is named differently, change below
    plot_from_analysis("out.txt")

