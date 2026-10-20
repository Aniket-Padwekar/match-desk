"""Match Desk orchestration on Microsoft Agent Framework (pip install agent-framework).

The five agents are Agent Framework executors wired as a workflow graph:
    StatsAnalyst -> Storyteller -> FactChecker -> Judge -> Editor -> verified recap
Each executor calls the same stage function that agents.pipeline() uses, so the workflow and the plain
pipeline give identical results. The language model is the gpt-5-mini deployment in Microsoft Foundry."""
import asyncio, threading
from typing_extensions import Never
from agent_framework import WorkflowBuilder, WorkflowContext, executor
from agents import stage_analyst, stage_storyteller, stage_factchecker, stage_judge, stage_editor

@executor(id="StatsAnalyst")
async def stats_analyst(state: dict, ctx: WorkflowContext[dict]) -> None:
    await ctx.send_message(stage_analyst(state))

@executor(id="Storyteller")
async def storyteller(state: dict, ctx: WorkflowContext[dict]) -> None:
    await ctx.send_message(stage_storyteller(state))

@executor(id="FactChecker")
async def fact_checker(state: dict, ctx: WorkflowContext[dict]) -> None:
    await ctx.send_message(stage_factchecker(state))

@executor(id="Judge")
async def judge(state: dict, ctx: WorkflowContext[dict]) -> None:
    await ctx.send_message(stage_judge(state))

@executor(id="Editor")
async def editor(state: dict, ctx: WorkflowContext[Never, dict]) -> None:
    await ctx.yield_output(stage_editor(state))

def build_workflow():
    return (WorkflowBuilder(start_executor=stats_analyst, output_from=[editor])
            .add_edge(stats_analyst, storyteller)
            .add_edge(storyteller, fact_checker)
            .add_edge(fact_checker, judge)
            .add_edge(judge, editor)
            .build())

async def arun(m, llm, audience="fan", lang="English"):
    result = await build_workflow().run({"m": m, "llm": llm, "audience": audience, "lang": lang, "max_fix": 1})
    return result.get_outputs()[0]

def run(m, llm, audience="fan", lang="English"):
    """Synchronous wrapper (runs the workflow on its own event loop, so it also works inside Colab/Jupyter)."""
    box = {}
    def go():
        try: box["out"] = asyncio.run(arun(m, llm, audience, lang))
        except BaseException as e: box["err"] = e
    t = threading.Thread(target=go); t.start(); t.join()
    if "err" in box: raise box["err"]
    return box["out"]
