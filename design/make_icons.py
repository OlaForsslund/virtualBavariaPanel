# Writes the app icons into webapp/ from the sailed Illustrator export (see icons.md).
# Needs: pip install cairosvg pillow
import io
import pathlib
import re
import cairosvg
from PIL import Image

WEBAPP = pathlib.Path(__file__).resolve().parents[1] / "webapp"
SRC = pathlib.Path(__file__).parent / "artwork" / "Bavaria34" / "Cruiser 34 sida2-sails.svg"
BG = "#1f2535"
SHAPE = r"<(?:path|polygon|polyline|line|rect)\b[^>]*?/>"
VIEWBOX = "98 53 351 622"
SAIL = re.compile(r'd="M(313\.56,102|326\.563,157)')  # mainsail and genoa paths


def load_boat():
    src = re.sub(r"<g id=\"Fönster\">.*?</g>\s*</g>", "", SRC.read_text(), flags=re.S)
    shapes = [s for s in re.findall(SHAPE, src, re.S) if "#7E91E0" not in s and 'd="M320.693,420.42"' not in s]
    shapes = [s.replace('fill="#FFFFFF"', 'fill="SAILFILL"') if SAIL.search(s) else s for s in shapes]
    return f'<svg viewBox="{VIEWBOX}" xmlns="http://www.w3.org/2000/svg">' + "".join(shapes) + "</svg>"


BOAT = load_boat()


def drawn_bounds():
    k = 8
    png = cairosvg.svg2png(bytestring=BOAT.encode(), output_width=351 * k, output_height=622 * k)
    left, top, right, bottom = Image.open(io.BytesIO(png)).getchannel("A").getbbox()
    return 98 + left / k, 53 + top / k, 98 + right / k, 53 + bottom / k


L, T, R, B = drawn_bounds()


def render(path, w, h, fill=1.0, whole=False, bg=None, below=None, keel=None, sail="#FFFFFF", shift=0.0):
    # Hull is `fill` of the width, keel on the bottom, rig cropped by the top edge;
    # whole: the whole boat is `fill` of the height, centred. below: space under the keel, as a fraction of the height.
    if whole:
        vb_h = (B - T) / fill
        vb_w = vb_h * w / h
        vb = f"{(L + R) / 2 - vb_w / 2:.2f} {(T + B) / 2 - vb_h / 2:.2f} {vb_w:.2f} {vb_h:.2f}"
    else:
        vb_w = (R - L) / fill
        vb_h = vb_w * h / w
        pad = (vb_w - (R - L)) / 2 if below is None else below * vb_h
        vb = f"{(L + R) / 2 - vb_w / 2 + shift * vb_w:.2f} {B + pad - vb_h:.2f} {vb_w:.2f} {vb_h:.2f}"
    svg = BOAT.replace(VIEWBOX, vb, 1)
    svg = svg.replace("SAILFILL", sail)
    if keel:
        svg = svg.replace("#2B348F", keel)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path if hasattr(path, "write") else str(path), output_width=w, output_height=h, background_color=bg)


render(WEBAPP / "favicon-16x16.png", 16, 16, 0.96, whole=True)
render(WEBAPP / "favicon-32x32.png", 32, 32, 0.96, whole=True)
render(WEBAPP / "garmin" / "icon.png", 360, 240)
# Opaque with a margin: declared `maskable` in manifest.json, and iOS blackens transparency.
render(WEBAPP / "apple-touch-icon.png", 180, 180, 0.80, bg=BG)
# Opaque: Android paints transparent PNG areas white on home-screen shortcuts.
for size in (150, 192, 512):
    render(WEBAPP / (f"mstile-{size}x{size}.png" if size == 150 else f"android-chrome-{size}x{size}.png"), size, size, 0.92, bg="#1D4A69", below=0.18, sail="#DBDBDB", shift=0.006)
# Android home screen: One UI shows the central ~86% of the canvas under a squircle (measured from a phone
# screenshot). Hull 92% of that width, lifted so the corners clear it, less room at the stern than the bow.
render(WEBAPP / "android-chrome-maskable-512x512.png", 512, 512, 0.789, bg="#1D4A69", below=0.2426, keel="#5A68C8", sail="#DBDBDB", shift=0.0069)

# B&G/Navico app tile: Zeus zooms and shifts transparent icons, but shows an opaque one as is.
# Background is the app's lightest (day --surface-hover); keel lightened to show on it, sails half a stop down, a little more room at the bow.
render(WEBAPP / "navico-tile.png", 192, 192, 0.92, bg="#1D4A69", below=0.18, keel="#7C8CF0", sail="#DBDBDB", shift=0.006)
