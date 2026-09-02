"""
LangGraph graph definition — the explicit state graph for the CalorAI agent.

Why LangGraph instead of a plain agent executor:
  - Multi-turn ambiguity handling is a control-flow decision. A graph makes
    that decision path inspectable and testable, not buried in a black-box loop.
  - The correction case ("actually that was 3 rotis not 2") requires precise
    state mutation. A graph with explicit nodes for tool execution makes the
    correctness guarantee auditable.

Graph structure:
  preprocess → load_context → agent ↔ tools → post_process

The agent ↔ tools loop is the standard LangGraph ReAct pattern: the agent
decides to call tools or respond, and the graph routes accordingly.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage

from backend.agent.state import AgentState
from backend.agent.nodes import preprocess, load_context, agent_node, post_process
from backend.agent.tools import ALL_TOOLS


def should_continue(state: AgentState) -> str:
    """
    Routing function: decide whether the agent needs to execute tools
    or is done and should post-process.

    This is where the graph makes the tool-call vs. respond decision
    explicit and inspectable.
    """
    messages = state.get("messages", [])
    if not messages:
        return "post_process"

    last_message = messages[-1]

    # If the last message has tool calls, route to tool execution
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    # Otherwise, the agent is done — go to post-processing
    return "post_process"


def create_graph():
    """
    Build and compile the CalorAI agent graph.

    Returns a compiled LangGraph that can be invoked with:
        result = graph.invoke({
            "messages": [HumanMessage(content="had 2 parathas")],
            "user_id": "default",
            "session_id": "abc123",
            "image_path": None,
        })
    """
    # Create the tool node from our tool list
    tool_node = ToolNode(ALL_TOOLS)

    # Build the graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("preprocess", preprocess)
    graph.add_node("load_context", load_context)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("post_process", post_process)

    # Define edges
    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "load_context")
    graph.add_edge("load_context", "agent")

    # Conditional: agent → tools (if tool calls) or → post_process (if done)
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "post_process": "post_process",
        },
    )

    # After tool execution, go back to agent for continued reasoning
    graph.add_edge("tools", "agent")

    # Post-process leads to end
    graph.add_edge("post_process", END)

    # Compile
    compiled = graph.compile()
    return compiled


# Create a singleton graph instance
agent_graph = create_graph()
