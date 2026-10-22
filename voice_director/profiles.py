"""Frozen capability snapshots used by the offline compiler.

Repository-derived claims are pinned to the commits in references/frozen-sources.json.
Other profiles are declared by TaskSpec v1 and are not live capability discovery.
"""

from copy import deepcopy

STATUS = ("native_exact", "model_guided", "unsupported", "not_requested")
CONTROL_NAMES = (
    "delivery",
    "energy",
    "pace",
    "emphasis",
    "pauses",
    "pronunciation_overrides",
    "fish_tags",
)

SOURCE_COMMITS = {
    "fish_s2_pro": "fishaudio/fish-speech@541566932abbaebcb0a40e562a1f846738383f38",
    "cosyvoice": "QwenAudio/CosyVoice@074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc",
    "chattts": "2noise/ChatTTS@77b89ee281cd479f5b1a787ada330dc975ca1f2a",
    "parler": "huggingface/parler-tts@d108732cd57788ec86bc857d99a6cabd66663d68",
    "f5": "SWivid/F5-TTS@2f866649b779881af8bd644e76b9a6d95053da29",
    "whisperx": "m-bain/whisperX@db8fde4d31a3e7f49fe5835938685a76f5ba5477",
}

_PROFILES = {
    "eleven_v4": {
        "profile_id": "eleven-v4-task-spec-v1",
        "evidence": "TaskSpec v1; profile is declared, not live-discovered",
        "capabilities": {
            "delivery": "model_guided",
            "energy": "model_guided",
            "pace": "model_guided",
            "emphasis": "model_guided",
            "pauses": "model_guided",
            "pronunciation_overrides": "unsupported",
            "fish_tags": "unsupported",
        },
        "pause_tags": {"short": "[short pause]", "long": "[long pause]"},
        "experimental_controls": ["delivery", "energy", "pace", "emphasis"],
        "notes": [
            "Pause tags are qualitative model guidance; target_ms is not an exact duration.",
            "Never compile this profile as SSML.",
            "Requested delivery, energy, pace, and emphasis compile into an experimental natural-language cue tag in draft_text; audition is required and word-level emphasis is not deterministic.",
        ],
    },
    "azure": {
        "profile_id": "azure-ssml-task-spec-v1",
        "evidence": "TaskSpec v1; selected voice support must be verified by the caller",
        "capabilities": {
            "delivery": "unsupported",
            "energy": "unsupported",
            "pace": "unsupported",
            "emphasis": "unsupported",
            "pauses": "native_exact",
            "pronunciation_overrides": "unsupported",
            "fish_tags": "unsupported",
        },
        "notes": [
            "Break duration is serialized from target_ms; this does not certify voice playback behavior.",
            "An express-as style is emitted only when explicitly allowlisted in the voice profile.",
            "This profile does not assume Xiaoxiao or any other voice supports a requested style.",
        ],
    },
    "fish_s2_pro": {
        "profile_id": "fish-speech-54156693",
        "evidence": SOURCE_COMMITS["fish_s2_pro"],
        "capabilities": {
            "delivery": "unsupported",
            "energy": "unsupported",
            "pace": "unsupported",
            "emphasis": "unsupported",
            "pauses": "model_guided",
            "pronunciation_overrides": "unsupported",
            "fish_tags": "model_guided",
        },
        "pause_tags": {"short": "[pause]", "long": "[pause]"},
        "notes": [
            "Only explicitly requested [excited] and [whisper] fish_tags plus [pause] events are emitted.",
            "Free-text delivery, energy, pace, and emphasis have no mapped encoding and are unsupported.",
            "Fish Audio code and S2-Pro weight license materials are listed separately; review them before production use.",
        ],
    },
    "cosyvoice": {
        "profile_id": "cosyvoice-074ca6dc",
        "evidence": SOURCE_COMMITS["cosyvoice"],
        "capabilities": {
            "delivery": "model_guided",
            "energy": "model_guided",
            "pace": "model_guided",
            "emphasis": "model_guided",
            "pauses": "model_guided",
            "pronunciation_overrides": "model_guided",
            "fish_tags": "unsupported",
        },
        "notes": [
            "Text and instruct_text remain separate; instructions do not alter the source text.",
            "Natural-language instructions are model-guided, not deterministic word-level controls.",
        ],
    },
    "chattts": {
        "profile_id": "chattts-77b89ee2",
        "evidence": SOURCE_COMMITS["chattts"],
        "capabilities": {
            "delivery": "unsupported",
            "energy": "unsupported",
            "pace": "unsupported",
            "emphasis": "unsupported",
            "pauses": "model_guided",
            "pronunciation_overrides": "unsupported",
            "fish_tags": "unsupported",
        },
        "allowed_tokens": {"short": "[uv_break]", "long": "[lbreak]"},
        "notes": [
            "Only tokens explicitly allowlisted in the input voice profile may be emitted.",
            "The frozen README describes pause/laughter token-level controls and says generic multi-emotion control is not available in the released model.",
        ],
    },
    "parler": {
        "profile_id": "parler-tts-d108732c",
        "evidence": SOURCE_COMMITS["parler"],
        "capabilities": {
            "delivery": "model_guided",
            "energy": "model_guided",
            "pace": "model_guided",
            "emphasis": "model_guided",
            "pauses": "model_guided",
            "pronunciation_overrides": "unsupported",
            "fish_tags": "unsupported",
        },
        "notes": [
            "Global voice description and per-segment delivery remain separate model-guided fields.",
            "Punctuation is not rewritten or added to the immutable script.",
        ],
    },
    "f5": {
        "profile_id": "f5-tts-2f866649",
        "evidence": SOURCE_COMMITS["f5"],
        "capabilities": {
            "delivery": "unsupported",
            "energy": "unsupported",
            "pace": "unsupported",
            "emphasis": "unsupported",
            "pauses": "unsupported",
            "pronunciation_overrides": "unsupported",
            "fish_tags": "unsupported",
        },
        "notes": [
            "This adapter describes chunk boundaries only; chunking does not imply emotion control.",
            "No inference, speed control, or cross-fade is performed.",
        ],
    },
}

