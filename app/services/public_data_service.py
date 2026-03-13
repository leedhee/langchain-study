import os
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.getenv("PUBLIC_DATA_API_KEY")
MEDICINE_API_URL = "http://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
HOSPITAL_API_URL = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"


def _safe_text(value: Optional[str], default: str = "") -> str:
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def search_medicine_items(medicine_name: str, num_of_rows: int = 3) -> list[dict[str, str]]:
    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": str(num_of_rows),
        "itemName": medicine_name,
    }

    try:
        response = httpx.get(MEDICINE_API_URL, params=params, timeout=30.0)
        response.raise_for_status()
    except httpx.ReadTimeout as exc:
        raise RuntimeError(
            "약 정보 조회 시간이 초과되었습니다. 공공데이터 서비스 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요."
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else None
        if status_code == 502:
            raise RuntimeError("약 정보 조회 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요.") from exc
        raise RuntimeError(f"약 정보 조회 중 오류가 발생했습니다. (상태코드: {status_code})") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"약 정보 조회 중 오류가 발생했습니다: {exc}") from exc

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise RuntimeError("약 정보 응답을 해석하지 못했습니다.") from exc

    items = []
    for item in root.findall(".//item"):
        items.append(
            {
                "item_name": _safe_text(item.findtext("itemName"), "약 이름 정보 없음"),
                "efcy": _safe_text(item.findtext("efcyQesitm"), "효능 정보 없음"),
                "use_method": _safe_text(item.findtext("useMethodQesitm"), "복용법 정보 없음"),
                "atpn": _safe_text(item.findtext("atpnQesitm"), "주의사항 정보 없음"),
            }
        )

    return items


def search_hospital_items(
    hospital_name: Optional[str] = None,
    sido_cd: Optional[str] = None,
    sggu_cd: Optional[str] = None,
    emdong_name: Optional[str] = None,
    subject_code: Optional[str] = None,
    num_of_rows: int = 30,
) -> list[dict[str, str]]:
    params = {
        "ServiceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": str(num_of_rows),
    }

    if hospital_name:
        params["yadmNm"] = hospital_name
    if sido_cd:
        params["sidoCd"] = sido_cd
    if sggu_cd:
        params["sgguCd"] = sggu_cd
    if emdong_name:
        params["emdongNm"] = emdong_name
    if subject_code:
        params["dgsbjtCd"] = subject_code

    try:
        response = httpx.get(HOSPITAL_API_URL, params=params, timeout=20.0)
        response.raise_for_status()
    except httpx.ReadTimeout as exc:
        raise RuntimeError("병원 검색 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else None
        raise RuntimeError(f"병원 검색 중 오류가 발생했습니다. (상태코드: {status_code})") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"병원 검색 중 오류가 발생했습니다: {exc}") from exc

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise RuntimeError("병원 검색 응답을 해석하지 못했습니다.") from exc

    items = []
    for item in root.findall(".//item"):
        items.append(
            {
                "name": _safe_text(item.findtext("yadmNm")),
                "addr": _safe_text(item.findtext("addr")),
                "tel": _safe_text(item.findtext("telno")),
                "hosp_url": _safe_text(item.findtext("hospUrl")),
                "cl_cd_nm": _safe_text(item.findtext("clCdNm")),
                "sggu_nm": _safe_text(item.findtext("sgguCdNm")),
                "estb_dd": _safe_text(item.findtext("estbDd")),
            }
        )

    return items
