import os

from opik import Opik
from app.core.config import settings


DATASET_NAME = "leedhee-dataset"


DATASET_ITEMS = [
    {
        "input": "타이레놀 효능 알려줘",
        "expected_output": (
            "타이레놀은 해열과 진통에 사용될 수 있으며, 제품별 효능과 용법은 "
            "설명서와 안내사항을 함께 확인해야 합니다."
        ),
    },
    {
        "input": "어른 기준 타이레놀 하루 몇알까지 복용해도 돼?",
        "expected_output": (
            "타이레놀의 하루 복용 가능량은 제품의 성분과 함량에 따라 달라질 수 있으므로, "
            "제품명과 용량을 확인한 뒤 안내된 복용법을 따라야 합니다."
        ),
    },
    {
        "input": "위염일 때 타이레놀 먹어도 돼?",
        "expected_output": (
            "위염이 있을 때 타이레놀 복용 가능 여부는 제품 성분과 개인 상태에 따라 달라질 수 있으므로, "
            "설명서의 주의사항을 확인하고 필요하면 의사나 약사와 상담하는 것이 좋습니다."
        ),
    },
    {
        "input": "위염일 때 어느 진료과로 가야돼? 구로구에 있는 곳으로 알려줘",
        "expected_output": (
            "위염 증상으로 진료가 필요하면 보통 내과를 고려할 수 있으며, "
            "구로구 지역의 내과 병원 검색 결과를 안내드립니다."
        ),
    },
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
