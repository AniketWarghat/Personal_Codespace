"""
mymaps_html_to_shapefile.py

Extract line and point features, including original names and line colors,
from a Google My Maps page saved to disk as HTML.

The extracted features are written as ESRI Shapefiles with matching
QGIS .qml style files.

Graphical usage
---------------
Run without arguments:

    python mymaps_html_to_shapefile.py

A file-selection dialog will ask for the saved HTML file, followed by a
folder-selection dialog for the output directory.

Command-line usage
------------------
Provide both paths:

    python mymaps_html_to_shapefile.py saved_map.html output_folder

Provide only the HTML file and select the output folder graphically:

    python mymaps_html_to_shapefile.py saved_map.html

Requirements
------------
    pip install geopandas shapely

Tkinter is part of standard Python installations on Windows and macOS.

On Debian/Ubuntu, it may need to be installed separately:

    sudo apt install python3-tk

Output
------
    <output_dir>/<slug>_lines.shp
    <output_dir>/<slug>_lines.qml
    <output_dir>/<slug>_points.shp
    <output_dir>/<slug>_points.qml

Shapefile support files such as .shx, .dbf, .prj, and .cpg are generated
automatically by GeoPandas.

Limitations
-----------
- Only line and point geometries are exported.
- Polygon layers are not currently handled.
- Point icons are represented by a generic circle marker.
- Line colors are reproduced using a categorized QGIS style.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:
    tk = None
    filedialog = None
    messagebox = None

try:
    import geopandas as gpd
except ImportError:
    print(
        "GeoPandas is not installed.\n"
        "Install the required packages with:\n\n"
        "    pip install geopandas shapely\n",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from shapely.geometry import LineString, Point
except ImportError:
    print(
        "Shapely is not installed.\n"
        "Install the required packages with:\n\n"
        "    pip install geopandas shapely\n",
        file=sys.stderr,
    )
    sys.exit(1)


# --------------------------------------------------------------------------
# 1. Locate and decode the embedded _pageData JSON blob
# --------------------------------------------------------------------------

def extract_page_data(html_text: str):
    """
    Find `var _pageData = "...";` in the HTML and fully decode it.

    The value is a JSON string literal whose contents are themselves a
    JSON document. Therefore, it must be decoded twice.
    """
    marker = 'var _pageData = "'
    start = html_text.find(marker)

    if start == -1:
        raise ValueError(
            "Could not find '_pageData' in this file.\n\n"
            "Make sure you saved the Google My Maps viewer page itself "
            "using 'Save As -> Webpage, HTML Only'."
        )

    str_start = start + len(marker)

    # scanstring correctly handles escaped quotes, backslashes, Unicode
    # escapes, and other JSON string escapes.
    decoded_once, _end = json.decoder.scanstring(html_text, str_start)

    return json.loads(decoded_once)


# --------------------------------------------------------------------------
# 2. Helpers for interpreting the My Maps data structure
# --------------------------------------------------------------------------

def build_style_map(layer):
    """
    Map an internal per-feature style ID to:

        (display_name, hex_color)

    The structure used by Google My Maps is undocumented and may change.
    """
    style_map = {}
    styles = layer[4] if len(layer) > 4 else None

    if not styles:
        return style_map

    for style in styles:
        try:
            style_id = style[4][6]
            name = style[5][0][0]
            icon_url = style[0][0] if style[0] else ""

            color_match = re.search(
                r"filter=ff([0-9A-Fa-f]{6})",
                icon_url,
            )
            color = color_match.group(1) if color_match else None

            style_map[style_id] = (name, color)

        except (IndexError, TypeError, KeyError):
            continue

    return style_map


def find_vertex_lists(node):
    """
    Recursively find all line vertex lists in a nested structure.

    A vertex normally looks like:

        [[latitude, longitude]]

    A line vertex list contains two or more such vertices.
    """
    results = []

    def is_vertex(value):
        return (
            isinstance(value, list)
            and len(value) == 1
            and isinstance(value[0], list)
            and len(value[0]) == 2
            and all(isinstance(c, (int, float)) for c in value[0])
        )

    def recurse(value):
        if not isinstance(value, list):
            return

        if len(value) >= 2 and all(is_vertex(vertex) for vertex in value):
            results.append(value)
            return

        for child in value:
            recurse(child)

    recurse(node)
    return results


def find_single_point(node):
    """
    Recursively find the first [latitude, longitude] coordinate pair.
    """
    if isinstance(node, list):
        if (
            len(node) == 2
            and all(isinstance(c, (int, float)) for c in node)
        ):
            return node

        for child in node:
            found = find_single_point(child)
            if found is not None:
                return found

    return None


def get_name_attr(attrs):
    """
    Extract the 'name' value from a My Maps feature attribute list.
    """
    if not attrs:
        return None

    for attr in attrs:
        try:
            if attr[0] == "name":
                return attr[1][0]
        except (IndexError, TypeError):
            continue

    return None


# --------------------------------------------------------------------------
# 3. Walk layers and classify features as lines or points
# --------------------------------------------------------------------------

def parse_layers(layers):
    """
    Parse all supported line and point features from the supplied layers.
    """
    line_records = []
    point_records = []

    for layer in layers:
        if not isinstance(layer, list):
            continue

        layer_name = (
            layer[2]
            if len(layer) > 2 and layer[2]
            else "unnamed layer"
        )

        style_map = build_style_map(layer)
        features = layer[12] if len(layer) > 12 else None

        if not features:
            continue

        for feature in features:
            if not isinstance(feature, list):
                continue

            geom_field = feature[13] if len(feature) > 13 else None

            if not geom_field or not geom_field[0]:
                continue

            sub_geometries = geom_field[0]

            for entry in sub_geometries:
                if not isinstance(entry, list) or len(entry) < 2:
                    continue

                geometry_id = entry[0]
                second = entry[1]

                if second is None:
                    # A line or polygon-ring geometry. Polygon detection is
                    # not reliable in this reverse-engineered structure, so
                    # discovered vertex lists are exported as lines.
                    vertex_lists = find_vertex_lists(entry[2:])

                    if not vertex_lists:
                        continue

                    feature_name, color = style_map.get(
                        geometry_id,
                        (None, None),
                    )

                    for vertex_list in vertex_lists:
                        coordinates = []

                        for vertex in vertex_list:
                            try:
                                latitude, longitude = vertex[0]
                                coordinates.append((longitude, latitude))
                            except (IndexError, TypeError, ValueError):
                                continue

                        if len(coordinates) >= 2:
                            line_records.append(
                                {
                                    "layer": str(layer_name),
                                    "name": (
                                        str(feature_name)
                                        if feature_name is not None
                                        else None
                                    ),
                                    "color": (
                                        f"#{color.upper()}"
                                        if color
                                        else None
                                    ),
                                    "geometry": LineString(coordinates),
                                }
                            )

                else:
                    # Point geometry
                    coordinate = find_single_point(second)

                    if coordinate is None:
                        continue

                    latitude, longitude = coordinate
                    attrs = entry[5] if len(entry) > 5 else None
                    station_name = get_name_attr(attrs)

                    # Use the style/legend name as a fallback if the point
                    # does not have an explicit name attribute.
                    if station_name is None:
                        station_name, _color = style_map.get(
                            geometry_id,
                            (None, None),
                        )

                    point_records.append(
                        {
                            "layer": str(layer_name),
                            "name": (
                                str(station_name)
                                if station_name is not None
                                else None
                            ),
                            "geometry": Point(longitude, latitude),
                        }
                    )

    return line_records, point_records


# --------------------------------------------------------------------------
# 4. QGIS style generation
# --------------------------------------------------------------------------

def hex_to_rgb(hex_color):
    """
    Convert a hexadecimal color such as '#FF0000' into an RGB tuple.
    """
    value = hex_color.lstrip("#")

    if not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        raise ValueError(f"Invalid hexadecimal color: {hex_color}")

    return tuple(
        int(value[index:index + 2], 16)
        for index in (0, 2, 4)
    )


def write_lines_qml(gdf, path):
    """
    Write a categorized QGIS line style based on feature names and colors.
    """
    unique_styles = (
        gdf[["name", "color"]]
        .dropna(subset=["color"])
        .drop_duplicates()
        .reset_index(drop=True)
    )

    if unique_styles.empty:
        return False

    categories = []
    symbols = []

    for index, row in unique_styles.iterrows():
        red, green, blue = hex_to_rgb(row["color"])

        raw_name = (
            str(row["name"])
            if row["name"] is not None
            else "Unnamed"
        )
        escaped_name = html.escape(raw_name, quote=True)

        categories.append(
            f'<category render="true" symbol="{index}" '
            f'value="{escaped_name}" label="{escaped_name}"/>'
        )

        symbols.append(
            f"""
      <symbol name="{index}" type="line" alpha="1" force_rhr="0">
        <layer class="SimpleLine" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option type="QString" name="line_color"
                    value="{red},{green},{blue},255"/>
            <Option type="QString" name="line_width" value="0.8"/>
            <Option type="QString" name="line_width_unit" value="MM"/>
            <Option type="QString" name="capstyle" value="round"/>
            <Option type="QString" name="joinstyle" value="round"/>
          </Option>
        </layer>
      </symbol>"""
        )

    qml = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34">
  <renderer-v2 type="categorizedSymbol"
               attr="name"
               forceraster="0"
               symbollevels="0"
               enableorderby="0">
    <categories>
      {''.join(categories)}
    </categories>
    <symbols>
      {''.join(symbols)}
    </symbols>
  </renderer-v2>
</qgis>
"""

    Path(path).write_text(qml, encoding="utf-8")
    return True


