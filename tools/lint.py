#!/usr/bin/env python3
"""Проверка готовых глав на дефекты машинного текста и порчу фактов.

Что ловит:
  1. Длинное и среднее тире.
  2. Иностранные слова посреди русской фразы (модель их иногда подставляет).
  3. Антитезы «не X, а Y» и родственные конструкции.
  4. Канцелярит и заглушки уверенности.
  5. Заголовки по шаблону «Термин: пояснение».
  6. Порчу имён моделей и библиотек: сверяет их с белым списком.
  7. Пустые блоки, оставшиеся после сбоя генерации.

Запуск:
    python3 tools/lint.py site/*.html
    python3 tools/lint.py site/ch10.html --fail   # ненулевой код возврата при находках
"""

import argparse
import re
import sys
from pathlib import Path

# Латиница, допустимая в русском тексте: термины, имена, библиотеки.
ALLOWED = set(
    """API HTTP HTTPS JSON JSONL YAML CSV SQL HTML CSS SVG PDF DOCX UTF Unicode
    RAG LLM GPU CPU TPU RAM MCP BPE SFT LoRA QLoRA DPO RLHF PPO KTO ORPO PEFT TRL
    GQA MQA MHA RoPE ALiBi YaRN NTK KV MoE CoT ReAct RRF BM25 HNSW ANN IVF PQ
    nDCG MRR MAP recall precision top span NaN CI CD SLA SLO API TTFT TPOT QPS RPS
    WER CER MOS CTC STT TTS VAD NER POS BIO BIOES CRF HMM UAS LAS PPL FID
    NumPy PyTorch TensorFlow JAX Python pandas sklearn scikit tiktoken transformers
    sentence FAISS Qdrant Weaviate Milvus Chroma PostgreSQL pgvector Elasticsearch
    OpenSearch Redis Docker Kubernetes pytest Pydantic FastAPI LangChain LlamaIndex
    ReLU GELU SiLU SwiGLU tanh sigmoid softmax dropout Adam AdamW SGD MSE MAE
    RMSNorm LayerNorm BatchNorm FlashAttention
    BERT GPT LLaMA Qwen Mistral Gemma Claude Chinchilla Instruct
    word2vec GloVe fastText PPMI LSA cl100k
    OpenAI Anthropic DeepMind Google Meta Stanford HuggingFace
    Jurafsky Martin Prince Firth Mikolov Alammar Grootendorst Huyen Raschka Vaswani
    Understanding Deep Learning Speech Language Processing Scratch Hands On
    Matryoshka Leaky Byte Pair Encoding Grouped Multi Query Attention Chain Thought
    Supervised Fine Tuning Direct Preference Optimization Reinforcement Human Feedback
    exp log cos sin sqrt max min sum argmax softmax
    pre post skip few shot zero one self cross bi encoder
    seed temperature passage query intent order urgency status refund complaint
    id ru en bash python js sh
    nbsp mdash ndash lt gt amp quot
    Word Excel PowerPoint Camelot Tabula unstructured PyMuPDF Schema
    verdict reasoning answer confidence sources chunk text metadata
    Instruct Chat Base Small Large Mini Turbo Flash Sonnet Opus Haiku
    Okapi Reciprocal Rank Fusion Cross Encoder Bi Dense Sparse Hybrid
    ADJ ADP ADV AUX DET NOUN NUM PRON PROPN PUNCT SCONJ VERB CCONJ INTJ PART SYM
    NNP NNS NNPS VBD VBG VBN VBZ JJR RBS PRP WDT WRB
    PER ORG LOC GPE MISC FAC NORP DATE TIME MONEY PERCENT
    Penn Treebank Universal Dependencies WSJ OntoNotes CoNLL PropBank FrameNet
    spaCy seqeval Stanza NLTK Natasha librosa jiwer Whisper faster Piper
    Viterbi Levenshtein Hearst Vilain Bagga Baldwin Luo Grosz Ramshaw Lafferty
    McCallum Pereira Marneffe Nivre Mintz Fillmore Palmer Gildea Kingsbury Graves""".split()
)
# Дополнительный список ведётся отдельным файлом, чтобы пополнять его без правки кода.
EXTRA = Path(__file__).resolve().parent / "lint_allow.txt"
if EXTRA.exists():
    ALLOWED |= {
        w for line in EXTRA.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#") for w in line.split()
    }

ALLOWED_LOWER = {w.lower() for w in ALLOWED}

# Слово латиницей целиком, включая написание через дефис: fine-tuning ловится
# как одно слово, иначе половинки прячутся друг за друга.
LATIN = re.compile(r"(?<![\w>/=\"'.])([A-Za-z][A-Za-z]*(?:-[A-Za-z]+)*)"
                   r"(?![\w<]|\.[A-Za-z0-9])")  # точка в конце предложения слово больше не прячет

