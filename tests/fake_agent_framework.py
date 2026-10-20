"""Tiny stand-in for the agent_framework package, only to test the wiring offline (the real package is used in Colab/CI)."""
import sys, types, asyncio, copy
class WorkflowContext:
    def __class_getitem__(cls, item): return cls
    def __init__(self, out, outputs): self._o, self._out = out, outputs
    async def send_message(self, msg): self._o.append(copy.deepcopy(msg))   # like the real framework: messages are copied
    async def yield_output(self, v): self._out.append(v)
class _Ex:
    def __init__(self, fn, id): self.fn, self.id = fn, id
def executor(id):
    return lambda fn: _Ex(fn, id)
class _Result:
    def __init__(self, outs): self._o = outs
    def get_outputs(self): return self._o
class WorkflowBuilder:
    def __init__(self, start_executor, output_from=None): self.start, self.edges = start_executor, {}
    def add_edge(self, a, b): self.edges[a.id] = b; return self
    def build(self):
        b = self
        class W:
            async def run(self, msg):
                cur, outs = b.start, []
                while cur:
                    sent = []; await cur.fn(msg, WorkflowContext(sent, outs)); msg = sent[0] if sent else None
                    cur = b.edges.get(cur.id)
                return _Result(outs)
        return W()
mod = types.ModuleType("agent_framework"); mod.WorkflowContext = WorkflowContext; mod.executor = executor; mod.WorkflowBuilder = WorkflowBuilder
sys.modules["agent_framework"] = mod
