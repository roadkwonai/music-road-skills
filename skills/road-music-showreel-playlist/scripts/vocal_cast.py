"""Explicit vocalist casting rules for Showreel CD image plans."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata


ASSET_KEYS = ("photoA", "photoB", "photoC", "case", "paper")
VOCALS = {"female", "male", "mixed", "unknown", "none"}
ACTS = {"auto", "solo", "duo", "band", "ensemble", "artwork"}
KNOWN_VOCALS = {"female", "male", "mixed"}

_VOCAL_ALIASES = {
    "female": "female", "여성": "female", "여성보컬": "female", "여자": "female", "여자보컬": "female",
    "male": "male", "남성": "male", "남성보컬": "male", "남자": "male", "남자보컬": "male",
    "mixed": "mixed", "혼성": "mixed", "혼성보컬": "mixed",
    "unknown": "unknown", "불명": "unknown", "미상": "unknown",
    "none": "none", "instrumental": "none", "연주곡": "none", "무보컬": "none",
}


def _key(value: str) -> str:
    return re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", value).casefold())


def _vocal(value, *, allow_none: bool = True) -> str:
    if value is None and allow_none:
        return "unknown"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("vocal: female/male/mixed/unknown/none 또는 지정된 별칭이 필요합니다")
    result = _VOCAL_ALIASES.get(_key(value))
    if result is None:
        raise ValueError("vocal: female/male/mixed/unknown/none 또는 지정된 별칭만 사용할 수 있습니다")
    return result


def _act(value) -> str:
    if not isinstance(value, str):
        raise ValueError("act: auto/solo/duo/band/ensemble/artwork 중 하나가 필요합니다")
    result = value.strip().casefold()
    if result not in ACTS:
        raise ValueError("act: auto/solo/duo/band/ensemble/artwork 중 하나가 필요합니다")
    return result


def _artist(value) -> str:
    if not isinstance(value, str):
        raise ValueError("artist: 문자열이어야 합니다")
    return value.strip()


def _subject(vocal: str, act: str, instrumental: bool) -> str:
    if act == "artwork":
        return "an album artwork still life with no singer or performer"
    if instrumental:
        if act == "band":
            return "an instrumental band with no singer"
        if act == "ensemble":
            return "an instrumental ensemble with no singer"
        return "instrumental music imagery with no singer"

    people = {
        "female": "an adult female vocalist",
        "male": "an adult male vocalist",
        "mixed": "adult female and male vocalists",
        "unknown": "an adult vocalist whose gender is not specified",
    }[vocal]
    if act == "solo":
        return f"{people} as a solo performer"
    if act == "duo":
        if vocal == "female":
            return "an adult female vocal duo"
        if vocal == "male":
            return "an adult male vocal duo"
        if vocal == "mixed":
            return "an adult female and male vocal duo"
        return "an adult vocal duo whose genders are not specified"
    if act == "band":
        lead = {
            "female": "an adult female lead vocalist",
            "male": "an adult male lead vocalist",
            "mixed": "adult female and male lead vocalists",
            "unknown": "a lead vocalist whose gender is not specified",
        }[vocal]
        return f"{lead} performing with a band; other members match the stated instrumentation"
    if act == "ensemble":
        if vocal == "female":
            return "an adult female vocal ensemble"
        if vocal == "male":
            return "an adult male vocal ensemble"
        if vocal == "mixed":
            return "an adult mixed-gender vocal ensemble"
        return "an adult vocal ensemble whose genders are not specified"
    return people


def casting_spec(vocal=None, act="auto", artist="", instrumental=False) -> dict:
    """Return a deliberate casting brief without inferring voice from genre or pitch."""
    if not isinstance(instrumental, bool):
        raise ValueError("instrumental: bool이어야 합니다")
    normalized_vocal = _vocal(vocal)
    normalized_act = _act(act)
    artist = _artist(artist)
    if instrumental and normalized_vocal in KNOWN_VOCALS:
        raise ValueError("instrumental=True와 여성/남성/혼성 보컬 지정은 함께 사용할 수 없습니다")
    if instrumental or normalized_vocal == "none":
        normalized_vocal = "none"
        instrumental = True
    subject = _subject(normalized_vocal, normalized_act, instrumental)
    if artist:
        subject += f"; artist identity or brief: {artist}"
    return {
        "vocal": normalized_vocal,
        "act": normalized_act,
        "subject": subject,
        "instrumental": instrumental,
        "needsConfirmation": normalized_vocal == "unknown",
    }


def _validated_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("casting spec: 객체여야 합니다")
    vocal = spec.get("vocal")
    act = spec.get("act")
    instrumental = spec.get("instrumental")
    subject = spec.get("subject")
    confirmation = spec.get("needsConfirmation")
    if vocal not in VOCALS or act not in ACTS:
        raise ValueError("casting spec: vocal 또는 act 값이 올바르지 않습니다")
    if not isinstance(instrumental, bool) or not isinstance(subject, str) or not subject.strip() or not isinstance(confirmation, bool):
        raise ValueError("casting spec: subject/instrumental/needsConfirmation 형식이 올바르지 않습니다")
    if vocal == "none" and not instrumental:
        raise ValueError("casting spec: vocal=none은 instrumental=True여야 합니다")
    if instrumental and vocal in KNOWN_VOCALS:
        raise ValueError("casting spec: instrumental과 보컬 성별이 충돌합니다")
    return spec


def _validated_manifest(manifest: dict, required_assets=ASSET_KEYS):
    if not isinstance(manifest, dict):
        raise ValueError("asset manifest: 객체여야 합니다")
    if not isinstance(required_assets, (tuple, list)) or any(not isinstance(name, str) or not name for name in required_assets):
        raise ValueError("required_assets: 비어 있지 않은 역할 이름 목록이어야 합니다")
    for name in required_assets:
        value = manifest.get(name)
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError(f"asset manifest: {name} 경로가 필요합니다")
    casting = manifest.get("casting")
    if casting is None:
        return None
    if not isinstance(casting, dict):
        raise ValueError("asset manifest.casting: 객체여야 합니다")
    vocal = _vocal(casting.get("vocal"), allow_none=False)
    act = _act(casting.get("act"))
    reviewed = casting.get("reviewed")
    if not isinstance(reviewed, bool):
        raise ValueError("asset manifest.casting.reviewed: bool이어야 합니다")
    if "artistId" in casting and (not isinstance(casting["artistId"], str) or not casting["artistId"].strip()):
        raise ValueError("asset manifest.casting.artistId: 비어 있지 않은 문자열이어야 합니다")
    if "evidence" in casting and not isinstance(casting["evidence"], (str, list, dict)):
        raise ValueError("asset manifest.casting.evidence: 문자열, 목록 또는 객체여야 합니다")
    return {"vocal": vocal, "act": act, "reviewed": reviewed}


def check_asset_casting(spec: dict, manifest: dict, allow_demo=False, required_assets=None) -> dict:
    """Validate generated assets against an explicit vocal casting decision."""
    spec = _validated_spec(spec)
    if not isinstance(allow_demo, bool):
        raise ValueError("allow_demo: bool이어야 합니다")
    casting = _validated_manifest(manifest, ASSET_KEYS if required_assets is None else required_assets)
    if allow_demo:
        return {"status": "demo-only", "vocal": spec["vocal"], "act": spec["act"]}

    if spec["act"] == "artwork":
        if casting is None or casting["act"] != "artwork" or casting["reviewed"] is not True:
            raise ValueError("artwork 선택에는 reviewed=True인 casting.act=artwork 메타데이터가 필요합니다")
        return {"status": "matched", "vocal": spec["vocal"], "act": spec["act"]}

    if casting is not None and spec["act"] != "auto" and casting["act"] != spec["act"]:
        raise ValueError("생성 자산의 편성 형태와 요청 캐스팅이 다릅니다")

    if spec["vocal"] in KNOWN_VOCALS:
        if casting is None:
            raise ValueError("여성/남성/혼성 보컬 이미지는 검수된 casting 메타데이터가 필요합니다")
        if spec["act"] == "auto" and casting["act"] == "artwork":
            raise ValueError("보컬이 알려진 요청에는 가수 없는 artwork 자산을 사용할 수 없습니다")
        if casting["vocal"] != spec["vocal"]:
            raise ValueError("생성 자산의 보컬 성별과 요청 캐스팅이 다릅니다")
        if casting["reviewed"] is not True:
            raise ValueError("생성 자산의 보컬 캐스팅을 검수해야 합니다")
        return {"status": "matched", "vocal": spec["vocal"], "act": spec["act"]}

    if spec["vocal"] == "none":
        if casting is None:
            return {"status": "unconfirmed", "vocal": "none", "act": spec["act"]}
        if casting["vocal"] != "none" or casting["reviewed"] is not True:
            raise ValueError("연주곡 자산은 reviewed=True 및 casting.vocal=none이어야 합니다")
        return {"status": "matched", "vocal": "none", "act": spec["act"]}

    if spec["act"] != "auto" and (casting is None or casting["reviewed"] is not True):
        return {"status": "unconfirmed", "vocal": "unknown", "act": spec["act"]}

    # An unspecified voice must not become a gender claim merely because old assets lack metadata.
    return {"status": "unconfirmed", "vocal": "unknown", "act": spec["act"]}