STYLE = [
    (re.compile(r"GPT-5\.6|Luna\.?5|gpt-5\.6-luna", re.I), "модель подставила своё имя вместо настоящего"),
    (re.compile(r"[—–]"), "длинное или среднее тире"),
    (re.compile(r"\bне просто\b", re.I), "антитеза «не просто»"),
    (re.compile(r"\bне [^.,;:!?<>]{2,60}, а (?:не\s+)?[а-яё]", re.I), "антитеза «не X, а Y»"),
    (re.compile(r"\b(являет|являют)ся\b", re.I), "канцелярит «является»"),
    (re.compile(r"\bосуществля[ею]т", re.I), "канцелярит «осуществляет»"),
    (re.compile(r"\bпредставля[ею]т собой\b", re.I), "канцелярит «представляет собой»"),
    (re.compile(r"\bв рамках\b", re.I), "канцелярит «в рамках»"),
    (re.compile(r"\bстоит отметить\b", re.I), "заглушка «стоит отметить»"),
    (re.compile(r"\bважно подчеркнуть\b", re.I), "заглушка «важно подчеркнуть»"),
    (re.compile(r"\bбезусловно\b", re.I), "заглушка «безусловно»"),
    (re.compile(r"\bиграет (?:ключевую|важную|значимую|решающую)\b", re.I), "раздутая значимость"),
    (re.compile(r"\bоткрывает (?:новые )?горизонт", re.I), "раздутая значимость"),
    (re.compile(r"\bпогружени[ея] в\b", re.I), "слово-маркер «погружение»"),
    (re.compile(r"\bэкосистем", re.I), "слово-маркер «экосистема»"),
    (re.compile(r"\b(комплексн|инновационн|бесшовн)", re.I), "слово-маркер"),
    (re.compile(r"[a-zA-Zа-яА-ЯёЁ]+-(?:окружени|нагрузк|пользовател|среда)", re.I),
     "микс языков в термине"),
]


def strip_noise(src: str) -> str:
    """Убирает код, схемы и разметку: там латиница законна."""
    body = re.sub(r"<(pre|svg|script|style)\b.*?</\1>", " ", src, flags=re.S)
    body = re.sub(r"<code\b.*?</code>", " ", body, flags=re.S)
    # Список источников состоит из английских названий работ, это норма.
    body = re.sub(r'<div class="sources">.*?</div>', " ", body, flags=re.S)
    # В глоссарии у каждого термина стоит английское написание, это тоже норма.
    body = re.sub(r'<span class="en">.*?</span>', " ", body, flags=re.S)
    body = re.sub(r"<dt>.*?</dt>", " ", body, flags=re.S)
    # Языковой пример в курсиве это цитата, а не порча текста: «слово back в a
    # back seat». Одиночное английское слово посреди русской фразы курсивом
    # не помечается и остаётся под проверкой.
    body = re.sub(r"<(i|em)\b[^>]*>.*?</\1>", " ", body, flags=re.S)
    body = re.sub(r"<a\b[^>]*>", " ", body)
    body = re.sub(r"<[^>]+>", " ", body)
    # Английский оригинал термина в скобках это норма учебника: «время до первого
    # токена (time to first token, TTFT)». Скобки, где нет ни одной кириллической
    # буквы, из проверки на иностранные слова убираем.
    body = re.sub(r"\(([^()]*)\)",
                  lambda m: " " if not re.search(r"[а-яё]", m.group(1), re.I) else m.group(0), body)
    # Иностранное слово в кавычках это цитата: «Gelidium», «United Airlines».
    return re.sub(r"«([^«»]*)»",
                  lambda m: " " if not re.search(r"[а-яё]", m.group(1), re.I) else m.group(0), body)


def check(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    text = strip_noise(src)
    issues: list[str] = []

    for word in set(LATIN.findall(text)):
        # однобуквенные и двухбуквенные обозначения это математика, а не порча текста
        if len(word) < 3 or all(p.lower() in ALLOWED_LOWER for p in word.split("-")):
            continue
        if word.lower() not in ALLOWED_LOWER:
            m = re.search(r".{0,60}\b" + re.escape(word) + r"\b.{0,60}", text)
            issues.append(f"иностранное слово «{word}»: …{' '.join(m.group(0).split())}…")

    for rx, why in STYLE:
        for m in rx.finditer(text):
            frag = " ".join(text[max(0, m.start() - 50):m.start() + 70].split())
            issues.append(f"{why}: …{frag}…")

    for h in re.findall(r"<h[23][^>]*>([^<]+)</h[23]>", src):
        if ":" in h and not re.search(r"\d", h):
            issues.append(f"заголовок по шаблону «термин: пояснение»: {h}")

    if re.search(r"<p>\s*</p>", src):
        issues.append("пустой абзац: блок не сгенерировался")
    if re.search(r'<p class="standfirst">\s*</p>', src):
        issues.append("пустой лид главы")
    empty_why = len(re.findall(r'<div class="why">\s*</div>', src))
    if empty_why:
        issues.append(f"вопросов квиза без объяснения: {empty_why}")

    # Обрыв генерации: модель иногда останавливается на середине фразы. Тогда
    # закрывающего тега нет, а текст кончается без знака препинания.
    opens, closes = src.count("<p>") + src.count("<p "), src.count("</p>")
    if opens != closes:
        issues.append(f"оборванный абзац: открыто {opens}, закрыто {closes}")
    for m in re.finditer(r"<p>(.*?)(?=<p>|</p>)", src, re.S):
        # строка из двух и более ссылок это навигация, а не оборванная фраза
        if m.group(1).count("<a ") >= 2:
            continue
        body = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        # строка из ссылок через разделитель это не обрыв, и короткие подписи тоже
        if len(body) > 60 and not re.search(r"[.!?:»)\]·…]\s*$", body):
            issues.append(f"абзац обрывается без знака препинания: …{body[-70:]}")
    if "<figcaption>\n\n</figcaption>" in src:
        issues.append("пустая подпись к схеме")

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fail", action="store_true", help="ненулевой код возврата при находках")
    args = ap.parse_args()

    total = 0
    for f in args.files:
        path = Path(f)
        issues = check(path)
        if issues:
            print(f"\n{path.name}: {len(issues)}")
            for i in issues[:12]:
                print("  ·", i)
            if len(issues) > 12:
                print(f"  … и ещё {len(issues) - 12}")
            total += len(issues)

    print(f"\nвсего находок: {total}")
    return 1 if (args.fail and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
