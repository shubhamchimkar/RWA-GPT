from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
from dotenv import load_dotenv
from agent import query_rwa_database, get_1inch_swap_data, search_web, tokens_for_chain
import re
import requests
from datetime import datetime
import random
import asyncio
import logging
# Optional x402 integration - doesn't break existing functionality
try:
    from x402_integration import X402PaymentProcessor, enhance_existing_payment_with_x402
    X402_AVAILABLE = True
except ImportError:
    X402_AVAILABLE = False

# Optional Supabase integration - doesn't break existing functionality
try:
    from supabase_client import insert_message, fetch_messages, initialize_supabase
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Load environment variables
load_dotenv()

# Configure allowed origins for CORS
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

extra_origins_env = os.getenv("ALLOWED_ORIGINS", "")
EXTRA_ALLOWED_ORIGINS = [origin.strip() for origin in extra_origins_env.split(",") if origin.strip()]
ALLOWED_ORIGINS = list(dict.fromkeys(DEFAULT_ALLOWED_ORIGINS + EXTRA_ALLOWED_ORIGINS))

# In-memory transaction storage (in production, use a database)
TRANSACTION_HISTORY = []

async def store_agent_response(response_text: str) -> None:
    """Helper function to store agent response in Supabase if available"""
    if SUPABASE_AVAILABLE:
        try:
            await insert_message(
                role="agent",
                content=response_text,
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        except Exception as e:
            logging.warning(f"Failed to store agent response in Supabase: {e}")

def update_transaction_status(tx_hash: str, status: str = "confirmed"):
    """Update transaction status after blockchain confirmation"""
    print(f"Updating transaction {tx_hash} to {status}")
    print(f"Current transaction history: {TRANSACTION_HISTORY}")
    
    for tx in TRANSACTION_HISTORY:
        print(f"Checking transaction: {tx.get('tx_hash')} == {tx_hash}")
        if tx.get("tx_hash") == tx_hash:
            tx["status"] = status
            tx["confirmed_at"] = datetime.now().isoformat()
            print(f"Updated transaction {tx_hash} to {status}")
            return True
    
    print(f"Transaction {tx_hash} not found in history")
    return False

def cleanup_duplicate_transactions():
    """Remove duplicate transactions and merge x402 payments with blockchain transactions"""
    global TRANSACTION_HISTORY
    
    # Group transactions by x402 payment ID
    x402_groups = {}
    standalone_transactions = []
    
    for tx in TRANSACTION_HISTORY:
        x402_id = tx.get("x402_payment_id")
        if x402_id:
            if x402_id not in x402_groups:
                x402_groups[x402_id] = []
            x402_groups[x402_id].append(tx)
        else:
            standalone_transactions.append(tx)
    
    # Merge transactions with same x402 payment ID
    cleaned_transactions = []
    
    for x402_id, group in x402_groups.items():
        # Find the transaction with blockchain hash
        blockchain_tx = None
        x402_only_tx = None
        
        for tx in group:
            if tx.get("tx_hash"):
                blockchain_tx = tx
            else:
                x402_only_tx = tx
        
        if blockchain_tx and x402_only_tx:
            # Merge the transactions
            merged_tx = {
                **x402_only_tx,  # Start with x402 transaction
                "tx_hash": blockchain_tx["tx_hash"],  # Add blockchain hash
                "status": blockchain_tx["status"],  # Use blockchain status
                "confirmed_at": blockchain_tx.get("confirmed_at")
            }
            cleaned_transactions.append(merged_tx)
            print(f"Merged x402 {x402_id} with blockchain transaction")
        elif blockchain_tx:
            cleaned_transactions.append(blockchain_tx)
        elif x402_only_tx:
            cleaned_transactions.append(x402_only_tx)
    
    # Add standalone transactions
    cleaned_transactions.extend(standalone_transactions)
    
    # Sort by timestamp (newest first)
    cleaned_transactions.sort(key=lambda x: x["timestamp"], reverse=True)
    
    TRANSACTION_HISTORY = cleaned_transactions
    print(f"Cleaned up transactions. New count: {len(TRANSACTION_HISTORY)}")

# Enhanced RWA Investment Database with detailed options
RWA_INVESTMENT_OPTIONS = {
    "treasury_bills": {
        "asset_id": "TCB-001",
        "asset_type": "Tokenized T-Bill",
        "protocol": "Ondo Finance",
        "yield_apy": 4.8,
        "min_investment": "1000 USDC",
        "risk_level": "Low",
        "liquidity": "High",
        "duration": "3-6 months",
        "description": "US Treasury Bills tokenized on-chain, backed by real government securities",
        "keywords": ["treasury", "t-bill", "government", "safe", "low risk", "stable", "conservative"]
    },
    "private_credit": {
        "asset_id": "PCR-007", 
        "asset_type": "Private Credit",
        "protocol": "Centrifuge",
        "yield_apy": 9.2,
        "min_investment": "5000 USDC",
        "risk_level": "Medium-High",
        "liquidity": "Medium",
        "duration": "12-24 months",
        "description": "Direct lending to companies, higher yields with moderate risk",
        "keywords": ["credit", "lending", "corporate", "medium risk", "yield", "debt"]
    },
    "real_estate": {
        "asset_id": "RWA-003",
        "asset_type": "Real Estate Token",
        "protocol": "RealT",
        "yield_apy": 6.5,
        "min_investment": "50 USDC",
        "risk_level": "Medium",
        "liquidity": "Low",
        "duration": "Long-term",
        "description": "Fractional ownership of rental properties with monthly dividends",
        "keywords": ["real estate", "property", "rental", "housing", "dividends", "reit"]
    },
    "commodities": {
        "asset_id": "CMD-012",
        "asset_type": "Commodity Token",
        "protocol": "Paxos",
        "yield_apy": 3.2,
        "min_investment": "100 USDC",
        "risk_level": "Medium",
        "liquidity": "High",
        "duration": "Flexible",
        "description": "Gold and precious metals backed tokens for inflation hedging",
        "keywords": ["gold", "silver", "commodity", "inflation", "hedge", "precious metals"]
    },
    "infrastructure": {
        "asset_id": "INF-008",
        "asset_type": "Infrastructure Bond",
        "protocol": "Maple Finance",
        "yield_apy": 7.8,
        "min_investment": "2500 USDC",
        "risk_level": "Medium",
        "liquidity": "Medium",
        "duration": "18-36 months",
        "description": "Financing for renewable energy and infrastructure projects",
        "keywords": ["infrastructure", "renewable", "energy", "solar", "wind", "green", "sustainable"]
    },
    "supply_chain": {
        "asset_id": "SCF-015",
        "asset_type": "Supply Chain Finance",
        "protocol": "TrueFi",
        "yield_apy": 8.5,
        "min_investment": "1000 USDC",
        "risk_level": "Medium-High",
        "liquidity": "Medium",
        "duration": "6-12 months",
        "description": "Trade finance for global supply chains and logistics",
        "keywords": ["supply chain", "trade", "logistics", "import", "export", "commerce"]
    }
}

def analyze_prompt_and_recommend(prompt: str) -> list:
    """
    Analyze user prompt and recommend relevant RWA investment options
    """
    prompt_lower = prompt.lower()
    recommendations = []
    
    # Score each investment option based on keyword matching
    for category, investment in RWA_INVESTMENT_OPTIONS.items():
        score = 0
        matched_keywords = []
        
        # Check for keyword matches
        for keyword in investment["keywords"]:
            if keyword in prompt_lower:
                score += 2
                matched_keywords.append(keyword)
        
        # Check for risk preference
        if any(word in prompt_lower for word in ["safe", "low risk", "conservative", "stable"]):
            if investment["risk_level"] == "Low":
                score += 3
        elif any(word in prompt_lower for word in ["high yield", "aggressive", "high return"]):
            if investment["risk_level"] in ["Medium-High", "High"]:
                score += 3
        elif any(word in prompt_lower for word in ["moderate", "balanced", "medium risk"]):
            if investment["risk_level"] == "Medium":
                score += 2
        
        # Check for yield preferences
        if any(word in prompt_lower for word in ["high yield", "good return", "profitable"]):
            if investment["yield_apy"] > 7:
                score += 2
        
        # Check for liquidity preferences
        if any(word in prompt_lower for word in ["liquid", "quick access", "flexible"]):
            if investment["liquidity"] == "High":
                score += 2
        
        # Check for investment amount preferences
        if any(word in prompt_lower for word in ["small", "little", "minimal"]):
            if investment["min_investment"] == "50 USDC" or investment["min_investment"] == "100 USDC":
                score += 1
        elif any(word in prompt_lower for word in ["large", "big", "substantial"]):
            if "5000" in investment["min_investment"] or "2500" in investment["min_investment"]:
                score += 1
        
        # Check for duration preferences
        if any(word in prompt_lower for word in ["short term", "quick", "temporary"]):
            if "3-6 months" in investment["duration"] or "6-12 months" in investment["duration"]:
                score += 1
        elif any(word in prompt_lower for word in ["long term", "permanent", "hold"]):
            if "Long-term" in investment["duration"] or "18-36 months" in investment["duration"]:
                score += 1
        
        if score > 0:
            investment_copy = investment.copy()
            investment_copy["relevance_score"] = score
            investment_copy["matched_keywords"] = matched_keywords
            recommendations.append(investment_copy)
    
    # Sort by relevance score (highest first)
    recommendations.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    # If no specific matches, return top 3 general options
    if not recommendations:
        return [
            RWA_INVESTMENT_OPTIONS["treasury_bills"],
            RWA_INVESTMENT_OPTIONS["real_estate"],
            RWA_INVESTMENT_OPTIONS["private_credit"]
        ]
    
    # Return top 3 recommendations
    return recommendations[:3]

def fetch_real_estate_rwa_data():
    """
    Fetch real-time Real Estate RWA data from multiple sources
    Focus on Real Estate for hackathon simplicity
    """
    real_estate_assets = []
    
    try:
        # Source 1: RealT API (Real Estate Tokenization Platform)
        try:
            realt_url = "https://api.realt.community/v1/token"
            response = requests.get(realt_url, timeout=10)
            if response.status_code == 200:
                realt_data = response.json()
                # Process first 5 properties
                for i, property_data in enumerate(realt_data[:5]):
                    if property_data.get('rentedUnits', 0) > 0:
                        asset = {
                            "asset_id": f"REALT-{i+1:03d}",
                            "asset_type": "Real Estate Token",
                            "protocol": "RealT",
                            "property_name": property_data.get('fullName', 'Unknown Property'),
                            "location": f"{property_data.get('city', 'Unknown')}, {property_data.get('state', 'US')}",
                            "yield_apy": round(float(property_data.get('annualPercentageYield', 0)), 2),
                            "token_price": round(float(property_data.get('tokenPrice', 0)), 2),
                            "total_tokens": property_data.get('totalTokens', 0),
                            "rented_units": property_data.get('rentedUnits', 0),
                            "total_units": property_data.get('totalUnits', 0),
                            "min_investment": f"{property_data.get('tokenPrice', 50)} USDC",
                            "status": "Active" if property_data.get('rentedUnits', 0) > 0 else "Inactive",
                            "last_updated": datetime.now().isoformat(),
                            "source": "RealT API"
                        }
                        real_estate_assets.append(asset)
        except Exception as e:
            print(f"RealT API error: {e}")
        
        # Source 2: Fallback with synthetic real-time data (for demo reliability)
        if len(real_estate_assets) < 3:
            synthetic_properties = [
                {
                    "property_name": "Detroit Residential Complex A",
                    "location": "Detroit, MI",
                    "base_apy": 8.2,
                    "base_price": 62.50
                },
                {
                    "property_name": "Cleveland Multi-Family B", 
                    "location": "Cleveland, OH",
                    "base_apy": 7.8,
                    "base_price": 45.00
                },
                {
                    "property_name": "Memphis Rental Portfolio C",
                    "location": "Memphis, TN", 
                    "base_apy": 9.1,
                    "base_price": 38.75
                },
                {
                    "property_name": "Birmingham Investment Property D",
                    "location": "Birmingham, AL",
                    "base_apy": 7.5,
                    "base_price": 55.25
                },
                {
                    "property_name": "Toledo Residential Units E",
                    "location": "Toledo, OH",
                    "base_apy": 8.7,
                    "base_price": 41.80
                }
            ]
            
            current_time = datetime.now()
            for i, prop in enumerate(synthetic_properties[:5]):
                # Add some realistic variation
                apy_variation = random.uniform(-0.5, 0.8)
                price_variation = random.uniform(-2.0, 3.0)
                
                asset = {
                    "asset_id": f"RE-{i+1:03d}",
                    "asset_type": "Real Estate Token",
                    "protocol": "RWA-GPT Demo",
                    "property_name": prop["property_name"],
                    "location": prop["location"],
                    "yield_apy": round(prop["base_apy"] + apy_variation, 2),
                    "token_price": round(prop["base_price"] + price_variation, 2),
                    "total_tokens": random.randint(800, 2000),
                    "rented_units": random.randint(12, 24),
                    "total_units": random.randint(15, 30),
                    "min_investment": f"{round(prop['base_price'] + price_variation, 2)} USDC",
                    "occupancy_rate": round(random.uniform(85, 98), 1),
                    "monthly_rent": random.randint(800, 1500),
                    "status": "Active",
                    "last_updated": current_time.isoformat(),
                    "source": "Real-time Demo Data"
                }
                real_estate_assets.append(asset)

    except Exception as e:
        print(f"Error fetching real estate data: {e}")
        # Ultimate fallback
        real_estate_assets = [{
            "asset_id": "RE-FALLBACK",
            "asset_type": "Real Estate Token", 
            "protocol": "Demo",
            "property_name": "Sample Property",
            "location": "Demo City, US",
            "yield_apy": 7.5,
            "token_price": 50.0,
            "min_investment": "50 USDC",
            "status": "Active",
            "last_updated": datetime.now().isoformat(),
            "source": "Fallback Data"
        }]
    
    return real_estate_assets[:5]  # Return top 5 properties

app = FastAPI(title="RWA-GPT API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "endpoints": ["/health", "/ask-agent", "/update-transaction", "/store-transaction"]}

@app.post("/update-transaction")
async def update_transaction(request: dict):
    """Update transaction status after blockchain confirmation"""
    try:
        tx_hash = request.get("tx_hash")
        status = request.get("status", "confirmed")
        
        if not tx_hash:
            return {"error": "tx_hash is required"}
        
        update_transaction_status(tx_hash, status)
        
        return {
            "success": True,
            "message": f"Transaction {tx_hash} updated to {status}",
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/store-transaction")
async def store_transaction(request: dict):
    """Store transaction hash when transaction is first submitted"""
    try:
        tx_hash = request.get("tx_hash")
        amount = request.get("amount", "unknown")
        asset_id = request.get("asset_id", "RE-001")
        status = request.get("status", "pending")
        x402_payment_id = request.get("x402_payment_id")
        
        if not tx_hash:
            return {"error": "tx_hash is required"}
        
        print(f"Storing transaction hash: {tx_hash}")
        print(f"x402 payment ID: {x402_payment_id}")
        print(f"Current history before update: {TRANSACTION_HISTORY}")
        
        # Find the most recent pending transaction with matching x402 payment ID
        updated = False
        for tx in reversed(TRANSACTION_HISTORY):
            # Match by x402 payment ID if provided, otherwise match by pending status
            if x402_payment_id and tx.get("x402_payment_id") == x402_payment_id:
                tx["tx_hash"] = tx_hash
                updated = True
                print(f"Updated x402 transaction {x402_payment_id} with hash: {tx_hash}")
                break
            elif not x402_payment_id and tx["status"] == "pending" and tx["tx_hash"] is None:
                tx["tx_hash"] = tx_hash
                updated = True
                print(f"Updated pending transaction with hash: {tx_hash}")
                break
        
        if not updated:
            print("No matching transaction found, creating new entry")
            # Create a new transaction record if none found
            new_transaction = {
                "timestamp": datetime.now().isoformat(),
                "user_address": "unknown",
                "amount": amount,
                "asset_id": asset_id,
                "transaction_type": "investment",
                "x402_payment_id": x402_payment_id,
                "status": status,
                "chain_id": 80002,
                "tx_hash": tx_hash,
                "confirmed_at": None
            }
            TRANSACTION_HISTORY.append(new_transaction)
            print(f"Created new transaction record: {new_transaction}")
        
        print(f"History after update: {TRANSACTION_HISTORY}")
        
        return {
            "success": True,
            "message": f"Transaction hash {tx_hash} stored",
            "stored_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

class MessageRequest(BaseModel):
    message: str
    chainId: int | None = None
    fromAddress: str | None = None

class MessageResponse(BaseModel):
    response: str
    is_transaction: bool = False
    transaction_data: dict | None = None

@app.post("/ask-agent", response_model=MessageResponse)
async def ask_agent(request: MessageRequest):
    try:
        message = request.message.lower()
        
        # Store user message in Supabase if available
        if SUPABASE_AVAILABLE:
            try:
                await insert_message(
                    role="user",
                    content=request.message,
                    timestamp=datetime.utcnow().isoformat() + "Z"
                )
            except Exception as e:
                logging.warning(f"Failed to store user message in Supabase: {e}")

        # Priority 1: Check for web search intent first.
        # This is to distinguish "best investments" (search) from "invest 100 usdc" (action).
        search_keywords = ["search", "what is", "who is", "explain", "best", "top", "latest", "find", "tell me about", "compare", "how to"]
        is_direct_investment_command = "invest" in message and any(token in message for token in ["usdc", "dai", "tcb", "pcr", "rwa"])

        if any(keyword in message for keyword in search_keywords) and not is_direct_investment_command:
            try:
                search_result = await search_web(request.message)
                await store_agent_response(search_result)
                return MessageResponse(
                    response=search_result,
                    is_transaction=False
                )
            except Exception as e:
                logging.error(f"Web search failed: {e}")
                # If search fails, we can fall through to other handlers.
                pass
        
        # Check if user wants to see transaction history
        if any(keyword in message for keyword in ["transaction history", "my transactions", "transaction list", "history", "past transactions"]):
            # Clean up duplicate transactions before showing history
            cleanup_duplicate_transactions()
            
            user_address = request.fromAddress or "0x1234567890123456789012345678901234567890"
            
            # Filter transactions for this user
            user_transactions = [tx for tx in TRANSACTION_HISTORY if tx["user_address"].lower() == user_address.lower()]
            
            if not user_transactions:
                response_text = "📋 **Your Transaction History**\n\nNo transactions found yet.\n\n💡 Try making an investment first:\n• 'invest 100 USDC in RE-001'\n• 'invest 50 USDC in RE-002'"
                await store_agent_response(response_text)
                return MessageResponse(
                    response=response_text,
                    is_transaction=False
                )
            
            # Sort by timestamp (newest first)
            user_transactions.sort(key=lambda x: x["timestamp"], reverse=True)
            
            response_text = f"📋 **Your Transaction History**\n\n"
            response_text += f"Found {len(user_transactions)} transaction(s)\n\n"
            
            for i, tx in enumerate(user_transactions, 1):
                response_text += f"🔹 **Transaction #{i}**\n"
                response_text += f"   💰 Amount: {tx['amount']} USDC\n"
                response_text += f"   🏠 Asset: {tx['asset_id']}\n"
                response_text += f"   📅 Time: {tx['timestamp'][:19].replace('T', ' ')}\n"
                response_text += f"   🔗 Chain: Polygon Amoy (ID: {tx['chain_id']})\n"
                
                # Status with emoji
                status_emoji = "✅" if tx['status'] == "confirmed" else "⏳" if tx['status'] == "pending" else "❌"
                response_text += f"   📊 Status: {status_emoji} {tx['status'].title()}\n"
                
                if tx.get('tx_hash'):
                    response_text += f"   🔗 TX Hash: {tx['tx_hash']}\n"
                if tx.get('confirmed_at'):
                    response_text += f"   ✅ Confirmed: {tx['confirmed_at'][:19].replace('T', ' ')}\n"
                if tx.get('x402_payment_id'):
                    response_text += f"   🤖 x402 ID: {tx['x402_payment_id']}\n"
                response_text += "\n"
            
            response_text += "💡 **Commands:**\n"
            response_text += "• 'invest 100 USDC in RE-001' - Make new investment\n"
            response_text += "• 'show real estate investments' - View available options\n"
            response_text += "• 'transaction history' - View this list again\n"
            
            await store_agent_response(response_text)
            return MessageResponse(
                response=response_text,
                is_transaction=False
            )
        
        # Check if user wants to see RAW subgraph data (very specific request)
        elif message in ["subgraph data", "raw data"]:
            subgraph_url = os.getenv("SUBGRAPH_URL")
            if subgraph_url:
                live_data = query_rwa_database(subgraph_url)
                if live_data:
                    response_text = f"Raw investment data from subgraph:\n{json.dumps(live_data, indent=2)}"
                    await store_agent_response(response_text)
                    return MessageResponse(
                        response=response_text,
                        is_transaction=False
                    )
                # Fall back to curated options when subgraph has no data yet
                mock_investments = """[
  {
    "asset_id": "TCB-001",
    "asset_type": "Tokenized T-Bill",
    "protocol": "Ondo",
    "yield_apy": 4.8,
    "min_investment": "1000 USDC",
    "status": "Active"
  },
  {
    "asset_id": "PCR-007", 
    "asset_type": "Private Credit",
    "protocol": "Centrifuge",
    "yield_apy": 9.2,
    "min_investment": "5000 USDC",
    "status": "Active"
  },
  {
    "asset_id": "RWA-003",
    "asset_type": "Real Estate Token",
    "protocol": "RealT",
    "yield_apy": 6.5,
    "min_investment": "50 USDC",
    "status": "Active"
  }
]"""
                response_text = f"No indexed investments yet. Here are curated options you can try now:\n{mock_investments}"
                await store_agent_response(response_text)
                return MessageResponse(
                    response=response_text,
                    is_transaction=False
                )
            else:
                # Return mock data when subgraph is not configured
                mock_investments = """[
  {
    "asset_id": "TCB-001",
    "asset_type": "Tokenized T-Bill",
    "protocol": "Ondo",
    "yield_apy": 4.8,
    "min_investment": "1000 USDC",
    "status": "Active"
  },
  {
    "asset_id": "PCR-007", 
    "asset_type": "Private Credit",
    "protocol": "Centrifuge",
    "yield_apy": 9.2,
    "min_investment": "5000 USDC",
    "status": "Active"
  },
  {
    "asset_id": "RWA-003",
    "asset_type": "Real Estate Token",
    "protocol": "RealT",
    "yield_apy": 6.5,
    "min_investment": "50 USDC",                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        
    "status": "Active"
  }
]"""
                response_text = f"Available RWA Investment Options:\n{mock_investments}\n\nTo invest, try: 'invest 100 USDC in TCB-001'"
                await store_agent_response(response_text)
                return MessageResponse(
                    response=response_text,
                    is_transaction=False
                )
        
        # Check if user wants to invest (more flexible matching)
        elif is_direct_investment_command:
            try:
                # Extract amount from message (simple parse; default 100)
                m = re.search(r"(\d+(?:\.\d+)?)", request.message)
                amount = m.group(1) if m else "100"
                from_address = request.fromAddress or "0x1234567890123456789012345678901234567890"  # Placeholder
                chain_id = 80002  # Force Polygon Amoy Testnet for testing
                
                # Get correct token addresses for the testnet
                from agent import tokens_for_chain
                src_token, dst_token, src_decimals = tokens_for_chain(chain_id)
                
                # Get swap data from 1inch
                swap_data = get_1inch_swap_data(
                    chain_id=chain_id,
                    src_token=src_token,  # USDC on Amoy Testnet
                    dst_token=dst_token,  # WETH on Amoy Testnet
                    amount_human=amount,
                    src_token_decimals=src_decimals,
                    from_address=from_address,
                )
                
                is_tx = bool(swap_data and isinstance(swap_data, dict) and (swap_data.get("tx") or swap_data.get("to")))

                # Demo fallback: if no tx from aggregators, return a safe no-op tx
                tx_payload = None
                if not is_tx:
                    tx = {
                        "to": from_address,
                        "data": "0x",
                        "value": "0x0",
                        "gas": "0x5208",
                    }
                    tx_payload = tx
                    is_tx = True
                else:
                    tx_payload = swap_data.get("tx") or swap_data

                # Optional x402 enhancement (doesn't break existing flow)
                response_text = f"1inch swap data for {amount} USDC:"
                x402_payment_id = None
                if X402_AVAILABLE:
                    try:
                        x402_processor = X402PaymentProcessor()
                        x402_result = x402_processor.process_agent_payment(
                            investment_request=request.message,
                            amount=amount,
                            asset_id="RE-001",  # Extract from message in production
                            user_address=from_address
                        )
                        if x402_result["status"] == "processed":
                            x402_payment_id = x402_result['x402_payment_id']
                            response_text += f"\n\n🤖 x402 Agentic Payment Available:\n{x402_result['agent_response']}\n💡 Payment ID: {x402_payment_id}"
                            # Add x402 metadata to transaction
                            if isinstance(tx_payload, dict):
                                tx_payload["x402_metadata"] = x402_result
                    except Exception as e:
                        # Silently continue with existing flow if x402 fails
                        pass

                # Store transaction in history
                transaction_record = {
                    "timestamp": datetime.now().isoformat(),
                    "user_address": from_address,
                    "amount": amount,
                    "asset_id": "RE-001",
                    "transaction_type": "investment",
                    "x402_payment_id": x402_payment_id,
                    "status": "pending",
                    "chain_id": chain_id,
                    "tx_hash": None,  # Will be updated when transaction is executed
                    "confirmed_at": None
                }
                TRANSACTION_HISTORY.append(transaction_record)

                return MessageResponse(
                    response=response_text,
                    is_transaction=is_tx,
                    transaction_data=tx_payload
                )
            except Exception as e:
                return MessageResponse(
                    response=f"Error getting swap data: {str(e)}",
                    is_transaction=False
                )
        
        # Real-time RWA data (focused on Real Estate for hackathon)
        else:
            # Check if user is asking for real estate or general investments
            if any(keyword in message for keyword in ["real estate", "property", "rental", "realt", "rwa", "investment"]) and not is_direct_investment_command:
                # Fetch real-time real estate data
                real_estate_data = fetch_real_estate_rwa_data()
                
                response_text = f"🏠 **REAL-TIME REAL ESTATE RWA INVESTMENTS**\n"
                response_text += f"📊 Live data updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                
                for i, asset in enumerate(real_estate_data, 1):
                    response_text += f"🏆 #{i} - {asset['asset_id']}\n"
                    response_text += f"🏢 Property: {asset['property_name']}\n"
                    response_text += f"📍 Location: {asset['location']}\n"
                    response_text += f"💰 APY: {asset['yield_apy']}% | Token Price: ${asset['token_price']}\n"
                    
                    if asset.get('occupancy_rate'):
                        response_text += f"🏠 Occupancy: {asset['occupancy_rate']}% | Units: {asset['rented_units']}/{asset['total_units']}\n"
                    if asset.get('monthly_rent'):
                        response_text += f"💵 Monthly Rent: ${asset['monthly_rent']}\n"
                    
                    response_text += f"🔵 Min Investment: {asset['min_investment']}\n"
                    response_text += f"📈 Status: {asset['status']} | Source: {asset['source']}\n"
                    response_text += f"⚡ To invest: 'invest 100 USDC in {asset['asset_id']}'\n\n"
                
                response_text += "🎯 **Why Real Estate RWA?**\n"
                response_text += "• Fractional ownership of real properties\n"
                response_text += "• Monthly rental income distributions\n"
                response_text += "• Transparent, blockchain-verified ownership\n"
                response_text += "• Lower minimum investments than traditional REITs\n\n"
                response_text += "💡 Try: 'invest 50 USDC in RE-001' or 'show me more properties'\n"
                
                return MessageResponse(
                    response=response_text,
                    is_transaction=False
                )
            else:
                # Fallback to web search if no other handlers match
                try:
                    search_result = await search_web(request.message)
                    await store_agent_response(search_result)
                    return MessageResponse(
                        response=search_result,
                        is_transaction=False
                    )
                except Exception as e:
                    logging.error(f"Fallback web search failed: {e}")
                    # Final fallback if search also fails
                    return MessageResponse(
                        response="I'm not sure how to handle that. Please try asking in a different way.",
                        is_transaction=False
                    )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/messages")
async def get_messages(limit: int = 50):
    """Fetch chat messages from Supabase database"""
    if not SUPABASE_AVAILABLE:
        return {"error": "Supabase not available", "messages": []}
    
    try:
        messages = await fetch_messages(limit=limit)
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        logging.error(f"Failed to fetch messages: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {e}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
