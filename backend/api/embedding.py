"""Generate vector embeddings using OpenCLIP."""

import io
import torch
import open_clip
from PIL import Image

# Initialize the model globally so we don't reload it per image
# We use ViT-B-32 as a fast and good default
MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"

# Note: In a real production app, we would load this lazily or in a worker process,
# but for simplicity we load it when the module is imported.
_model, _, _preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
_model.eval()  # Set model to evaluation mode

def generate_embedding(image_bytes: bytes) -> list[float]:
    """
    Generate a vector embedding for an image using OpenCLIP.
    
    Args:
        image_bytes: The raw image bytes.
        
    Returns:
        A list of floats representing the embedding vector.
    """
    try:
        # Load image from bytes
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # Preprocess the image and add batch dimension
        image_input = _preprocess(image).unsqueeze(0)
        
        # Calculate features
        with torch.no_grad():
            image_features = _model.encode_image(image_input)
            
            # Normalize the features to length 1
            image_features /= image_features.norm(dim=-1, keepdim=True)
            
        # Convert to list of floats
        return image_features.squeeze(0).cpu().numpy().tolist()
        
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

_tokenizer = open_clip.get_tokenizer(MODEL_NAME)

def generate_text_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for text using OpenCLIP.
    
    Args:
        text: The text to embed.
        
    Returns:
        A list of floats representing the embedding vector.
    """
    try:
        text_input = _tokenizer([text])
        
        with torch.no_grad():
            text_features = _model.encode_text(text_input)
            text_features /= text_features.norm(dim=-1, keepdim=True)
            
        return text_features.squeeze(0).cpu().numpy().tolist()
    except Exception as e:
        print(f"Error generating text embedding: {e}")
        return []
