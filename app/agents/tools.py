"""
의료용 Agent가 사용할 도구 정의
1. 증상(질병) 정보 검색 tool : analyze_symptom (Elasticsearch Retriever 사용)
2. 약 정보 검색 tool : analyze_medicine
3. 병원 검색 tool : search_hospital
"""

import re
import os
from difflib import SequenceMatcher

from dotenv import load_dotenv
from langchain.tools import tool
from app.domain.hospital_search_resolver import _normalize_text, _resolve_sigungu_code, _resolve_subject_code
from app.services.elasticsearch_service import create_es_retriever
from app.services.public_data_service import search_hospital_items, search_medicine_items

load_dotenv()

CONTENT_FIELD = os.getenv("CONTENT_FIELD", "content")
TOP_K = int(os.getenv("TOP_K", "3"))

SEARCH_QUERY_STOPWORDS = {
    "증상",
    "문의",
}

# 질문형/서술형 표현을 검색어 생성 전에 제거하기 위한 패턴
SEARCH_QUERY_FILLER_PATTERNS = (
    r"증상(?:일|인가요)?",
    r"알려\s*주(?:세요)?",
    r"(?:일\s*수\s*)?있(?:어|어요|는데|나|나요|을까)?",
    r"같(?:아|아요|은데|나|나요)?",
    r"맞(?:아|나요|을까)?",
)

# 질환명처럼 보이는 표현을 찾기 위한 정규식
DISEASE_HINT_PATTERN = re.compile(
    r"([가-힣A-Za-z][가-힣A-Za-z0-9]*(?:"
    r"염|증|질환|증후군|"
    r"암|종양|궤양|결석|출혈|폐색|마비|손상|골절|감염|비대|"
    r"역류질환|기능저하증|항진증|저혈당|고혈압|저혈압))"
)


def _normalize_medicine_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()


def _normalize_medicine_base_name(value: str) -> str:
    normalized_value = _normalize_medicine_name(value)
    normalized_value = re.sub(r"\d.*$", "", normalized_value)
    normalized_value = re.sub(
        r"(서방정|연질캡슐|캡슐|정|시럽|현탁액|액|주|크림|겔|패치)$",
        "",
        normalized_value,
    )
    return normalized_value


def _build_medicine_correction_notice(requested_name: str, matched_name: str) -> str:
    normalized_requested = _normalize_medicine_name(requested_name)
    normalized_matched = _normalize_medicine_name(matched_name)
    normalized_matched_base = _normalize_medicine_base_name(matched_name)

    if not normalized_requested or not normalized_matched:
        return ""

    if normalized_requested in normalized_matched:
        return ""

    similarity_candidates = [
        SequenceMatcher(None, normalized_requested, normalized_matched).ratio(),
    ]

    if normalized_matched_base:
        if normalized_requested in normalized_matched_base:
            similarity_candidates.append(1.0)
        similarity_candidates.append(
            SequenceMatcher(None, normalized_requested, normalized_matched_base).ratio()
        )

    if max(similarity_candidates) < 0.6:
        return ""

    return (
        f"입력하신 '{requested_name}'은(는) 약 이름 오타 또는 표기 차이로 보여 "
        f"'{matched_name}' 기준으로 안내드립니다.\n\n"
    )


def _select_best_medicine_item(
    requested_name: str, items: list[dict[str, str]]
) -> dict[str, str] | None:
    normalized_requested = _normalize_medicine_name(requested_name)
    if not normalized_requested:
        return items[0] if items else None

    for item in items:
        if _normalize_medicine_name(item["item_name"]) == normalized_requested:
            return item

    for item in items:
        if _normalize_medicine_base_name(item["item_name"]) == normalized_requested:
            return item

    return None


def _build_medicine_disambiguation_message(
    requested_name: str, items: list[dict[str, str]]
) -> str:
    candidate_names: list[str] = []
    seen: set[str] = set()

    for item in items:
        item_name = item["item_name"]
        if item_name in seen:
            continue
        seen.add(item_name)
        candidate_names.append(item_name)

    candidates_text = "\n".join(f"- {name}" for name in candidate_names[:3])

    return (
        f"'{requested_name}'만으로는 제품을 특정하기 어렵습니다.\n"
        "동일 브랜드에 성인용, 어린이용, 함량이 다른 제품이 있어 복용량을 하나로 확정할 수 없습니다.\n\n"
        f"조회된 예시 제품:\n{candidates_text}\n\n"
        "현재 정보만으로는 확정할 수 없다고 설명하고 제품명 또는 함량 확인이 필요하다고 안내한 뒤 종료하세요."
    )


def _normalize_symptom_query(value: str) -> str:
    normalized_value = re.sub(r"[,\u3001/]+", " ", value)
    normalized_value = re.sub(r"\s+", " ", normalized_value).strip()
    return normalized_value


def _strip_query_fillers(value: str) -> str:
    normalized_value = _normalize_symptom_query(value)

    for pattern in SEARCH_QUERY_FILLER_PATTERNS:
        normalized_value = re.sub(rf"\b(?:{pattern})\b", " ", normalized_value)

    normalized_value = re.sub(r"\s+", " ", normalized_value).strip()
    return normalized_value


