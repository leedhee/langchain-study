import os

from opik import Opik
from app.core.config import settings


DATASET_NAME = "leedhee-dataset"


DATASET_ITEMS = [
    {
        "input": "타이레놀 효능 알려줘",
        "expected_output": (
            "타이레놀의 효능과 사용 목적을 설명하고, 제품별 성분과 용법 차이가 있을 수 있음을 안내해야 합니다."
        ),
    },
    {
        "input": "타이레놀 주의사항 알려줘",
        "expected_output": (
        "타이레놀 복용 시 확인해야 할 주요 주의사항을 설명하고, 제품 성분과 용법에 따라 차이가 있을 수 있음을 안내해야 합니다."
        ),
    },
    {
        "input": "어른 기준 타이레놀 하루 몇알까지 복용해도 돼?",
        "expected_output": (
            "타이레놀 복용량은 제품 성분과 함량에 따라 달라질 수 있으므로, 제품명과 용량 확인이 필요하다고 안내해야 합니다."
        ),
    },
    {
        "input": "위염 증상 알려줘",
        "expected_output": (
            "위염에서 나타날 수 있는 대표 증상을 간단히 설명하고, 필요한 경우 진료를 권할 수 있어야 합니다."
        ),
    },
    {
        "input": "속이 쓰리고 아픈데 위염 증상일 수도 있어?",
        "expected_output": (
            "속쓰림과 복통이 위염에서 나타날 수 있는 증상임을 설명하고, 위염의 기본 설명이나 주요 원인을 간단히 안내할 수 있어야 합니다. "
            "다만 증상을 단정적으로 진단하지 말고, 지속되거나 심해지면 진료 상담을 권장해야 합니다."
        ),
    },
    {
        "input": "강동구에 있는 내과 알려줘",
        "expected_output": (
            "강동구 지역의 내과 병원 검색 결과를 안내해야 하며, 병원명 또는 주소 등 식별 가능한 정보가 포함되어야 합니다."
        ),
    },
    {
        "input": "위염 증상 알려주고, 이 증상일 때 타이레놀 먹어도 돼?",
        "expected_output": (
            "위염 증상과 타이레놀 복용 관련 주의사항을 함께 설명해야 하며, 두 질문에 모두 답해야 합니다."
        ),
    },
    {
        "input": "위염일 때 어느 진료과로 가야돼? 구로구에 있는 곳으로 알려줘",
        "expected_output": (
            "위염 증상으로 고려할 수 있는 진료과를 안내하고, 구로구 지역 병원 검색 결과를 함께 제공해야 합니다."
        ),
    },
    {
        "input": "강동구에 있는 내과 알려주고, 타이레놀 효능도 알려줘",
        "expected_output": (
            "강동구 내과 병원 정보와 타이레놀 효능 설명을 함께 제공해야 하며, 두 요청을 빠뜨리지 않아야 합니다."
        ),
    },
    {
        "input": "위염 증상 알려주고, 강동구에 있는 내과도 알려줘",
        "expected_output": (
            "위염 관련 증상을 설명하고, 강동구 지역의 내과 병원 검색 결과를 함께 제공해야 하며, 두 요청에 모두 답해야 합니다."
        ),
    }
]


def configure_opik() -> None:
    opik_settings = settings.OPIK
    if not opik_settings:
        return

    if opik_settings.URL_OVERRIDE:
        os.environ["OPIK_URL_OVERRIDE"] = opik_settings.URL_OVERRIDE
    if opik_settings.API_KEY:
        os.environ["OPIK_API_KEY"] = opik_settings.API_KEY
    if opik_settings.WORKSPACE:
        os.environ["OPIK_WORKSPACE"] = opik_settings.WORKSPACE


def main() -> None:
    configure_opik()
    client = Opik()
    dataset = client.get_or_create_dataset(name=DATASET_NAME)

    # Opik deduplicates identical items, so re-running this script is safe.
    dataset.insert(DATASET_ITEMS)
    print(f"Inserted {len(DATASET_ITEMS)} items into dataset '{DATASET_NAME}'.")


if __name__ == "__main__":
    main()
