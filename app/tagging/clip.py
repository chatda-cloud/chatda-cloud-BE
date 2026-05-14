import clip
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
torch.set_num_threads(1)

_model = None
_preprocess = None


def _get_model():
    global _model, _preprocess
    if _model is None or _preprocess is None:
        _model, _preprocess = clip.load("ViT-B/32", device=device)
    return _model, _preprocess


def encode_text(text: str) -> list[float]:
    model, _ = _get_model()
    with torch.no_grad():
        tokens = clip.tokenize([text]).to(device)
        vector = model.encode_text(tokens)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector.cpu().numpy()[0].tolist()


def encode_image_from_pil(image) -> list[float]:
    model, preprocess = _get_model()
    tensor = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        vector = model.encode_image(tensor)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector.cpu().numpy()[0].tolist()
