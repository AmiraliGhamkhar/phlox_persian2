"""
Regression tests for the RAG chunking pipeline.

The chunkers were historically vendored from LangChain and are now provided by
the ``langchain-text-splitters`` dependency. These tests lock the exact chunk
output for representative texts so a dependency swap cannot silently change
what gets embedded and stored in the vector store.

``len`` is used as the length function (instead of the tiktoken-based
``openai_token_count``) so the tests stay deterministic and offline; the
boundary/merge logic being locked is independent of the length function.
"""

from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from server.rag.chunking_utils import openai_token_count
from server.rag.semantic_chunker import ClusterSemanticChunker


def _make_splitter(**kwargs: Any) -> RecursiveCharacterTextSplitter:
    defaults: dict[str, Any] = {
        "chunk_size": 50,
        "chunk_overlap": 0,
        "length_function": len,
        "separators": ["\n\n", "\n", ".", "?", "!", " ", ""],
        "keep_separator": True,
    }
    defaults.update(kwargs)
    return RecursiveCharacterTextSplitter(**defaults)


def test_recursive_token_chunker_chunks_persian_clinical_text():
    """Splits mixed Persian/English clinical text on the configured separators."""
    splitter = _make_splitter()
    text = (
        "بیمار با شکایت سردرد مراجعه کرده است. "
        "Blood pressure was 130/85. "
        "در معاینه علائم حیاتی پایدار بود.\n"
        "سابقه دیابت نوع دو از پنج سال پیش دارد. "
        "HbA1c latest reading is 7.2%."
    )
    chunks = splitter.split_text(text)
    assert chunks, "expected at least one chunk"
    for chunk in chunks:
        assert len(chunk) <= 60  # small slack over chunk_size
    # The exact boundaries (including the upstream separator attachment
    # quirk: leading ". " on follow-up chunks) are locked here to catch
    # behavior drift on future upgrades.
    assert chunks == [
        "بیمار با شکایت سردرد مراجعه کرده است",
        ". Blood pressure was 130/85",
        ". در معاینه علائم حیاتی پایدار بود.",
        "سابقه دیابت نوع دو از پنج سال پیش دارد",
        ". HbA1c latest reading is 7.2%.",
    ]


def test_semantic_chunker_clusters_sentences(monkeypatch):
    """ClusterSemanticChunker groups sentences into clusters via embeddings."""
    # Keep the test offline: the inner splitter normally token-counts via
    # tiktoken, which downloads an encoding file on first use.
    monkeypatch.setattr("server.rag.semantic_chunker.openai_token_count", len)
    chunker = ClusterSemanticChunker(
        embedding_function=lambda texts: [[1.0] * 8] * len(texts),
        max_chunk_size=150,
        min_chunk_size=50,
    )
    text = "یک. دو. سه. چهار. پنج. شش. هفت. هشت. نه. ده."
    docs = chunker.split_text(text)
    assert docs, "expected at least one cluster"
    joined = " ".join(docs)
    for token in ("یک", "ده"):
        assert token in joined


def test_openai_token_count_falls_back_on_encoding_failure(monkeypatch):
    """The token-count helper degrades to a character estimate when tiktoken cannot resolve an encoding."""
    import tiktoken

    def boom(_name):
        raise ValueError("unknown encoding (test)")

    monkeypatch.setattr(tiktoken, "get_encoding", boom)
    text = "متن بالینی نمونه برای شمارش توکن"
    assert openai_token_count(text) == len(text) // 4


def test_openai_token_count_falls_back_on_transient_error(monkeypatch):
    """Network/OS failures while loading the encoding also degrade gracefully."""
    import tiktoken

    def boom(_name):
        raise OSError("offline (test)")

    monkeypatch.setattr(tiktoken, "get_encoding", boom)
    text = "متن بالینی نمونه برای شمارش توکن"
    assert openai_token_count(text) == len(text) // 4
