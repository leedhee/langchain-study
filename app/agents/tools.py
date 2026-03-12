"""
의료용 Agent가 사용할 도구 정의
1. 증상(질병) 정보 검색 tool : analyze_symptom
2. 약 정보 검색 tool : analyze_medicine
3. 병원 검색 tool : search_hospital
"""

import os
import httpx
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
SERVICE_KEY = os.getenv("PUBLIC_DATA_API_KEY")


# -----------------------------
# 공통 유틸
# -----------------------------
def _normalize_text(text: str) -> str:
    return text.strip().replace(" ", "") if text else ""


def _safe_text(value: Optional[str], default: str = "") -> str:
    if value is None:
        return default
    value = value.strip()
    return value if value else default


# -----------------------------
# 지역 코드 매핑
# -----------------------------
SIDO_CODE_MAP = {
    "서울": "110000",
    "서울시": "110000",
    "서울특별시": "110000",
    # 필요 시 추가
    # "부산": "210000",
    # "대구": "220000",
}

SIGUNGU_CODE_MAP = {
    "서울특별시 구로구": "110005",
    # 필요 시 추가
    # "서울특별시 강남구": "110023",
}


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


# -----------------------------
# 진료과목 코드 매핑
# -----------------------------
SUBJECT_CODE_MAP = {
    "내과": "01",
    "신경과": "02",
    "정신건강의학과": "03",
    "외과": "04",
    "정형외과": "05",
    "신경외과": "06",
    "흉부외과": "07",
    "성형외과": "08",
    "마취통증의학과": "09",
    "산부인과": "10",
    "소아청소년과": "11",
    "안과": "12",
    "이비인후과": "13",
    "피부과": "14",
    "비뇨의학과": "15",
    "영상의학과": "16",
    "방사선종양학과": "17",
    "병리과": "18",
    "진단검사의학과": "19",
    "재활의학과": "20",
    "핵의학과": "21",
    "가정의학과": "23",
    "응급의학과": "24",
    "치과": "49",
    "한방내과": "80",
    "한방부인과": "81",
    "한방소아과": "82",
    "한방안·이비인후·피부과": "83",
    "한방신경정신과": "84",
    "침구과": "85",
    "한방재활의학과": "86",
    "사상체질과": "87",
}


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


# -----------------------------
# 1. 증상(질병) 정보 검색 tool
# -----------------------------
def analyze_symptom(symptom_name: str) -> str:
    """증상 또는 질병명 키워드로 질병 정보를 검색합니다.
    사용자가 증상, 질병명, 관련 상병 정보를 물을 때 사용합니다.
    병원 검색이나 약 효능 검색 질문에는 사용하지 않습니다.
    """

    url = "https://apis.data.go.kr/B551182/diseaseInfoService1/getDissNameCodeList1"
    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": "5",
        "sickType": "1",          # 상병 구분
        "medTp": "1",             # 1: 의과, 2: 한방
        "diseaseType": "SICK_NM", # 질병명으로 검색
        "searchText": symptom_name,
    }

    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
    except httpx.ReadTimeout:
        return "증상 정보 조회 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else None
        return f"증상 정보 조회 중 오류가 발생했습니다. (상태코드: {status_code})"
    except httpx.HTTPError as e:
        return f"증상 정보 조회 중 오류가 발생했습니다: {e}"

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return "증상 정보 응답을 해석하지 못했습니다."

    items = root.findall(".//item")

    if not items:
        return f"'{symptom_name}'와(과) 관련된 질병 정보를 찾지 못했습니다."

    results = []
    seen = set()

    for item in items:
        sick_cd = _safe_text(item.findtext("sickCd"), "상병코드 정보 없음")
        sick_nm = _safe_text(item.findtext("sickNm"), "질병명 정보 없음")
        eng_nm = _safe_text(item.findtext("engSickNm"))
        med_tp = _safe_text(item.findtext("medTpNm"))

        lines = [
            f"질병명: {sick_nm}",
            f"상병코드: {sick_cd}",
        ]

        if eng_nm:
            lines.append(f"영문명: {eng_nm}")
        if med_tp:
            lines.append(f"구분: {med_tp}")

        result_text = "\n".join(lines)

        if result_text not in seen:
            seen.add(result_text)
            results.append(result_text)

    return "\n\n".join(results[:5])


