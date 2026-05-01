import clip
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)


def encode_text(text: str) -> list[float]:
    with torch.no_grad():
        tokens = clip.tokenize([text]).to(device)
        vector = model.encode_text(tokens)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector.cpu().numpy()[0].tolist()


def encode_image_from_pil(image) -> list[float]:
    tensor = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        vector = model.encode_image(tensor)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector.cpu().numpy()[0].tolist()
