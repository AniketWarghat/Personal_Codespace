import argparse
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Stitch municipal map-sheet PDFs into one combined map."
    )

    parser.add_argument(
        "--input",
        nargs="+",
        required=True,
        help="Input PDF files or a folder containing PDFs."
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output filename prefix, without extension."
    )

    parser.add_argument(
        "--layout",
        required=True,
        help='Layout string, e.g. "WS31,WS32;WS36,WS37"'
    )

    parser.add_argument(
        "--zoom",
        type=float,
        default=3.0,
        help="PDF render zoom factor (default: 3.0)"
    )

    parser.add_argument(
        "--blend",
        type=int,
        default=40,
        help="Seam blend width in pixels (default: 40)"
    )

    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF output."
    )

    return parser.parse_args()


def main():
    args = parse_args()

    print("Map Stitcher - Step 1")
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Layout: {args.layout}")
    print(f"Zoom:   {args.zoom}")
    print(f"Blend:  {args.blend}")
    print(f"PDF:    {'disabled' if args.no_pdf else 'enabled'}")


if __name__ == "__main__":
    main()