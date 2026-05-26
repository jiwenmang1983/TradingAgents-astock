from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config for MiniMax + A-Share
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "minimax"
config["deep_think_llm"] = "MiniMax-M2.7"
config["quick_think_llm"] = "MiniMax-M2.7"
config["max_debate_rounds"] = 1
config["output_language"] = "Chinese"
config["data_vendors"] = {
    "core_stock_apis": "a_stock",
    "technical_indicators": "a_stock",
    "fundamental_data": "a_stock",
    "news_data": "a_stock",
    "signal_data": "a_stock",
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate - using 688017 (科创板股票) as example
_, decision = ta.propagate("688017", "2026-05-12")
print(decision)