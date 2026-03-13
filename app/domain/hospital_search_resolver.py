from typing import Optional
from app.domain.hospital_codes import SIDO_CODE_MAP, SIGUNGU_CODE_MAP, SUBJECT_CODE_MAP

def _normalize_text(text: str) -> str:
    return text.strip().replace(" ", "") if text else ""

def _resolve_sido_code(area: str) -> Optional[str]:
    if not area:
        return None

    normalized_area = _normalize_text(area)

    for name, code in SIDO_CODE_MAP.items():
        normalized_name = _normalize_text(name)
        if normalized_name in normalized_area or normalized_area in normalized_name:
            return code

    return None


def _resolve_sigungu_code(area: str) -> tuple[Optional[str], Optional[str]]:
    """지역 문자열에서 시도코드와 시군구코드를 찾습니다.

    예:
    - '구로구' -> ('110000', '110005')
    - '서울 구로구' -> ('110000', '110005')
    """
    if not area:
        return None, None

    normalized_area = _normalize_text(area)

    # 1) 정확 매칭
    for full_name, sggu_code in SIGUNGU_CODE_MAP.items():
        if _normalize_text(full_name) == normalized_area:
            sido_code = _resolve_sido_code(full_name)
            return sido_code, sggu_code

    # 2) 부분 매칭
    for full_name, sggu_code in SIGUNGU_CODE_MAP.items():
        normalized_full_name = _normalize_text(full_name)
        if normalized_area in normalized_full_name or normalized_full_name in normalized_area:
            sido_code = _resolve_sido_code(full_name)
            return sido_code, sggu_code

    return None, None


def _resolve_subject_code(subject_name: Optional[str]) -> Optional[str]:
    """진료과목명을 API용 진료과목 코드로 변환합니다."""
    if not subject_name:
        return None

    normalized_subject = _normalize_text(subject_name)

    # 1) 정확 매칭
    for name, code in SUBJECT_CODE_MAP.items():
        if _normalize_text(name) == normalized_subject:
            return code

    # 2) 부분 매칭
    for name, code in SUBJECT_CODE_MAP.items():
        normalized_name = _normalize_text(name)
        if normalized_subject in normalized_name or normalized_name in normalized_subject:
            return code

    return None