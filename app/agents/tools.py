"""
의료용 Agent가 사용할 도구 정의
1. 증상(질병) 정보 검색 tool : analyze_symptom (Elasticsearch Retriever 사용)
2. 약 정보 검색 tool : analyze_medicine
3. 병원 검색 tool : search_hospital
"""

import os

from dotenv import load_dotenv
from langchain.tools import tool
from app.domain.hospital_search_resolver import _normalize_text, _resolve_sigungu_code, _resolve_subject_code
from app.services.elasticsearch_service import create_es_retriever
from app.services.public_data_service import search_hospital_items, search_medicine_items

load_dotenv()

CONTENT_FIELD = os.getenv("CONTENT_FIELD", "content")
TOP_K = int(os.getenv("TOP_K", "3"))

# -----------------------------
# 1. 증상(질병) 정보 검색 tool
# -----------------------------
@tool
def analyze_symptom(symptom_name: str) -> str:
    """Elasticsearch에서 증상/질병 관련 정보를 검색합니다.

    Args:
        symptom_name: 사용자가 입력한 증상 또는 질병명 키워드.

    Returns:
        검색 결과 요약 문자열. 결과가 없거나 오류 시 안내 문구를 반환합니다.
    """
    try:
        medical_retriever = create_es_retriever()
        docs = medical_retriever.invoke(symptom_name)
    except Exception as e:
        return f"증상 정보 검색 중 Elasticsearch 오류가 발생했습니다: {e}"

    if not docs:
        return f"'{symptom_name}'와(과) 관련된 증상 정보를 찾지 못했습니다."

    results = []
    for doc in docs[:TOP_K]:
        content = (doc.page_content or "").strip()
        metadata = doc.metadata or {}

        lines = []
        title = metadata.get("title")
        if title:
            lines.append(f"제목: {title}")
        if content:
            lines.append(f"내용: {content}")

        result_text = "\n".join(lines).strip()
        if result_text:
            results.append(result_text)

    if not results:
        return f"'{symptom_name}'와(과) 관련된 증상 정보를 찾았지만 표시할 내용이 없습니다."

    return "\n\n".join(results)



# -----------------------------
# 2. 약 효능 검색 tool
# -----------------------------
@tool
def analyze_medicine(medicine_name: str) -> str:
    """약 이름으로 의약품 정보를 검색합니다.

    Args:
        medicine_name: 조회할 의약품 이름.

    Returns:
        약 이름, 효능, 복용법, 주의사항을 포함한 문자열.
    """
    try:
        items = search_medicine_items(medicine_name)
    except RuntimeError as e:
        return str(e)

    if not items:
        return f"'{medicine_name}' 의약품 정보를 찾지 못했습니다."

    item = items[0]

    return (
        f"약 이름: {item['item_name']}\n"
        f"효능: {item['efcy']}\n\n"
        f"복용법: {item['use_method']}\n\n"
        f"주의사항: {item['atpn']}"
    )


# -----------------------------
# 3. 병원 검색 tool
# -----------------------------
@tool
def search_hospital(
    hospital_name: str | None = None,
    area: str | None = None,
    emdong_name: str | None = None,
    subject_name: str | None = None,
) -> str:
    """병원명/지역/진료과목 조건으로 병원을 검색합니다.

    Args:
        hospital_name: 검색할 병원명(부분 일치).
        area: 시군구 단위 지역명(예: 강남구, 구로구).
        emdong_name: 동 이름(예: 역삼동).
        subject_name: 진료과목명(예: 내과, 정형외과).

    Returns:
        조건에 맞는 병원 목록 문자열. 결과가 없거나 오류 시 안내 문구를 반환합니다.
    """
    if not hospital_name and not area and not emdong_name and not subject_name:
        return "검색어가 없습니다. 병원명 또는 지역 정보를 입력해주세요."
    sido_cd = None
    sggu_cd = None

    if area:
        sido_cd, sggu_cd = _resolve_sigungu_code(area)

        if not sggu_cd:
            return (
                f"'{area}'에 해당하는 지역 코드를 찾지 못했습니다. "
                "시군구 단위로 입력해주세요. (예: 구로구, 강남구)"
            )

        
    if subject_name:
        resolved_subject_code = _resolve_subject_code(subject_name)
        if not resolved_subject_code:
            return (
                f"'{subject_name}'에 해당하는 진료과목 코드를 찾지 못했습니다. "
                "예: 내과, 정형외과, 이비인후과"
            )
    else:
        resolved_subject_code = None

    try:
        items = search_hospital_items(
            hospital_name=hospital_name,
            sido_cd=sido_cd,
            sggu_cd=sggu_cd,
            emdong_name=emdong_name,
            subject_code=resolved_subject_code,
        )
    except RuntimeError as e:
        return str(e)

    if not items:
        conditions = []
        if area:
            conditions.append(f"지역: {area}")
        if emdong_name:
            conditions.append(f"동: {emdong_name}")
        if hospital_name:
            conditions.append(f"병원명: {hospital_name}")
        if subject_name:
            conditions.append(f"진료과목: {subject_name}")

        condition_text = ", ".join(conditions) if conditions else "입력 조건 없음"
        return f"조건에 맞는 병원 검색 결과가 없습니다. ({condition_text})"

    results: list[str] = []
    seen: set[str] = set()

    normalized_area = _normalize_text(area) if area else None
    normalized_emdong = _normalize_text(emdong_name) if emdong_name else None

    for item in items:
        name = item["name"]
        addr = item["addr"]
        tel = item["tel"]
        hosp_url = item["hosp_url"]
        cl_cd_nm = item["cl_cd_nm"]
        sggu_nm = item["sggu_nm"]
        estb_dd = item["estb_dd"]

        normalized_name = _normalize_text(name)
        normalized_addr = _normalize_text(addr)

        if hospital_name and _normalize_text(hospital_name) not in normalized_name:
            continue

        if normalized_area and normalized_area not in normalized_addr and normalized_area not in normalized_name:
            continue

        if normalized_emdong and normalized_emdong not in normalized_addr:
            continue

        lines = [f"병원명: {name}"]

        if cl_cd_nm:
            lines.append(f"종별: {cl_cd_nm}")
        if addr:
            lines.append(f"주소: {addr}")
        if sggu_nm:
            lines.append(f"지역: {sggu_nm}")
        if tel:
            lines.append(f"전화: {tel}")
        if hosp_url:
            lines.append(f"홈페이지: {hosp_url}")
        if estb_dd:
            lines.append(f"개설일자: {estb_dd}")

        result_text = "\n".join(lines)

        if result_text not in seen:
            seen.add(result_text)
            results.append(result_text)

    if not results:
        conditions = []
        if area:
            conditions.append(f"지역: {area}")
        if emdong_name:
            conditions.append(f"동: {emdong_name}")
        if hospital_name:
            conditions.append(f"병원명: {hospital_name}")
        if subject_name:
            conditions.append(f"진료과목: {subject_name}")

        condition_text = ", ".join(conditions) if conditions else "입력 조건 없음"
        return f"조건에 맞는 병원 검색 결과가 없습니다. ({condition_text})"

    return "\n\n".join(results[:5])