def write_points_qml(path):
    """
    Write a simple circle-marker QGIS style for point features.
    """
    qml = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34">
  <renderer-v2 type="singleSymbol"
               forceraster="0"
               symbollevels="0"
               enableorderby="0">
    <symbols>
      <symbol name="0" type="marker" alpha="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option type="QString" name="name" value="circle"/>
            <Option type="QString" name="color"
                    value="255,255,255,255"/>
            <Option type="QString" name="outline_color"
                    value="35,35,35,255"/>
            <Option type="QString" name="outline_width" value="0.6"/>
            <Option type="QString" name="outline_width_unit" value="MM"/>
            <Option type="QString" name="size" value="2.4"/>
            <Option type="QString" name="size_unit" value="MM"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""

    Path(path).write_text(qml, encoding="utf-8")


# --------------------------------------------------------------------------
# 5. File and folder selection
# --------------------------------------------------------------------------

def select_input_output(html_file=None, output_dir=None):
    """
    Open native file/folder dialogs for any paths not supplied through
    command-line arguments.

    Returns:
        (html_path, output_path, dialogs_used)

    If the user cancels a dialog, both paths are returned as None.
    """
    dialogs_used = html_file is None or output_dir is None

    if not dialogs_used:
        return Path(html_file), Path(output_dir), False

    if tk is None:
        raise RuntimeError(
            "Tkinter is not installed, so graphical file-selection dialogs "
            "cannot be opened.\n\n"
            "Install Tkinter or provide both paths on the command line:\n\n"
            "python mymaps_html_to_shapefile.py input.html output_folder"
        )

    root = tk.Tk()
    root.withdraw()
    root.update()

    try:
        if html_file is None:
            html_file = filedialog.askopenfilename(
                parent=root,
                title="Select saved Google My Maps HTML file",
                filetypes=[
                    ("HTML files", "*.html *.htm"),
                    ("HTML files", "*.html"),
                    ("HTM files", "*.htm"),
                    ("All files", "*.*"),
                ],
            )

            if not html_file:
                return None, None, True

        html_path = Path(html_file).expanduser()

        if output_dir is None:
            try:
                initial_directory = str(html_path.resolve().parent)
            except OSError:
                initial_directory = str(Path.cwd())

            output_dir = filedialog.askdirectory(
                parent=root,
                title="Select output folder for shapefiles",
                initialdir=initial_directory,
                mustexist=True,
            )

            if not output_dir:
                return None, None, True

        return html_path, Path(output_dir).expanduser(), True

    finally:
        root.destroy()


