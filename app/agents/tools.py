"""
의약품 정보 안내 Agent가 사용할 도구 정의
1. 약 정보 검색 tool : analyze_medicine
2. 병용금기 정보 검색 tool : analyze_medicine_caution
3. 약국 검색 tool : search_pharmacy
"""

import os
import httpx
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
SERVICE_KEY = os.getenv("PUBLIC_DATA_API_KEY")


# 1. 약 효능 검색 tool
def analyze_medicine(medicine_name: str) -> str:
    """약 이름으로 의약품의 효능, 복용법, 일반적인 주의사항을 검색합니다.
    약의 기본 정보나 복용 안내가 필요할 때 사용합니다.
    병용금기, 함께 복용하면 안 되는 약, 병용 가능 여부를 묻는 경우에는 사용하지 않습니다."""

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

    item_name = item.findtext("itemName", default="")
    efcy = item.findtext("efcyQesitm", default="효능 정보 없음")
    use_method = item.findtext("useMethodQesitm", default="복용법 정보 없음")
    atpn = item.findtext("atpnQesitm", default="주의사항 정보 없음")

    return (
        f"약 이름: {item_name}\n"
        f"효능: {efcy}\n\n"
        f"복용법: {use_method}\n\n"
        f"주의사항: {atpn}"
    )

# 2. 병용금기 정보 검색 tool
def analyze_medicine_caution(medicine_name: str) -> str:
    """약 이름으로 병용금기 정보를 검색합니다.
    다른 약과 함께 복용하면 안 되는 약, 같이 먹으면 안 되는 약, 병용 주의 약을 확인할 때 사용합니다.
    약의 효능, 복용법, 일반적인 주의사항을 묻는 경우에는 사용하지 않습니다."""

    def safe_str(value) -> str:
        return value.strip() if isinstance(value, str) else ""

    url = "https://apis.data.go.kr/1471000/DURPrdlstInfoService03/getUsjntTabooInfoList03"
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": "5",
        "type": "json",
        "itemName": medicine_name,
    }

    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        return f"병용금기 정보 조회 중 오류가 발생했습니다: {e}"
    except ValueError:
        return "병용금기 응답을 JSON으로 해석하지 못했습니다."

    header = data.get("header", {})
    result_code = header.get("resultCode", "")
    result_msg = header.get("resultMsg", "")

    if result_code and result_code != "00":
        return f"병용금기 정보 조회에 실패했습니다. 결과코드: {result_code}, 메시지: {result_msg}"

    body = data.get("body", {})
    items = body.get("items", [])

    if isinstance(items, dict):
        items = items.get("item", [])
    elif not isinstance(items, list):
        items = []

    if isinstance(items, dict):
        items = [items]

    if not items:
        return f"'{medicine_name}'에 대한 병용금기 정보가 없습니다."

    results = []
    seen = set()

    for item in items:
        item_name = safe_str(item.get("ITEM_NAME"))                   # 조회된 약 이름
        entp_name = safe_str(item.get("ENTP_NAME"))                   # 업체명
        type_name = safe_str(item.get("TYPE_NAME"))                   # 주의 유형명
        mixture_item_name = safe_str(item.get("MIXTURE_ITEM_NAME"))   # 함께 복용 주의대상 약 이름
        mixture_entp_name = safe_str(item.get("MIXTURE_ENTP_NAME"))   # 함께 복용 주의대상 업체명
        prohbt_content = safe_str(item.get("PROHBT_CONTENT"))         # 병용금기 내용
        remark = safe_str(item.get("REMARK"))                         # 추가 설명
        notification_date = safe_str(item.get("NOTIFICATION_DATE"))   # 고시일자

        lines = [f"약 이름: {item_name or medicine_name}"]

        if entp_name:
            lines.append(f"업체명: {entp_name}")

        if type_name:
            lines.append(f"주의 유형: {type_name}")

        if mixture_item_name:
            if mixture_entp_name:
                lines.append(f"함께 복용 주의 약: {mixture_item_name} ({mixture_entp_name})")
            else:
                lines.append(f"함께 복용 주의 약: {mixture_item_name}")

        if prohbt_content:
            lines.append(f"병용금기 내용: {prohbt_content}")

        if remark:
            lines.append(f"추가 설명: {remark}")

        if notification_date:
            lines.append(f"고시일자: {notification_date}")

        result_text = "\n".join(lines)

        if result_text not in seen:
            seen.add(result_text)
            results.append(result_text)

    if not results:
        return f"'{medicine_name}'에 대한 병용금기 정보는 조회되었지만 표시할 상세 정보가 없습니다."

    return "\n\n".join(results[:5])


