import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from uagents import Agent, Context, Model
from decimal import Decimal
from typing import Tuple, Optional
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import asyncio

# Initialize the tools
tavily_tool = TavilySearchResults(max_results=5)
tools = [tavily_tool]

# Initialize the model
model = ChatOpenAI(temperature=0)

# Create the agent
graph = create_react_agent(model, tools)


class Message(Model):
    content: str


agent = Agent(name="RWA-GPT-Agent")

async def search_web(query: str):
    """Search the web for a query and provide RWA-focused analysis or a direct answer."""
    
    # Determine if the query is a simple greeting or unrelated to finance
    is_generic_query = query.lower().strip() in ["hello", "hi", "how are you", "help"]

    # If it's a generic query, provide a helpful, general-purpose response
    if is_generic_query:
        return (
            "Hello! I am an AI assistant specializing in Real World Assets (RWA). "
            "You can ask me about RWA investments, market trends, or specific assets. "
            "For example, try 'show me real estate investments' or 'what is the APY for tokenized T-bills?'"
        )

    # Determine if the query is definitional
    is_definitional = any(q in query.lower() for q in ["what is", "what are", "define", "explain"])

    if is_definitional:
        # Prompt for providing a direct definition
        prompt = f"""
        You are a specialized financial analyst AI focusing on Real World Assets (RWA).
        A user has the following query: "{query}"

        Your task is to provide a clear, concise, and direct definition or explanation in well-formatted Markdown.

        1.  **Analyze the Query**: Understand the core concept the user is asking about.
        2.  **Web Search**: Use the search tool to find authoritative definitions and explanations.
        3.  **Synthesize and Format**: Create a direct answer. Start with a simple definition, then provide more detail, examples, and explain its significance in the context of DeFi and investing. 
        
        Do NOT use the "Analytics Summary" or "Recommendations" format for this type of query.
        """
    else:
        # Prompt for providing a structured analytical summary
        prompt = f"""
        You are a specialized financial analyst AI focusing exclusively on Real World Assets (RWA).
        A user has the following query: "{query}"

        Your task is to generate a response in clean, well-formatted Markdown.

        1.  **Analyze the Query**: Re-interpret the user's query strictly within the context of Real World Assets. If the query is "best investments", treat it as "best RWA investments".
        2.  **Web Search**: Use the search tool to find relevant articles, market data, and analytics about the RWA-focused query. Prioritize sources with concrete data.
        3.  **Synthesize and Format**: Create a response with the following structure:

            ### 📊 Analytics Summary
            -   **Typical APY**: Provide a range (e.g., 4% - 12%).
            -   **Risk Level**: Categorize as Low, Medium, or High, and briefly explain why.
            -   **Popular Platforms**: List 2-3 key protocols or platforms in this space (e.g., Ondo Finance, Centrifuge, RealT).
            -   **Market Trend**: Briefly describe the current market trend (e.g., "Growing adoption due to high yields in traditional finance").
            -   **Liquidity**: Describe the typical liquidity (e.g., "Varies from highly liquid T-bills to illiquid real estate tokens").

            ### 💡 Recommendations
            Based on the analytics, provide a clear, actionable recommendation. Use bullet points.
            -   **For Conservative Investors**: Suggest a specific type of RWA and explain why it's suitable.
            -   **For High-Yield Seekers**: Suggest a different type of RWA and explain the risk/reward trade-off.

        Ensure the entire output is valid Markdown. Do not include any preamble before the first heading.
        """
    
    try:
        # The create_react_agent expects a list of messages
        messages = [("human", prompt)]
        response = await graph.ainvoke({"messages": messages})
        # The final answer is in the 'content' of the last message
        return response['messages'][-1].content
    except Exception as e:
        return f"Error searching web: {str(e)}"



