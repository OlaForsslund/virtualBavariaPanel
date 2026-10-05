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


def load_boat():
    src = re.sub(r"<g id=\"Fönster\">.*?</g>\s*</g>", "", SRC.read_text(), flags=re.S)
    shapes = [s for s in re.findall(SHAPE, src, re.S) if "#7E91E0" not in s and 'd="M320.693,420.42"' not in s]
    return f'<svg viewBox="{VIEWBOX}" xmlns="http://www.w3.org/2000/svg">' + "".join(shapes) + "</svg>"


BOAT = load_boat()


def drawn_bounds():
    k = 8
    png = cairosvg.svg2png(bytestring=BOAT.encode(), output_width=351 * k, output_height=622 * k)
    left, top, right, bottom = Image.open(io.BytesIO(png)).getchannel("A").getbbox()
    return 98 + left / k, 53 + top / k, 98 + right / k, 53 + bottom / k


L, T, R, B = drawn_bounds()


def render(path, w, h, fill=1.0, whole=False, bg=None):
    # Hull is `fill` of the width, keel on the bottom, rig cropped by the top edge;
    # whole: the whole boat is `fill` of the height, centred.
    if whole:
        vb_h = (B - T) / fill
        vb_w = vb_h * w / h
        vb = f"{(L + R) / 2 - vb_w / 2:.2f} {(T + B) / 2 - vb_h / 2:.2f} {vb_w:.2f} {vb_h:.2f}"
    else:
        vb_w = (R - L) / fill
        vb_h = vb_w * h / w
        vb = f"{(L + R) / 2 - vb_w / 2:.2f} {B + (vb_w - (R - L)) / 2 - vb_h:.2f} {vb_w:.2f} {vb_h:.2f}"
    svg = BOAT.replace(VIEWBOX, vb, 1)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(path), output_width=w, output_height=h, background_color=bg)


render(WEBAPP / "favicon-16x16.png", 16, 16, 0.96, whole=True)
render(WEBAPP / "favicon-32x32.png", 32, 32, 0.96, whole=True)
render(WEBAPP / "mstile-150x150.png", 150, 150)
render(WEBAPP / "android-chrome-192x192.png", 192, 192)
render(WEBAPP / "android-chrome-512x512.png", 512, 512)
render(WEBAPP / "garmin" / "icon.png", 360, 240)
# Opaque with a margin: declared `maskable` in manifest.json, and iOS blackens transparency.
render(WEBAPP / "apple-touch-icon.png", 180, 180, 0.80, bg=BG)
