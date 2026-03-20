"""
의약품 정보 안내 Agent 정의
"""

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from app.agents.tools import analyze_symptom, analyze_medicine, search_hospital
from app.agents.medical_prompt import MEDICAL_AGENT_SYSTEM_PROMPT
from langchain.agents.structured_output import ToolStrategy
from app.models.agent_response import AgentResponse


def create_medical_agent(checkpointer=None):
    model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    )

    tools = [
        analyze_symptom,
        analyze_medicine,
        search_hospital,
    ]

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=MEDICAL_AGENT_SYSTEM_PROMPT,
        response_format=ToolStrategy(AgentResponse),
        checkpointer=checkpointer,
    )

    return agent
