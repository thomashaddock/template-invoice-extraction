from typing import Any, List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai.tasks.task_output import TaskOutput

from invoice_extraction.models import InvoiceRecord


def validate_invoice_record(result: TaskOutput) -> tuple[bool, Any]:
    data = result.pydantic
    if data is None:
        return (False, "Failed to parse structured output — retry extraction")
    if not data.invoice_number:
        return (False, "Missing invoice_number — retry extraction")
    if not data.vendor_name:
        return (False, "Missing vendor_name — retry extraction")
    if data.total_amount is None:
        return (False, "Missing total_amount — retry extraction")
    if not data.line_items:
        return (False, "Empty line_items — retry extraction")
    return (True, result.raw)


@CrewBase
class ExtractionCrew:
    """Single-agent crew for structured invoice data extraction."""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def invoice_extractor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["invoice_extractor_agent"],  # type: ignore[index]
        )

    @task
    def extract_invoice_task(self) -> Task:
        return Task(
            config=self.tasks_config["extract_invoice_task"],  # type: ignore[index]
            output_pydantic=InvoiceRecord,
            guardrail=validate_invoice_record,
            guardrail_max_retries=2,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )
