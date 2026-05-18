"""Image compression for the upload / webscrape pipeline."""

LARGE_IMAGE_BYTES = 500 * 1024


def compress_image_if_needed(image: bytes) -> bytes:
    """Placeholder: compress when over the size threshold. Not implemented yet."""
    return image