_UNASSESSED_LICENSE_REVIEW = {
    "status": "review_required_before_production",
    "code": {"name": None, "status": "not_assessed"},
    "weights": {"name": None, "status": "not_assessed"},
    "source": {"status": "not_assessed", "note": "No license materials were assessed for this backend."},
}

_FISH_LICENSE_REVIEW = {
    "status": "review_required_before_production",
    "code": {
        "name": "Fish Audio Community License Agreement, Version 1.0",
        "status": "review_required_before_production",
    },
    "weights": {
        "name": "Fish Audio Research License (S2-Pro weights)",
        "status": "review_required_before_production",
    },
    "source": {
        "repository": "fishaudio/fish-speech",
        "commit": "541566932abbaebcb0a40e562a1f846738383f38",
        "files": [
            {"path": "README.md", "sha256": "BAA129FAC0B9D32C55B3972BF8CCABEAB3EBBA1CA435E313E20C0ADEA5A7088D"},
            {"path": "LICENSE", "sha256": "733A32442087ACBDA12ECAFE8E71EB8EE5890C89B50CE7AC4EA3777FAA3C823E"},
        ],
        "note": "Source snapshot identifies separate code/license materials and S2-Pro weight terms; review before production use.",
    },
}


def get_license_review(backend):
    review = _FISH_LICENSE_REVIEW if backend == "fish_s2_pro" else _UNASSESSED_LICENSE_REVIEW
    return deepcopy(review)


def get_profile(backend):
    profile = _PROFILES.get(backend)
    if profile is None:
        return None
    result = deepcopy(profile)
    result["capabilities"].setdefault("fish_tags", "unsupported")
    result["license_review"] = get_license_review(backend)
    return result


def list_profiles():
    return {name: get_profile(name) for name in sorted(_PROFILES)}
