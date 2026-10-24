"""Optional tracing of the Agent Framework workflow into Azure Monitor (Application Insights), which Microsoft Foundry
shows under Tracing. Off unless APPLICATIONINSIGHTS_CONNECTION_STRING is set. It never stops a run: any problem is reported, not raised.
Needs: pip install azure-monitor-opentelemetry
STATUS: written from the Agent Framework documentation and NOT yet run against a live Azure resource."""
import os

_done = False

def enable_tracing():
    """Returns a short status string. Safe to call more than once."""
    global _done
    cs = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not cs: return "tracing off (no connection string)"
    if _done: return "tracing already on"
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor(connection_string=cs)
        from agent_framework.observability import enable_instrumentation
        enable_instrumentation()
        _done = True
        return "tracing on"
    except Exception as e:
        return f"tracing could not start: {type(e).__name__}: {e}"