# 시도 코드 매핑
SIDO_CODE_MAP = {
    "서울": "110000",
    "서울시": "110000",
    "서울특별시": "110000",
}


# 시군구 코드 매핑
# key는 "시도명 시군구명" 형태로 관리
SIGUNGU_CODE_MAP = {
    "서울특별시 구로구": "110005",
    # 필요한 지역 추가
    # "서울특별시 강남구": "110023",
}


def _normalize_text(text: str) -> str:
    return text.strip().replace(" ", "")


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


# 3. 약국 검색 tool
def search_pharmacy(
    pharmacy_name: Optional[str] = None,
    area: Optional[str] = None,
    emdong_name: Optional[str] = None,
) -> str:
    """약국명 또는 지역 정보를 기준으로 약국 정보를 검색합니다.
    - 특정 약국명을 찾을 때는 pharmacy_name을 사용합니다.
    - 특정 지역의 약국을 찾을 때는 area를 사용합니다.
    - 동 단위까지 좁히고 싶을 때는 emdong_name을 사용합니다.
    같은 질문에서 반복 호출하지 않습니다.
    """

    url = "http://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList"

    if not pharmacy_name and not area and not emdong_name:
        return "검색어가 없습니다. 약국명 또는 지역 정보를 입력해주세요."

    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": "30",
    }

    if pharmacy_name:
        params["yadmNm"] = pharmacy_name

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

    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        return f"약국 검색 중 오류가 발생했습니다: {e}"

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return "약국 검색 응답을 해석하지 못했습니다."

    items = root.findall(".//item")

    if not items:
        conditions = []
        if area:
            conditions.append(f"지역: {area}")
        if emdong_name:
            conditions.append(f"동: {emdong_name}")
        if pharmacy_name:
            conditions.append(f"약국명: {pharmacy_name}")

        condition_text = ", ".join(conditions) if conditions else "입력 조건 없음"
        return f"조건에 맞는 약국 검색 결과가 없습니다. ({condition_text})"

    results = []
    seen = set()

    normalized_area = _normalize_text(area) if area else None
    normalized_emdong = _normalize_text(emdong_name) if emdong_name else None

    for item in items:
        name = (item.findtext("yadmNm", default="") or "").strip()
        addr = (item.findtext("addr", default="") or "").strip()
        tel = (item.findtext("telno", default="") or "").strip()
        estb_dd = (item.findtext("estbDd", default="") or "").strip()

        normalized_name = _normalize_text(name)
        normalized_addr = _normalize_text(addr)

        if pharmacy_name and pharmacy_name not in name:
            continue

        if normalized_area and normalized_area not in normalized_addr and normalized_area not in normalized_name:
            continue

        if normalized_emdong and normalized_emdong not in normalized_addr:
            continue

        result_text = (
            f"약국명: {name}\n"
            f"주소: {addr}\n"
            f"전화: {tel}\n"
            f"개설일자: {estb_dd}"
        )

        if result_text not in seen:
            seen.add(result_text)
            results.append(result_text)

    if not results:
        conditions = []
        if area:
            conditions.append(f"지역: {area}")
        if emdong_name:
            conditions.append(f"동: {emdong_name}")
        if pharmacy_name:
            conditions.append(f"약국명: {pharmacy_name}")

        condition_text = ", ".join(conditions) if conditions else "입력 조건 없음"
        return f"조건에 맞는 약국 검색 결과가 없습니다. ({condition_text})"

    return "\n\n".join(results[:5])