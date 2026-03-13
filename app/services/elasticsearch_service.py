import os
from typing import Dict

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from langchain_elasticsearch import ElasticsearchRetriever

load_dotenv()

ES_URL = os.getenv("ES_URL")
ES_USER = os.getenv("ES_USER")
ES_PASSWORD = os.getenv("ES_PASSWORD")
INDEX_NAME = os.getenv("INDEX_NAME")
CONTENT_FIELD = os.getenv("CONTENT_FIELD", "content")


def create_es_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=ES_URL,
        basic_auth=(ES_USER, ES_PASSWORD),
    )


def bm25_query(search_query: str) -> Dict:
    return {
        "query": {
            "match": {
                CONTENT_FIELD: search_query
            }
        }
    }


def create_es_retriever() -> ElasticsearchRetriever:
    es_client = create_es_client()

    return ElasticsearchRetriever(
        client=es_client,
        index_name=INDEX_NAME,
        body_func=bm25_query,
        content_field=CONTENT_FIELD,
    )
