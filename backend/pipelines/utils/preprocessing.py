from PIL import Image

def resize_for_condition_image(image: Image.Image, width: int, height: int) -> Image.Image:
    """Preprocess image to match requested width and height."""
    return image.resize((width, height), Image.LANCZOS)
