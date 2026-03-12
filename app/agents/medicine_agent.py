"""
의약품 정보 안내 Agent 정의
"""

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from app.agents.tools import analyze_medicine_caution, analyze_medicine, search_pharmacy
from app.agents.medicine_prompt import MEDICINE_AGENT_SYSTEM_PROMPT
from langchain.agents.structured_output import ToolStrategy
from app.models.chat import ChatResponse


def create_medicine_agent(checkpointer=None):
    model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    )

    tools = [
        analyze_medicine,
        analyze_medicine_caution,
        search_pharmacy,
    ]
    
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=MEDICINE_AGENT_SYSTEM_PROMPT,
        response_format=ToolStrategy(ChatResponse),
        checkpointer=checkpointer,
    )

    return agent
