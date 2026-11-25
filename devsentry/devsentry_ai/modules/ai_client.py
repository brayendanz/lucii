"""
Client AI untuk versi hosted/online.

Memakai Anthropic API (Claude) lewat HTTPS — cocok untuk dijalankan di
server cloud mana pun karena tidak perlu meng-install model AI apa pun
di server itu sendiri. Cukup set ANTHROPIC_API_KEY di environment variable
layanan hosting-mu (Render/Railway/Fly.io/dll).
"""

import requests
import config


class AIError(Exception):
    pass


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


def chat(messages, system_prompt, model=None, temperature=0.4, max_tokens=4096):
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    (role "system" dipisah lewat parameter system_prompt, sesuai format Anthropic API)
    """
    if not config.ANTHROPIC_API_KEY:
        raise AIError(
            "ANTHROPIC_API_KEY belum diset. Tambahkan di Environment Variables "
            "dashboard hosting-mu (Render/Railway/dll), lalu redeploy."
        )

    model = model or config.ANTHROPIC_MODEL
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": messages,
    }

    try:
        resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=120)
    except requests.exceptions.RequestException as e:
        raise AIError(f"Gagal menghubungi Anthropic API: {e}")

    if resp.status_code == 401:
        raise AIError("API key tidak valid. Periksa ANTHROPIC_API_KEY di environment variable.")
    if resp.status_code == 429:
        raise AIError("Rate limit tercapai. Coba lagi sebentar lagi.")
    if resp.status_code >= 400:
        raise AIError(f"Anthropic API error ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    blocks = data.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return text


def chat_multi_model(messages, system_prompt, model_ids, temperature=0.4, max_tokens=4096):
    """
    Fitur Multi-Model Intelligence: kirim prompt yang sama ke beberapa model
    sekaligus, kembalikan hasil masing-masing untuk dibandingkan.
    Mengembalikan dict {model_id: {"reply": str} | {"error": str}}.
    """
    results = {}
    for model_id in model_ids:
        try:
            reply = chat(messages, system_prompt=system_prompt, model=model_id,
                         temperature=temperature, max_tokens=max_tokens)
            results[model_id] = {"reply": reply}
        except AIError as e:
            results[model_id] = {"error": str(e)}
    return results