# -----------------------------
# 2. 약 효능 검색 tool
# -----------------------------
def analyze_medicine(medicine_name: str) -> str:
    """약 이름으로 의약품의 효능, 복용법, 일반적인 주의사항을 검색합니다.
    약의 기본 정보나 복용 안내가 필요할 때 사용합니다.
    병원 검색이나 증상/질병 조회 질문에는 사용하지 않습니다.
    """

    url = "http://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": "3",
        "itemName": medicine_name,
    }

    try:
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
    except httpx.ReadTimeout:
        return "약 정보 조회 시간이 초과되었습니다. 공공데이터 서비스 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요."
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else None
        if status_code == 502:
            return "약 정보 조회 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요."
        return f"약 정보 조회 중 오류가 발생했습니다. (상태코드: {status_code})"
    except httpx.HTTPError as e:
        return f"약 정보 조회 중 오류가 발생했습니다: {e}"

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return "약 정보 응답을 해석하지 못했습니다."

    items = root.findall(".//item")

    if not items:
        return f"'{medicine_name}' 의약품 정보를 찾지 못했습니다."

    item = items[0]

    item_name = _safe_text(item.findtext("itemName"), "약 이름 정보 없음")
    efcy = _safe_text(item.findtext("efcyQesitm"), "효능 정보 없음")
    use_method = _safe_text(item.findtext("useMethodQesitm"), "복용법 정보 없음")
    atpn = _safe_text(item.findtext("atpnQesitm"), "주의사항 정보 없음")

    return (
        f"약 이름: {item_name}\n"
        f"효능: {efcy}\n\n"
        f"복용법: {use_method}\n\n"
        f"주의사항: {atpn}"
    )


# -----------------------------
# 3. 병원 검색 tool
# -----------------------------
def search_hospital(
    hospital_name: Optional[str] = None,
    area: Optional[str] = None,
    emdong_name: Optional[str] = None,
    subject_name: Optional[str] = None,
) -> str:
    """병원명 또는 지역 정보를 기준으로 병원 정보를 검색합니다.
    - 특정 병원명을 찾을 때는 hospital_name을 사용합니다.
    - 특정 지역의 병원을 찾을 때는 area를 사용합니다.
    - 동 단위까지 좁히고 싶을 때는 emdong_name을 사용합니다.
    - 진료과목 기준 검색이 필요하면 subject_name을 사용합니다.
    같은 질문에서 반복 호출하지 않습니다.
    """

    url = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"

    if not hospital_name and not area and not emdong_name and not subject_name:
        return "검색어가 없습니다. 병원명 또는 지역 정보를 입력해주세요."

    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": "30",
    }

    if hospital_name:
        params["yadmNm"] = hospital_name

    if area:
        sido_cd, sggu_cd = _resolve_sigungu_code(area)

        if not sggu_cd:
            return (
                f"'{area}'에 해당하는 지역 코드를 찾지 못했습니다. "
                "시군구 단위로 입력해주세요. (예: 구로구, 강남구)"
            )

        if sido_cd:
            params["sidoCd"] = sido_cd
        params["sgguCd"] = sggu_cd

    if emdong_name:
        params["emdongNm"] = emdong_name

    if subject_name:
        resolved_subject_code = _resolve_subject_code(subject_name)
        if not resolved_subject_code:
            return (
                f"'{subject_name}'에 해당하는 진료과목 코드를 찾지 못했습니다. "
                "예: 내과, 정형외과, 이비인후과"
            )
        params["dgsbjtCd"] = resolved_subject_code

    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
    except httpx.ReadTimeout:
        return "병원 검색 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else None
        return f"병원 검색 중 오류가 발생했습니다. (상태코드: {status_code})"
    except httpx.HTTPError as e:
        return f"병원 검색 중 오류가 발생했습니다: {e}"

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return "병원 검색 응답을 해석하지 못했습니다."

    items = root.findall(".//item")

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

    results = []
    seen = set()

    normalized_area = _normalize_text(area) if area else None
    normalized_emdong = _normalize_text(emdong_name) if emdong_name else None

    for item in items:
        name = _safe_text(item.findtext("yadmNm"))
        addr = _safe_text(item.findtext("addr"))
        tel = _safe_text(item.findtext("telno"))
        hosp_url = _safe_text(item.findtext("hospUrl"))
        cl_cd_nm = _safe_text(item.findtext("clCdNm"))
        sggu_nm = _safe_text(item.findtext("sgguCdNm"))
        estb_dd = _safe_text(item.findtext("estbDd"))

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