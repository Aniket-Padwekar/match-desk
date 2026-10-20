"""Azure Function (Python v2 model): POST /api/ask. The Azure OpenAI key lives only in the Function App's settings."""
import os, logging
import azure.functions as func
from live_ask import handle, TableCaps

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
_caps = None
def caps():
    global _caps
    if _caps is None: _caps = TableCaps(os.environ["AzureWebJobsStorage"])
    return _caps
def llm():
    from agents import AzureLLM
    return AzureLLM(os.environ["AZURE_OPENAI_ENDPOINT"], os.environ["AZURE_OPENAI_KEY"], os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini"))

@app.route(route="ask", methods=["POST", "OPTIONS"])
def ask(req: func.HttpRequest) -> func.HttpResponse:
    try: c = caps()
    except Exception as e:
        logging.error("caps init failed: %s", e); c = type("Deny", (), {"get": lambda s, *a: 10**9, "add": lambda s, *a: None})()
    code, headers, body = handle(req.method, dict(req.headers), req.get_body(), llm, c)
    import json
    return func.HttpResponse(json.dumps(body, ensure_ascii=False) if body is not None else "", status_code=code, headers=headers, mimetype="application/json")

@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    import json
    try: used = caps().get("total", "all")
    except Exception: used = -1
    return func.HttpResponse(json.dumps({"ok": True, "used": used, "cap": int(os.environ.get("TOTAL_CAP", 300))}), mimetype="application/json")
