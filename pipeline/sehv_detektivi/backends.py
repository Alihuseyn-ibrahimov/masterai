"""Səhv Detektivi modelinin harada işlədiyi: vLLM (GPU, OpenAI-uyğun API) və ya lokal.

Adapter (QLoRA, Qwen2.5-1.5B) repoda DEYİL: Colab-da öyrədilib, Google Drive-dadır. Server
1 nüvəli VPS-dir və torch QOYULMUR (gün 15/17 qaydası), ona görə iki yol var:

* `vllm`: `vllm serve Qwen/Qwen2.5-1.5B-Instruct --enable-lora --lora-modules sehv=<adapter>`
  (Colab + Cloudflare tuneli, `ml/vllm_serve.ipynb` naxışı). Qəbz oxuyucusu ilə EYNİ baza
  modeldir, yəni bir `vllm serve` iki adapteri (`receipts`, `sehv`) birlikdə verə bilər.
* `local`: transformers + peft eyni prosesdə (müəllimin GPU-lu kompüteri, Colab). Adapter
  yolu lokal qovluq (`/content/drive/MyDrive/...`) və ya HF repo adı (`istifadeci/sehv-lora`).

Heç biri qurulmayıbsa backend YOXDUR və `detector` yalnız sympy ilə işləyir.

Hər backend iki şey verir: `generate` (modelin xam JSON mətni) və `null_prob` («həll
düzgündür» ehtimalı, kalibrasiya eşiyi üçün). `null_prob` hesablana bilmirsə None-dur və
eşik tətbiq olunmur (vLLM-in chat API-si namizəd ehtimallarını birbaşa vermir).
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import Protocol

from .prompts import SYSTEM_PROMPT_SHORT, build_messages, format_user

logger = logging.getLogger(__name__)

DEFAULT_BASE = "Qwen/Qwen2.5-1.5B-Instruct"
MAX_NEW_TOKENS = 200


class Backend(Protocol):
    name: str

    def generate(self, domain: str, problem: str, steps: list[str]) -> str: ...

    def null_prob(self, domain: str, problem: str, steps: list[str]) -> float | None: ...


class VllmBackend:
    """OpenAI-uyğun `/v1/chat/completions`. `model` = `--lora-modules` adı (defolt `sehv`).

    Temperatur 0: təlimdəki `do_sample=False` ilə eyni (eyni həll = eyni diaqnoz).
    Prompt adapterin öyrədildiyi QISA sistem promptudur, chat şablonunu vLLM özü qoyur.
    """

    name = "vllm"

    def __init__(self, base_url: str, model: str, *, api_key: str = "", timeout: float = 30.0,
                 transport=None):
        from pipeline.providers import openai_compatible_completer

        self._complete = openai_compatible_completer(
            base_url, model, api_key=api_key, timeout=timeout, max_tokens=MAX_NEW_TOKENS,
            temperature=0.0, transport=transport)

    def generate(self, domain, problem, steps):
        return self._complete(SYSTEM_PROMPT_SHORT, format_user(domain, problem, steps))

    def null_prob(self, domain, problem, steps):
        return None


class LocalBackend:
    """transformers + peft eyni prosesdə. Model ilk sorğuda yüklənir (servis tez açılsın).

    Kod Səhv Detektivi reposundakı `sehv/infer.py::Detective` ilə eynidir: CUDA varsa 4-bit
    NF4, yoxdursa fp32 (CPU-da yavaşdır, amma işləyir).
    """

    name = "local"

    def __init__(self, adapter: str, base: str = DEFAULT_BASE):
        self.adapter = adapter
        self.base = base
        self._model = None
        self._tok = None
        self._torch = None

    def _load(self):
        if self._model is not None:
            return
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        cuda = torch.cuda.is_available()
        kw = {}
        if cuda:
            from transformers import BitsAndBytesConfig
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            kw = {"quantization_config": BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=dtype), "device_map": "auto", "dtype": dtype}
        else:
            kw = {"dtype": torch.float32}
        tok = AutoTokenizer.from_pretrained(self.base)
        model = AutoModelForCausalLM.from_pretrained(self.base, **kw)
        model = PeftModel.from_pretrained(model, self.adapter)
        model.eval()
        self._torch, self._tok, self._model = torch, tok, model

    def _prompt(self, domain, problem, steps) -> str:
        rec = {"domain": domain, "problem": problem, "steps": steps}
        return self._tok.apply_chat_template(build_messages(rec, with_answer=False, short=True),
                                             tokenize=False, add_generation_prompt=True)

    def generate(self, domain, problem, steps):
        self._load()
        inputs = self._tok(self._prompt(domain, problem, steps), return_tensors="pt").to(self._model.device)
        with self._torch.no_grad():
            out = self._model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                       pad_token_id=self._tok.eos_token_id)
        return self._tok.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    def null_prob(self, domain, problem, steps):
        """`{"wrong_step":`-dən sonra " null" və " 1".." N" davamlarının ehtimalı (teacher forcing),
        yalnız bu namizədlər arasında normallaşdırılır. `scripts/calibrate.py`-nin ölçdüyü EYNİ ədəd."""
        self._load()
        torch = self._torch
        prefix = self._prompt(domain, problem, steps) + '{"wrong_step":'
        scores = []
        with torch.no_grad():
            for cand in [" null"] + [f" {i}" for i in range(1, len(steps) + 1)]:
                enc = self._tok(prefix + cand + ",", return_offsets_mapping=True)
                ids = torch.tensor([enc["input_ids"]], device=self._model.device)
                start = next(k for k, (_, end) in enumerate(enc["offset_mapping"]) if end > len(prefix))
                logp = torch.log_softmax(self._model(ids).logits[0, :-1].float(), dim=-1)
                target = ids[0, 1:]
                token_lp = logp[torch.arange(len(target), device=target.device), target]
                scores.append(float(token_lp[start - 1:].sum()))
        return float(torch.softmax(torch.tensor(scores), dim=0)[0])


def _is_local_path(spec: str) -> bool:
    return spec.startswith(("/", "~", ".")) or os.sep in spec and os.path.exists(spec)


def backend_from_env(env=None) -> tuple[Backend | None, str]:
    """Konfiqurasiyadan backend. (backend, izah) - izah jurnala və /health-ə gedir.

    SEHV_BACKEND: boş (avtomatik) | vllm | local | off.
    Avtomatik: `SEHV_VLLM_MODEL` + vLLM ünvanı varsa vllm, `SEHV_ADAPTER_PATH` varsa local.
    """
    env = os.environ if env is None else env
    mode = env.get("SEHV_BACKEND", "").strip().lower()
    if mode == "off":
        return None, "söndürülüb (SEHV_BACKEND=off)"

    base_url = (env.get("SEHV_VLLM_URL", "") or env.get("VLLM_BASE_URL", "")).rstrip("/")
    model = env.get("SEHV_VLLM_MODEL", "").strip()
    if mode == "vllm" or (not mode and base_url and model):
        if not (base_url and model):
            return None, "vllm seçilib, amma SEHV_VLLM_MODEL və ya vLLM ünvanı yoxdur"
        timeout = float(env.get("SEHV_TIMEOUT", "30") or 30)
        api_key = env.get("SEHV_VLLM_API_KEY", "") or env.get("VLLM_API_KEY", "")
        return VllmBackend(base_url, model, api_key=api_key, timeout=timeout), f"vllm ({model})"

    adapter = env.get("SEHV_ADAPTER_PATH", "").strip()
    if mode == "local" or (not mode and adapter):
        if not adapter:
            return None, "local seçilib, amma SEHV_ADAPTER_PATH yoxdur"
        missing = [m for m in ("torch", "transformers", "peft") if importlib.util.find_spec(m) is None]
        if missing:
            return None, f"adapter var, amma {', '.join(missing)} quraşdırılmayıb"
        path = os.path.expanduser(adapter)
        if _is_local_path(adapter) and not os.path.exists(path):
            return None, f"adapter qovluğu tapılmadı: {adapter}"
        return LocalBackend(path if os.path.exists(path) else adapter,
                            env.get("SEHV_BASE_MODEL", "") or DEFAULT_BASE), f"local ({adapter})"

    if mode not in ("", "vllm", "local"):
        return None, f"naməlum SEHV_BACKEND: {mode}"
    return None, "model qoşulmayıb (yalnız sympy)"