def _extract_disease_hint(value: str) -> str | None:
    normalized_value = _normalize_symptom_query(value)
    matches = DISEASE_HINT_PATTERN.findall(normalized_value)
    if not matches:
        return None

    # 가장 긴 후보를 우선 사용해 "식도염"보다 "역류성식도염"을 선택한다.
    return max(matches, key=len)


def _split_symptom_terms(value: str, disease_hint: str | None) -> list[str]:
    normalized_value = _strip_query_fillers(value)
    if disease_hint:
        normalized_value = normalized_value.replace(disease_hint, " ")

    raw_terms = re.split(r"\s+", normalized_value)
    filtered_terms: list[str] = []
    seen: set[str] = set()

    for term in raw_terms:
        cleaned_term = term.strip(" ?!.,")
        cleaned_term = re.sub(r"(과|와|이|가|은|는|을|를|도|만|에|에서|로|으로)$", "", cleaned_term)
        if len(cleaned_term) < 2:
            continue
        if cleaned_term in SEARCH_QUERY_STOPWORDS:
            continue
        if cleaned_term in seen:
            continue
        seen.add(cleaned_term)
        filtered_terms.append(cleaned_term)

    return filtered_terms


def _build_symptom_search_queries(symptom_name: str) -> list[str]:
    # 원문 질의를 정리한 뒤 질환 후보와 증상 키워드를 분리
    normalized_query = _normalize_symptom_query(symptom_name)
    disease_hint = _extract_disease_hint(normalized_query)
    symptom_terms = _split_symptom_terms(normalized_query, disease_hint)

    search_queries: list[str] = []
    # 질환 후보가 있으면 해당 키워드를 우선 검색어로 사용
    if disease_hint:
        search_queries.append(disease_hint)

    # 질환 후보와 증상 키워드가 모두 있으면 조합 검색어 추가
    if disease_hint and symptom_terms:
        search_queries.append(" ".join([disease_hint, *symptom_terms]))
    elif symptom_terms:
        # 질환 후보가 없으면 증상 키워드만으로 검색
        search_queries.append(" ".join(symptom_terms))

    # 위 단계에서 검색어가 만들어지지 않으면 정규화된 원문을 fallback으로 사용
    if not search_queries and normalized_query:
        search_queries.append(normalized_query)

    deduped_queries: list[str] = []
    seen_queries: set[str] = set()
    for query in search_queries:
        if query in seen_queries:
            continue
        seen_queries.add(query)
        deduped_queries.append(query)

    return deduped_queries


def _collect_symptom_results(docs) -> list[str]:
    results: list[str] = []
    for doc in docs[:TOP_K]:
        content = (doc.page_content or "").strip()
        metadata = doc.metadata or {}

        lines = []
        title = metadata.get("title")
        if title:
            lines.append(f"제목: {title}")
        if content:
            lines.append(f"내용: {content[:1200]}")

        result_text = "\n".join(lines).strip()
        if result_text:
            results.append(result_text)

    return results

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
    search_queries = _build_symptom_search_queries(symptom_name)
    last_error: Exception | None = None
    medical_retriever = create_es_retriever()

    for index, search_query in enumerate(search_queries):
        try:
            docs = medical_retriever.invoke(search_query)
        except Exception as e:
            last_error = e
            continue

        if not docs:
            continue

        results = _collect_symptom_results(docs)
        if not results:
            continue

        query_notes: list[str] = []
        normalized_original = _normalize_symptom_query(symptom_name)
        if index == 0 and search_query != normalized_original:
            query_notes.append(f"사용 검색어: {search_query}")
        elif index > 0:
            query_notes.append(f"보조 검색어: {search_query}")

        if len(search_queries) > 1:
            query_notes.append(f"원문 질의: {normalized_original}")

        prefix = ""
        if query_notes:
            prefix = "\n".join(f"- {note}" for note in query_notes) + "\n\n"

        return prefix + "\n\n".join(results) + "\n\n"

    if last_error is not None:
        return f"증상 정보 검색 중 Elasticsearch 오류가 발생했습니다: {last_error}"

    normalized_query = _normalize_symptom_query(symptom_name)
    return f"'{normalized_query}'와(과) 관련된 증상 정보를 찾지 못했습니다."


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

    item = _select_best_medicine_item(medicine_name, items)
    if item is None:
        return _build_medicine_disambiguation_message(medicine_name, items)

    correction_notice = _build_medicine_correction_notice(
        medicine_name,
        item["item_name"],
    )

    return (
        f"{correction_notice}"
        f"약 이름: {item['item_name']}\n"
        f"효능: {item['efcy']}\n\n"
        f"복용법: {item['use_method']}\n\n"
        f"주의사항: {item['atpn']}\n\n"
        "정보가 부족하면 한계를 설명하고 제품명 또는 함량 확인이 필요하다고 안내한 뒤 종료하세요."
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
