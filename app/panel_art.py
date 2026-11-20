from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps


@lru_cache(maxsize=20)
def brush_font(path, size):
    return ImageFont.truetype(str(path), size)


def logo(image, title, font_path, box):
    x, y, width, height = box
    size = max(10, height)
    font = brush_font(font_path, size)
    bounds = font.getbbox(title, stroke_width=1)
    natural_width = bounds[2] - bounds[0]
    natural_height = bounds[3] - bounds[1]
    scale = min(width / natural_width, height / natural_height, 1)
    mask = Image.new("L", (natural_width, natural_height))
    ImageDraw.Draw(mask).text((-bounds[0], -bounds[1]), title, font=font, fill=255, stroke_width=1)
    if scale < 1:
        mask = mask.resize((max(1, round(mask.width * scale)), max(1, round(mask.height * scale))),
                           Image.Resampling.LANCZOS)
    tint = Image.new("RGB", (mask.width, 1))
    tint.putdata([(max(0, 245 - int(247 * col / mask.width)),
                   250 - int(68 * col / mask.width), 255) for col in range(mask.width)])
    image.paste(tint.resize(mask.size), (x + (width - mask.width) // 2, y + (height - mask.height) // 2), mask)


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
