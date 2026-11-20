from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps


@lru_cache(maxsize=20)
def brush_font(path, size):
    return ImageFont.truetype(str(path), size)


def logo(image, title, font_path, box):
    x, y, width, height = box
    title = title.upper()
    font = brush_font(font_path, max(10, height))
    stroke = max(1, round(height * .035))
    bounds = font.getbbox(title, stroke_width=stroke)
    mask = Image.new("L", (bounds[2] - bounds[0], bounds[3] - bounds[1]))
    ImageDraw.Draw(mask).text((-bounds[0], -bounds[1]), title, font=font,
                             fill=255, stroke_width=stroke)
    scale = min(max(1, width - 10) / mask.width, max(1, height - 8) / mask.height, 1)
    if scale < 1:
        mask = mask.resize((max(1, round(mask.width * scale)), max(1, round(mask.height * scale))),
                           Image.Resampling.LANCZOS)
    # Keep a bright, thick face; a restrained cyan rim separates it from artwork.
    face = Image.new("RGB", (1, mask.height))
    face.putdata([(round(245 - 89 * row / max(1, mask.height - 1)),
                   round(253 - 14 * row / max(1, mask.height - 1)), 255)
                  for row in range(mask.height)])
    position = (x + (width - mask.width) // 2, y + (height - mask.height) // 2)
    layer = Image.new("L", image.size)
    layer.paste(mask, position)
    outline = layer.filter(ImageFilter.MaxFilter(3))
    image.paste("#001225", (0, 0), outline.filter(ImageFilter.MaxFilter(3)))
    glow = outline.filter(ImageFilter.GaussianBlur(1.2)).point(lambda value: round(value * .55))
    image.paste("#00bfff", (0, 0), glow)
    image.paste("#20ceff", (0, 0), outline)
    image.paste(face.resize(mask.size), position, mask)


def control_texture(texture, size, palette, hovered):
    width, height = size
    bright, dark, edge = map(ImageColor.getrgb, palette)
    gradient = Image.new("RGB", (1, height))
    gradient.putdata([tuple(round(a + (b - a) * row / height) for a, b in zip(bright, dark))
                      for row in range(height)])
    face = gradient.resize(size)
    detail = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.fit(texture, size)))
    colored = ImageOps.colorize(detail, dark, bright)
    face = Image.blend(face, colored, 0.25 if hovered else 0.16)
    mask = Image.new("L", size)
    bounds = (0, 0, width - 1, height - 1)
    ImageDraw.Draw(mask).rounded_rectangle(bounds, radius=10, fill=255)
    surface = Image.new("RGB", size, "#041020")
    surface.paste(face, (0, 0), mask)
    draw = ImageDraw.Draw(surface)
    draw.rounded_rectangle(bounds, radius=10, outline=edge, width=2)
    draw.rounded_rectangle((2, 2, width - 3, height - 3), radius=8, outline=bright)
    return surface


def shaded_art(texture, size, role):
    width, height = size
    fitted = ImageOps.fit(texture, size, centering=(0.50, 0.36))
    if role == "lateral":
        vertical = Image.new("L", (1, height))
        vertical.putdata([int(250 * max(0, 1 - row / (height * .38))) for row in range(height)])
        return Image.composite(Image.new("RGB", size, "#040c18"), fitted, vertical.resize(size))
    if role == "cabecalho":
        return Image.blend(fitted, Image.new("RGB", size, "#01040a"), .83)
    base = Image.blend(fitted, Image.new("RGB", size, "#000613"), .73)
    portrait_width = max(1, round(width * .49))
    portrait = ImageOps.fit(texture, (portrait_width, height), centering=(.5, .27))
    horizontal = Image.new("L", (portrait_width, 1))
    horizontal.putdata([int(255 * min(1, (portrait_width - col) / max(1, portrait_width * .35)))
                        for col in range(portrait_width)])
    base.paste(portrait, (0, 0), horizontal.resize(portrait.size))
    return base
