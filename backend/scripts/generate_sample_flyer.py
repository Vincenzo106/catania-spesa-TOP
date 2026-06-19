from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_sample_flyer(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 1600), color=(248, 244, 235))
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    draw.rounded_rectangle((40, 40, 1160, 1560), radius=42, fill=(255, 251, 245))
    draw.rectangle((40, 40, 1160, 240), fill=(195, 43, 30))
    draw.text((80, 96), "COOP VOLANTINO SETTIMANALE", font=title_font, fill="white")
    draw.text((80, 170), "Offerte valide fino al 2026-06-30", font=body_font, fill="white")

    offers = [
        ("Pasta Rummo 500g", "Prima: EUR 1.99  Ora: EUR 1.09"),
        ("Latte UHT Parmalat 1L", "Prima: EUR 1.59  Ora: EUR 0.99"),
        ("Detersivo Casa 2L", "Prima: EUR 5.49  Ora: EUR 3.79"),
    ]

    top = 340
    for title, price_line in offers:
        draw.rounded_rectangle((80, top, 1120, top + 260), radius=30, fill=(255, 240, 208))
        draw.text((120, top + 40), title, font=title_font, fill=(47, 44, 38))
        draw.text((120, top + 150), price_line, font=body_font, fill=(47, 44, 38))
        top += 320

    image.save(destination)
    return destination


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "data" / "validation-flyer.png"
    create_sample_flyer(output)
    print(output)
