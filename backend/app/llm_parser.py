import httpx
import asyncio
import logging
from typing import List

# basic logger for LLM requests
logging.basicConfig()
logger = logging.getLogger("bmad.llm")
logger.setLevel(logging.INFO)

def _mask_key(key: str):
    if not key:
        return None
    return (key[:4] + "..." + key[-4:]) if len(key) > 8 else (key[:2] + "...")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
HUGGINGFACE_INFERENCE_URL = "https://router.huggingface.co/v1/models"


async def parse_with_llm(lines: List[str], api_key: str, model: str = "gpt-3.5-turbo", provider: str = "openai") -> List[str]:
    """Extract menu items using a remote LLM provider. Supports 'openai' and 'huggingface'.

    Returns a list of item names (strings).
    """
    if not api_key:
        raise ValueError("API key required for LLM parsing")

    text = "\n".join(lines)
    prompt = (
        f"Extract probable food menu item names from the following noisy OCR output. "
        f"Return a JSON array of item names only, without prices or descriptions.\n\n{text}\n\n"
        "Example response: [\"Aloo Bonda\", \"Onion Pakoda\"]"
    )

    def _mask(key: str):
        if not key:
            return None
        return (key[:4] + "..." + key[-4:]) if len(key) > 8 else (key[:2] + "...")

    logger.info("LLM request: provider=%s model=%s api_key=%s prompt_preview=%s", provider, model, _mask(api_key), (prompt[:300].replace('\n', ' ') + '...'))

    # Use Hugging Face official client when provider is 'huggingface' to improve compatibility
    if provider == "huggingface":
        try:
            from huggingface_hub import InferenceClient
        except Exception as e:
            raise RuntimeError("huggingface-hub library not installed; add it to requirements.txt")

        def hf_call():
            # run in thread to avoid blocking async loop
            client = InferenceClient(api_key=api_key)
            # Try chat completions (if model supports chat). Fall back to text_generation.
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
                # completion.choices[0].message may be an object; try to extract text
                try:
                    c0 = completion.choices[0]
                    # c0.message may be a dict with 'content' or an object
                    msg = getattr(c0, 'message', None) or (c0.get('message') if isinstance(c0, dict) else None)
                    if isinstance(msg, dict):
                        return msg.get('content') or str(msg)
                    return str(msg)
                except Exception:
                    return str(completion)
            except Exception:
                # fallback to text generation
                resp = client.text_generation.create(model=model, inputs=prompt, max_new_tokens=256)
                # resp could be dict or list
                if isinstance(resp, list) and resp:
                    first = resp[0]
                    if isinstance(first, dict) and 'generated_text' in first:
                        return first['generated_text']
                    return str(first)
                if isinstance(resp, dict):
                    return resp.get('generated_text') or str(resp)
                return str(resp)

        content = await asyncio.to_thread(hf_call)

    else:
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You extract menu item names from OCR output."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 512,
            }
            r = await client.post(OPENAI_CHAT_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = data["choices"][0].get("text", "")

    # Try to extract a JSON array from the model output
    import json

    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = content[start : end + 1]
        try:
            arr = json.loads(snippet)
            return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass

    # Fallback: lines from content
    lines_out = [l.strip() for l in content.splitlines() if l.strip()]
    cleaned = []
    for l in lines_out:
        l = l.lstrip("-•*0123456789. )\t ")
        if l:
            cleaned.append(l)
    return cleaned


async def describe_and_prompt(names: List[str], api_key: str, model: str = "gpt-3.5-turbo", provider: str = "openai"):
    """For each dish name, produce a short appetizing description and a photorealistic image prompt.

    Returns list of {name, description, prompt}.
    """
    if not api_key:
        raise ValueError("API key required for LLM description generation")

    text = "\n".join(names)
    instruction = (
        "For each of the following dish names, return a JSON array of objects with keys: 'name', 'description', and 'prompt'. "
        "'description' should be a one-sentence appetizing description of the dish. 'prompt' should be a concise but discriptive photorealistic image prompt suitable for image generation (include style hints like 'photorealistic, food photography, shallow depth of field, natural lighting, high detail, appetizing'). "
        f"Here are the dish names:\n\n{text}\n\nReturn only valid JSON array."
    )

    # Delegate to unified parse_and_describe if available to avoid duplicate LLM calls
    return await parse_and_describe(names, api_key=api_key, model=model, provider=provider)


async def parse_and_describe(lines: List[str], api_key: str, model: str = "gpt-3.5-turbo", provider: str = "openai"):
    """Single-call function: from noisy OCR `lines` return a JSON array of objects
    [{name, description, prompt}] where 'description' is a one-sentence appetizing
    description and 'prompt' is a concise photorealistic image prompt.
    """
    if not api_key:
        raise ValueError("API key required for LLM parsing")

    text = "\n".join(lines)
    instruction = (
        "Extract probable food menu item names from the following noisy OCR output. "
        "For each item return an object with keys: 'name', 'description', and 'prompt'. "
        "'description' should be a one-sentence appetizing description. 'prompt' should be a concise photorealistic image prompt suitable for image generation. "
        "Return ONLY a valid JSON array of objects.\n\n"
        f"{text}\n\n"
        "Example: [{\"name\": \"Aloo Bonda\", \"description\": \"Crispy potato fritters...\", \"prompt\": \"Photorealistic food photography of Aloo Bonda...\"}]"
    )

    logger.info("LLM request: provider=%s model=%s api_key=%s instruction_preview=%s", provider, model, _mask_key(api_key), (instruction[:300].replace('\n', ' ') + '...'))

    # HuggingFace path
    if provider == "huggingface":
        try:
            from huggingface_hub import InferenceClient
        except Exception:
            raise RuntimeError("huggingface-hub library not installed; add it to requirements.txt")

        def hf_call():
            client = InferenceClient(api_key=api_key)
            try:
                completion = client.chat.completions.create(model=model, messages=[{"role": "user", "content": instruction}])
                c0 = completion.choices[0]
                msg = getattr(c0, 'message', None) or (c0.get('message') if isinstance(c0, dict) else None)
                if isinstance(msg, dict):
                    return msg.get('content') or str(msg)
                return str(msg)
            except Exception:
                resp = client.text_generation.create(model=model, inputs=instruction, max_new_tokens=512)
                if isinstance(resp, list) and resp:
                    first = resp[0]
                    if isinstance(first, dict) and 'generated_text' in first:
                        return first['generated_text']
                    return str(first)
                if isinstance(resp, dict):
                    return resp.get('generated_text') or str(resp)
                return str(resp)

        content = await asyncio.to_thread(hf_call)
    else:
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You extract menu items and generate descriptions/prompts in JSON."},
                    {"role": "user", "content": instruction},
                ],
                "temperature": 0.0,
                "max_tokens": 1024,
            }
            r = await client.post(OPENAI_CHAT_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = data["choices"][0].get("text", "")

    # extract JSON array
    import json
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = content[start:end+1]
        try:
            arr = json.loads(snippet)
            out = []
            for obj in arr:
                name = obj.get('name') if isinstance(obj, dict) else None
                desc = obj.get('description') if isinstance(obj, dict) else None
                prompt = obj.get('prompt') if isinstance(obj, dict) else None
                out.append({'name': name or '', 'description': desc or '', 'prompt': prompt or ''})
            return out
        except Exception:
            pass

    # Fallback: build objects from lines
    out = []
    for l in lines:
        n = l.strip()
        if not n:
            continue
        desc = f"A delicious serving of {n}, flavorful and freshly prepared."
        prompt = f"Photorealistic food photography of {n}, plated, high detail, natural lighting, shallow depth of field, appetizing"
        out.append({'name': n, 'description': desc, 'prompt': prompt})
    return out