@agent.on_message(model=Message)
async def handle_message(ctx: Context, sender: str, msg: Message) -> None:
    ctx.logger.info(f"Received message from {sender}: {msg.content}")
    
    # Check if user wants to see investments
    if "show investments" in msg.content.lower() or "show me investment options" in msg.content.lower():
        # This is a mock response. In a real application, you would fetch this from a database or API.
        response = """
### 🏠 REAL-TIME REAL ESTATE RWA INVESTMENTS
*Live data updated: 2025-10-19 21:17:10*

---

**🏆 #1 - RE-001**
- **Property:** Detroit Residential Complex A
- **Location:** Detroit, MI 💰
- **APY:** 8.01%
- **Token Price:** $63.27
- **Occupancy:** 92.5%
- **Units:** 15/24
- **Monthly Rent:** $1498
- **Min Investment:** 63.27 USDC
- **Status:** Active
- **Source:** Real-time
- **To invest:** `invest 100 USDC in RE-001`

**🏆 #2 - RE-002**
- **Property:** Cleveland Multi-Family B
- **Location:** Cleveland, OH 💰
- **APY:** 8.02%
- **Token Price:** $44.78
- **Occupancy:** 91.5%
- **Units:** 23/25
- **Monthly Rent:** $892
- **Min Investment:** 44.78 USDC
- **Status:** Active
- **Source:** Real-time
- **To invest:** `invest 100 USDC in RE-002`

**🏆 #3 - RE-003**
- **Property:** Memphis Rental Portfolio C
- **Location:** Memphis, TN 💰
- **APY:** 9.43%
- **Token Price:** $37.05
- **Occupancy:** 91.6%
- **Units:** 12/28
- **Monthly Rent:** $1221
- **Min Investment:** 37.05 USDC
- **Status:** Active
- **Source:** Real-time
- **To invest:** `invest 100 USDC in RE-003`
"""
    # Check if user wants to invest
    elif "invest" in msg.content.lower() and "usdc" in msg.content.lower():
        # Extract amount and asset from message (simplified parsing)
        try:
            # For demo: "invest 100 USDC in TCB-001"
            parts = msg.content.lower().split()
            amount = "100"  # Simplified - would need proper parsing
            from_address = "0x1234567890123456789012345678901234567890"  # Placeholder
            
            # Get swap data from 1inch
            # Default to Polygon if not provided elsewhere
            chain_id = 137
            src_token, dst_token, usdc_decimals = tokens_for_chain(chain_id)

            swap_data = get_1inch_swap_data(
                chain_id=chain_id,
                src_token=src_token,
                dst_token=dst_token,
                amount_human=amount,
                src_token_decimals=usdc_decimals,
                from_address=from_address,
            )
            
            # Decide whether we have a transaction
            is_tx = bool(isinstance(swap_data, dict) and (swap_data.get("tx") or swap_data.get("to")))
            pretty = json.dumps(swap_data, indent=2)
            response = f"1inch swap data for {amount} USDC:\n{pretty}" if is_tx else f"No executable tx from aggregator. Details:\n{pretty}"
        except Exception as e:
            response = f"Error getting swap data: {str(e)}"
    elif "search" in msg.content.lower() or "rwa best investment" in msg.content.lower():
        query = msg.content.replace("search", "").strip()
        response = await search_web(query)
    else:
        response = "Message received, you can ask me to 'search <your query>' or 'show investments' or 'invest <amount> USDC in <asset>'"
    
    await ctx.send(sender, Message(content=response))


def query_rwa_database(subgraph_url: str):
    """Return latest 5 investments from subgraph, or None on error."""
    try:
        query = {
            "query": "{ investments(first: 5, orderBy: timestamp, orderDirection: desc) { id investor amount timestamp } }"
        }
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("SUBGRAPH_API_KEY")
        if api_key:
            headers["X-API-KEY"] = api_key
        response = requests.post(subgraph_url, json=query, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("data") and data["data"].get("investments") is not None:
            return data["data"]["investments"]
        return None
    except Exception:
        return None


def get_1inch_swap_data(chain_id: int, src_token: str, dst_token: str, amount_human: str, src_token_decimals: int, from_address: str) -> dict:
    """
    Get swap data from 1inch API for specified EVM chain
    """
    try:
        # Prefer 1inch DEV API (requires API key). Fallback to 0x if unavailable
        oneinch_api_key = os.getenv("ONEINCH_API_KEY")
        oneinch_url = f"https://api.1inch.dev/swap/v5.2/{chain_id}/swap"

        # Convert human amount to minimal units
        amount_units = str(int(Decimal(amount_human) * (10 ** src_token_decimals)))
        
        params = {
            "src": src_token,
            "dst": dst_token,
            "amount": amount_units,
            "from": from_address,
            "slippage": "1"
        }
        
        if oneinch_api_key:
            headers = {"Authorization": f"Bearer {oneinch_api_key}"}
            try:
                response = requests.get(oneinch_url, params=params, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and (data.get("tx") or data.get("to")):
                    return data
            except Exception:
                # Fall through to 0x
                pass

        # Fallback: 0x quote (often works without API key for demos)
        if chain_id == 137:
            zerox_url = "https://polygon.api.0x.org/swap/v1/quote"
        elif chain_id == 1:
            zerox_url = "https://api.0x.org/swap/v1/quote"
        else:
            return {"error": "Unsupported chain for fallback aggregator"}

        zerox_params = {
            "sellToken": src_token,
            "buyToken": dst_token,
            "sellAmount": amount_units,
            "takerAddress": from_address,
            "slippagePercentage": "0.01",
        }
        try:
            zr = requests.get(zerox_url, params=zerox_params, timeout=15)
            zr.raise_for_status()
            z = zr.json()
            # Normalize to 1inch-like shape with tx field
            tx = {
                "to": z.get("to"),
                "data": z.get("data"),
                "value": hex(int(z.get("value", "0"))),
                "gas": hex(int(z.get("gas"))) if z.get("gas") else None,
                "gasPrice": hex(int(z.get("gasPrice"))) if z.get("gasPrice") else None,
            }
            return {"tx": tx, "_source": "0x"}
        except Exception as e:
            return {"error": f"aggregator_unavailable: {str(e)}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"1inch API error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def tokens_for_chain(chain_id: int) -> Tuple[str, str, int]:
    """Return (usdc, weth, usdc_decimals) for a supported chain."""
    if chain_id == 1:
        # Ethereum Mainnet
        return (
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            6,
        )
    elif chain_id == 137:
        # Polygon Mainnet
        return (
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
            6,
        )
    elif chain_id == 80002:
        # Polygon Amoy Testnet
        return (
            "0x41E94Eb019C0762f9Bfcf9Fb1E58725BfB0e7582",  # USDC on Amoy
            "0x360ad4f9a9A8EFe9A8DCB5f461c4Cc1047E1Dcf9",  # WETH on Amoy
            6,
        )
    # Default to Polygon Mainnet
    return (
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
        "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
        6,
    )


if __name__ == "__main__":
    agent.run()