def show_info_dialog(title, message):
    """
    Display an informational dialog if Tkinter is available.
    """
    if tk is None:
        return

    root = tk.Tk()
    root.withdraw()
    root.update()

    try:
        messagebox.showinfo(
            parent=root,
            title=title,
            message=message,
        )
    finally:
        root.destroy()


def show_error_dialog(title, message):
    """
    Display an error dialog if Tkinter is available.
    """
    if tk is None:
        return

    root = tk.Tk()
    root.withdraw()
    root.update()

    try:
        messagebox.showerror(
            parent=root,
            title=title,
            message=message,
        )
    finally:
        root.destroy()


# --------------------------------------------------------------------------
# 6. General helpers
# --------------------------------------------------------------------------

def slugify(name):
    """
    Convert a map name into a safe filename component.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(name))
    slug = slug.strip("_").lower()
    return slug or "mymaps"


# --------------------------------------------------------------------------
# 7. Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "html_file",
        nargs="?",
        default=None,
        help=(
            "Path to the saved My Maps HTML file. If omitted, a graphical "
            "file-selection dialog opens."
        ),
    )

    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help=(
            "Directory in which to write the shapefiles. If omitted, a "
            "graphical folder-selection dialog opens."
        ),
    )

    args = parser.parse_args()
    dialogs_used = args.html_file is None or args.output_dir is None

    try:
        html_path, output_dir, dialogs_used = select_input_output(
            html_file=args.html_file,
            output_dir=args.output_dir,
        )

        if html_path is None or output_dir is None:
            print("Operation cancelled.")
            return

        html_path = html_path.resolve()
        output_dir = output_dir.resolve()

        if not html_path.exists():
            raise FileNotFoundError(
                f"Input HTML file does not exist:\n{html_path}"
            )

        if not html_path.is_file():
            raise ValueError(
                f"The selected input path is not a file:\n{html_path}"
            )

        if html_path.suffix.lower() not in {".html", ".htm"}:
            print(
                "Warning: the selected input file does not have an "
                ".html or .htm extension.",
                file=sys.stderr,
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Input file: {html_path}")
        print(f"Output folder: {output_dir}")
        print("Reading HTML file...")

        html_text = html_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        print("Extracting embedded My Maps data...")
        data = extract_page_data(html_text)

        if not isinstance(data, list) or len(data) <= 1:
            raise ValueError(
                "The embedded _pageData structure is not in the expected "
                "format. Google may have changed the My Maps page format."
            )

        map_block = data[1]

        if not isinstance(map_block, list):
            raise ValueError(
                "The embedded map block is not in the expected format."
            )

        map_title = (
            map_block[2]
            if len(map_block) > 2 and map_block[2]
            else "mymaps"
        )

        layers = (
            map_block[6]
            if len(map_block) > 6 and map_block[6]
            else []
        )

        print(f"Map: {map_title}")
        print(f"Layers found: {len(layers)}")
        print("Parsing map features...")

        line_records, point_records = parse_layers(layers)

        print(f"Line features: {len(line_records)}")
        print(f"Point features: {len(point_records)}")

        slug = slugify(map_title)
        written_files = []

        # Export lines
        if line_records:
            lines_gdf = gpd.GeoDataFrame(
                line_records,
                geometry="geometry",
                crs="EPSG:4326",
            )

            lines_path = output_dir / f"{slug}_lines.shp"
            lines_qml_path = output_dir / f"{slug}_lines.qml"

            lines_gdf.to_file(
                lines_path,
                driver="ESRI Shapefile",
                encoding="UTF-8",
            )

            qml_written = write_lines_qml(
                lines_gdf,
                lines_qml_path,
            )

            written_files.append(lines_path)

            if qml_written:
                written_files.append(lines_qml_path)

            print(f"Wrote line shapefile: {lines_path}")

            if qml_written:
                print(f"Wrote line style: {lines_qml_path}")
            else:
                print(
                    "No line QML style was written because no line colors "
                    "were found.",
                    file=sys.stderr,
                )
        else:
            print("No line features found.", file=sys.stderr)

        # Export points
        if point_records:
            points_gdf = gpd.GeoDataFrame(
                point_records,
                geometry="geometry",
                crs="EPSG:4326",
            )

            points_path = output_dir / f"{slug}_points.shp"
            points_qml_path = output_dir / f"{slug}_points.qml"

            points_gdf.to_file(
                points_path,
                driver="ESRI Shapefile",
                encoding="UTF-8",
            )

            write_points_qml(points_qml_path)

            written_files.extend(
                [
                    points_path,
                    points_qml_path,
                ]
            )

            print(f"Wrote point shapefile: {points_path}")
            print(f"Wrote point style: {points_qml_path}")
        else:
            print("No point features found.", file=sys.stderr)

        if not written_files:
            warning = (
                "No supported line or point features were found.\n\n"
                "No output files were created."
            )
            print(warning, file=sys.stderr)

            if dialogs_used:
                show_info_dialog(
                    "No features found",
                    warning,
                )
            return

        completion_message = (
            "Export completed successfully.\n\n"
            f"Map: {map_title}\n"
            f"Line features: {len(line_records)}\n"
            f"Point features: {len(point_records)}\n\n"
            f"Output folder:\n{output_dir}"
        )

        print()
        print("Export completed successfully.")
        print(f"Output folder: {output_dir}")

        if dialogs_used:
            show_info_dialog(
                "Google My Maps export complete",
                completion_message,
            )

    except (tk.TclError if tk is not None else RuntimeError) as exc:
        error_message = (
            "Could not open the graphical file or folder selector.\n\n"
            "Provide both paths on the command line instead:\n\n"
            "python mymaps_html_to_shapefile.py "
            "input.html output_folder\n\n"
            f"Details: {exc}"
        )
        print(error_message, file=sys.stderr)
        sys.exit(1)

    except Exception as exc:
        error_message = f"Export failed:\n\n{exc}"
        print(error_message, file=sys.stderr)

        if dialogs_used:
            try:
                show_error_dialog(
                    "Google My Maps export failed",
                    error_message,
                )
            except Exception:
                pass

        sys.exit(1)


if __name__ == "__main__":
    main()