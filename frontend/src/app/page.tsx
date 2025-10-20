"use client";

import { useState, useEffect, useRef } from "react";
import { ethers } from "ethers";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  polygonProvider, 
  POLYGON_CONFIG, 
  POLYGON_ERRORS,
  formatAddress,
  formatBalance,
  forcePhantomUsage
} from "../utils/polygon";

declare global {
  interface Window {
    ethereum?: {
      request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
      send: (method: string, params?: unknown[]) => Promise<unknown>;
      isMetaMask?: boolean;
      isPhantom?: boolean;
      isBraveWallet?: boolean;
      isCoinbaseWallet?: boolean;
      providers?: Array<{
        isMetaMask?: boolean;
        isPhantom?: boolean;
        isBraveWallet?: boolean;
        request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
      }>;
    };
    solana?: {
      isPhantom?: boolean;
      connect: () => Promise<void>;
    };
  }
}

interface Message {
  sender: 'user' | 'agent';
  text: string;
  isTransaction?: boolean;
  transactionData?: Record<string, unknown>;
}

interface WalletState {
  address: string | null;
  provider: ethers.BrowserProvider | null;
  signer: ethers.JsonRpcSigner | null;
  balance: string;
  isConnectedToPolygon: boolean;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [wallet, setWallet] = useState<WalletState>({
    address: null,
    provider: null,
    signer: null,
    balance: "0",
    isConnectedToPolygon: false
  });
  const [isConnecting, setIsConnecting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Auto-scroll to bottom when new messages are added
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Connect wallet to Polygon
  const connectWallet = async () => {
    try {
      setIsConnecting(true);
      
      // Try to force Phantom usage first
      console.log('🔧 Attempting to force Phantom usage...');
      forcePhantomUsage();
      
      // Use Polygon provider
      const { address, provider, signer } = await polygonProvider.connect();
      
      // Get balance
      const balance = await polygonProvider.getBalance();
      
      // Check if connected to Polygon
      const isConnectedToPolygon = await polygonProvider.isConnectedToPolygon();
      
      setWallet({
        address,
        provider,
        signer,
        balance,
        isConnectedToPolygon
      });
      
      // Show success message
      const successMessage: Message = {
        sender: 'agent',
        text: `✅ Connected to Polygon!\n💰 Balance: ${formatBalance(balance)}\n🌐 Network: ${POLYGON_CONFIG.chainName}`,
        isTransaction: false
      };
      setMessages(prev => [...prev, successMessage]);
      
    } catch (error: unknown) {
      console.error("Error connecting to Polygon:", error);
      
      let errorMsg = POLYGON_ERRORS.WALLET_NOT_CONNECTED;
      const errorText = error instanceof Error ? error.message : String(error);
      if (errorText.includes('network')) {
        errorMsg = POLYGON_ERRORS.NETWORK_NOT_FOUND;
      } else if (errorText.includes('rejected')) {
        errorMsg = POLYGON_ERRORS.USER_REJECTED;
      }
      
      const errorMessage: Message = {
        sender: 'agent',
        text: `❌ ${errorMsg}\n\n💡 Make sure to:\n• Install Phantom (👻 https://phantom.app)\n• Switch Phantom to Ethereum mode\n• Add Polygon Amoy testnet to Phantom\n• Get test MATIC tokens from the faucet`,
        isTransaction: false
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsConnecting(false);
    }
  };

  // Execute swap transaction on Polygon
  const executeSwap = async (transactionData: Record<string, unknown>) => {
    if (!wallet.signer) {
      const errorMessage: Message = {
        sender: 'agent',
        text: `❌ ${POLYGON_ERRORS.WALLET_NOT_CONNECTED}`,
        isTransaction: false
      };
      setMessages(prev => [...prev, errorMessage]);
      return;
    }

    try {
      // Check if we're on Polygon
      if (!wallet.isConnectedToPolygon) {
        const networkErrorMessage: Message = {
          sender: 'agent',
          text: `❌ ${POLYGON_ERRORS.WRONG_NETWORK}\n\n💡 Please switch to Polygon Amoy testnet in your wallet.`,
          isTransaction: false
        };
        setMessages(prev => [...prev, networkErrorMessage]);
        return;
      }

      // Parse the 1inch transaction data properly
      let txParams: Record<string, unknown> = {};
      
      const txData = transactionData.tx as Record<string, unknown>;
      if (txData) {
        // 1inch v5 format
        txParams = {
          to: txData.to as string,
          value: (txData.value as string) || "0x0",
          data: txData.data as string,
          gasLimit: (txData.gas as string) || "0x5208", // Default gas limit
        };
      } else if (transactionData.to) {
        // Direct format
        txParams = {
          to: transactionData.to as string,
          value: (transactionData.value as string) || "0x0",
          data: transactionData.data as string,
          gasLimit: (transactionData.gas as string) || "0x5208",
        };
      } else {
        throw new Error("Invalid transaction data format");
      }

      // Add gas price if available
      if (transactionData.gasPrice) {
        txParams.gasPrice = transactionData.gasPrice as string;
      }

      console.log("Sending transaction with params:", txParams);

      // Use Polygon provider for transaction execution
      const txResponse = await polygonProvider.executeTransaction({
        to: txParams.to as string,
        value: txParams.value as string,
        data: txParams.data as string,
        gasLimit: txParams.gasLimit as string,
      });
      const txHash = (txResponse as { hash: string }).hash;

      // Store transaction hash in backend for tracking
      try {
        // Extract x402 payment ID from transaction metadata if available
        const x402Metadata = (transactionData as Record<string, unknown>).x402_metadata as Record<string, unknown> | undefined;
        const x402PaymentId = x402Metadata?.x402_payment_id;
        
        await fetch('http://localhost:8000/store-transaction', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            tx_hash: txHash,
            amount: transactionData.amount || 'unknown',
            asset_id: 'RE-001',
            status: 'pending',
            x402_payment_id: x402PaymentId
          })
        });
        
        console.log('Stored transaction with x402 ID:', x402PaymentId);
      } catch (storeError) {
        console.log('Could not store transaction:', storeError);
      }

      const successMessage: Message = {
        sender: 'agent',
        text: `🚀 Transaction submitted to Polygon! Hash: ${txHash}\n⏳ Waiting for confirmation...\n💡 Transaction will use standard gas fees`,
        isTransaction: false
      };
      
      setMessages(prev => [...prev, successMessage]);

      // Wait for confirmation
      const receipt = await (txResponse as { wait: () => Promise<{ hash: string; blockNumber: number }> }).wait();
      
      // Update transaction status in backend
      try {
        await fetch('http://localhost:8000/update-transaction', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            tx_hash: receipt?.hash,
            status: 'confirmed'
          })
        });
      } catch (updateError) {
        console.log('Could not update transaction status:', updateError);
      }
      
      const confirmedMessage: Message = {
        sender: 'agent',
        text: `✅ Transaction confirmed on Polygon! \n🔗 Hash: ${receipt?.hash}\n📦 Block: ${receipt?.blockNumber}\n🎉 Your RWA investment is complete!\n🌐 View on explorer: ${POLYGON_CONFIG.blockExplorerUrl}/tx/${receipt?.hash}`,
        isTransaction: false
      };
      
      setMessages(prev => [...prev, confirmedMessage]);
    } catch (error: unknown) {
      console.error("Transaction failed:", error);
      let errorMsg = "❌ Transaction failed on Polygon";
      
      if (error && typeof error === 'object' && 'code' in error) {
        const errorCode = (error as { code: number }).code;
        if (errorCode === -32603) {
          errorMsg = "❌ Transaction rejected by Polygon network. Please check your gas fees.";
        } else if (errorCode === 4001) {
          errorMsg = POLYGON_ERRORS.USER_REJECTED;
        } else if (errorCode === -32000) {
          errorMsg = "❌ Insufficient funds. Please get test MATIC tokens from the faucet.";
        }
      }
      if (error && typeof error === 'object' && 'message' in error) {
        const errorMessage = (error as { message: string }).message;
        if (errorMessage.includes('insufficient funds')) {
          errorMsg = "❌ Insufficient funds. Please get test MATIC tokens from the Polygon faucet.";
        } else if (errorMessage.includes('network')) {
          errorMsg = POLYGON_ERRORS.WRONG_NETWORK;
        } else {
          errorMsg = `❌ Transaction failed: ${errorMessage}`;
        }
      }
      
      const errorMessage: Message = {
        sender: 'agent',
        text: errorMsg + `\n\n💡 Polygon Benefits:\n• Low gas fees\n• Fast transactions\n• Ethereum compatibility\n• Get test MATIC tokens from the faucet`,
        isTransaction: false
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  const handleSubmit = async (e: React.FormEvent, quickQuery?: string) => {
    e.preventDefault();
    const currentQuery = quickQuery || inputText;
    if (!currentQuery.trim()) return;

    // Add user message
    const userMessage: Message = {
      sender: 'user',
      text: currentQuery
    };
    setMessages(prev => [...prev, userMessage]);
    setInputText("");

    try {
      // Call backend API
      const response = await fetch(`${API_BASE}/ask-agent`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: currentQuery,
          chainId: wallet.provider ? Number((await wallet.provider.getNetwork()).chainId) : 80002,
          fromAddress: wallet.address,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      const data = await response.json();
      
      const agentMessage: Message = {
        sender: 'agent',
        text: data.response,
        isTransaction: data.is_transaction,
        transactionData: data.transaction_data
      };

      setMessages(prev => [...prev, agentMessage]);
    } catch {
      const errorMessage: Message = {
        sender: 'agent',
        text: "Sorry, I couldn't connect to the backend. Please make sure the server is running.",
        isTransaction: false
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  const quickActions = [
    { title: "Show Investments", query: "show investments", icon: "📊" },
    { title: "Investment Options", query: "show me investment options", icon: "💼" },
    { title: "Invest 100 USDC", query: "invest 100 USDC in TCB-001", icon: "💰" },
    { title: "Portfolio Status", query: "show my portfolio", icon: "📈" }
  ];

  return (
    <div className="h-screen flex bg-gray-50 overflow-hidden">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-16'} bg-gray-900 text-white transition-all duration-300 flex flex-col flex-shrink-0`}>
        {/* Logo */}
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-lg flex items-center justify-center text-white font-bold">
              R
            </div>
            {sidebarOpen && <span className="font-semibold">RWA-GPT</span>}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <div className="space-y-2">
            <button 
              className="w-full flex items-center gap-3 p-3 rounded-lg bg-blue-600 text-white"
              onClick={() => setMessages([])}
            >
              <span>💬</span>
              {sidebarOpen && <span>AI Chat Helper</span>}
            </button>
            
            {sidebarOpen && (
              <div className="mt-6">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Quick Actions</h3>
                <div className="space-y-1">
                  {quickActions.map((action, index) => (
                    <button
                      key={index}
                      onClick={(e) => {
                        setInputText(action.query);
                        handleSubmit(e, action.query);
                      }}
                      className="w-full flex items-center gap-3 p-2 rounded text-sm text-gray-300 hover:bg-gray-800 transition-colors"
                    >
                      <span>{action.icon}</span>
                      <span>{action.title}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </nav>

        {/* Wallet Status */}
        <div className="p-4 border-t border-gray-700">
          {wallet.address ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${wallet.isConnectedToPolygon ? 'bg-green-400' : 'bg-yellow-400'}`}></div>
                {sidebarOpen && (
                  <div className="text-xs text-gray-400">
                    <div>{formatAddress(wallet.address)}</div>
                    <div className="text-xs text-gray-500">
                      {wallet.isConnectedToPolygon ? 'Polygon Amoy' : 'Other Network'}
                    </div>
                    <div className="text-xs text-gray-500">
                      {formatBalance(wallet.balance)}
                    </div>
                  </div>
                )}
              </div>
              {!wallet.isConnectedToPolygon && sidebarOpen && (
                <div className="text-xs text-yellow-400">
                  Switch to Polygon
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <button
                onClick={connectWallet}
                disabled={isConnecting}
                className={`${sidebarOpen ? 'w-full' : 'w-8 h-8'} bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium ${sidebarOpen ? 'py-2' : 'flex items-center justify-center'}`}
              >
                {isConnecting ? "..." : sidebarOpen ? "👻 Connect Phantom" : "🔗"}
              </button>
              
              {sidebarOpen && (
                <button
                  onClick={() => {
                    console.log('🔍 Wallet Debug Info:');
                    console.log('window.ethereum:', window.ethereum);
                    console.log('window.ethereum.providers:', window.ethereum?.providers);
                    console.log('window.ethereum.isMetaMask:', window.ethereum?.isMetaMask);
                    console.log('window.ethereum.isPhantom:', window.ethereum?.isPhantom);
                    console.log('window.ethereum.isBraveWallet:', window.ethereum?.isBraveWallet);
                    console.log('window.solana:', window.solana);
                    
                    const debugMessage: Message = {
                      sender: 'agent',
                      text: `🔍 **Wallet Debug Info**\n\nCheck the browser console (F12) for detailed wallet detection information.\n\n**Quick Check:**\n• Phantom in Ethereum mode: ${window.ethereum?.isPhantom ? '✅' : '❌'}\n• MetaMask: ${window.ethereum?.isMetaMask ? '✅' : '❌'}\n• Multiple providers: ${window.ethereum?.providers?.length || 0}\n\n**If Phantom is not detected:**\n1. Make sure Phantom is installed\n2. Switch Phantom to Ethereum mode\n3. Refresh the page and try again`,
                      isTransaction: false
                    };
                    setMessages(prev => [...prev, debugMessage]);
                  }}
                  className="w-full py-1 px-2 bg-gray-600 hover:bg-gray-700 text-white rounded text-xs"
                >
                  🔍 Debug Wallets
                </button>
              )}
            </div>
          )}
        </div>

        {/* Toggle Sidebar */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="absolute top-4 -right-3 w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded-full flex items-center justify-center text-white text-xs"
        >
          {sidebarOpen ? '←' : '→'}
        </button>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-gray-900">AI Chat Helper</h1>
              <p className="text-sm text-gray-500">Real-World Asset conversational agent</p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-sm text-gray-500">
                {messages.length}/50
              </div>
              <button className="p-2 hover:bg-gray-100 rounded-lg">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
            </div>
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col bg-gradient-to-br from-slate-50 via-gray-50 to-blue-50 min-h-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 flex flex-col">
            {messages.length === 0 ? (
              <div className="max-w-2xl mx-auto text-center py-12">
                <div className="w-16 h-16 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4">
                  R
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Welcome to RWA-GPT</h2>
                <p className="text-gray-600 mb-4">Your AI-powered Real-World Asset conversational agent. Ask me about investments, show data, or request swaps.</p>
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-8 text-sm">
                  <div className="font-medium text-blue-900 mb-2">🚀 Polygon Integration Active</div>
                  <div className="text-blue-700">
                    • System uses <strong>Polygon Amoy Testnet</strong><br/>
                    • <strong>Low gas fees</strong> - cost-effective transactions!<br/>
                    • <strong>Phantom preferred</strong> - Connect with Phantom 👻<br/>
                    • Ethereum compatibility enabled<br/>
                    • Fast and reliable transactions
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-4 max-w-md mx-auto">
                  {quickActions.map((action, index) => (
                    <button
                      key={index}
                      onClick={(e) => {
                        setInputText(action.query);
                        handleSubmit(e, action.query);
                      }}
                      className="p-4 bg-white rounded-xl border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all group"
                    >
                      <div className="text-2xl mb-2 group-hover:scale-110 transition-transform">{action.icon}</div>
                      <div className="text-sm font-medium text-gray-900">{action.title}</div>
                    </button>
                  ))}
                </div>
        </div>
            ) : (
              <div className="flex-1 flex flex-col justify-end">
                <div className="max-w-4xl mx-auto w-full space-y-6 pb-4">
                  {messages.map((message, index) => (
                    <div
                      key={index}
                      className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div className={`max-w-2xl ${message.sender === 'user' ? 'order-2' : 'order-1'}`}>
                        <div
                          className={`px-6 py-4 rounded-2xl ${
                            message.sender === 'user'
                              ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white'
                              : 'bg-white border border-gray-200 text-gray-900 shadow-sm'
                          }`}
                        >
                          <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {message.text}
                            </ReactMarkdown>
                          </div>
                          {message.isTransaction && message.transactionData && (
                            <div className="mt-4 pt-4 border-t border-gray-200">
                              <button
                                onClick={() => message.transactionData && executeSwap(message.transactionData)}
                                className="w-full px-4 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                              >
                                <span>⚡</span>
                                Execute Swap
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className={`flex items-end ${message.sender === 'user' ? 'order-1 mr-3' : 'order-2 ml-3'}`}>
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                          message.sender === 'user' 
                            ? 'bg-gray-300 text-gray-700' 
                            : 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white'
                        }`}>
                          {message.sender === 'user' ? 'U' : 'R'}
                        </div>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              </div>
            )}
          </div>

          {/* Input Area */}
          <div className="flex-shrink-0 p-6 bg-white border-t border-gray-200">
            <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
              <div className="flex gap-4">
                <div className="flex-1 relative">
                  <input
                    type="text"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Ask about RWA investments..."
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-black"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!inputText.trim()}
                  className="px-6 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
                >
                  Send
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}