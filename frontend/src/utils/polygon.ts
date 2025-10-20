import { ethers } from 'ethers';

// Type definitions for wallet providers
interface WalletProvider {
  request?: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  send?: (method: string, params?: unknown[]) => Promise<unknown>;
  isPhantom?: boolean;
  isMetaMask?: boolean;
  isBraveWallet?: boolean;
  isCoinbaseWallet?: boolean;
  providers?: WalletProvider[];
  constructor?: {
    name?: string;
  };
}

interface RpcError extends Error {
  code?: number;
  message: string;
}

// Polygon Amoy Testnet Configuration
export const POLYGON_CONFIG = {
  chainId: 80002, // Polygon Amoy Testnet
  chainName: 'Polygon Amoy Testnet',
  rpcUrl: 'https://rpc-amoy.polygon.technology/',
  blockExplorerUrl: 'https://amoy.polygonscan.com',
  nativeCurrency: {
    name: 'MATIC',
    symbol: 'MATIC',
    decimals: 18,
  },
  // Gas settings for Polygon
  gasless: false,
  metaTransactions: false,
};

// Polygon Mainnet Configuration (for future use)
export const POLYGON_MAINNET_CONFIG = {
  chainId: 137,
  chainName: 'Polygon Mainnet',
  rpcUrl: 'https://polygon-rpc.com/',
  blockExplorerUrl: 'https://polygonscan.com',
  nativeCurrency: {
    name: 'MATIC',
    symbol: 'MATIC',
    decimals: 18,
  },
  gasless: false,
  metaTransactions: false,
};

// Polygon Network Details for Wallet Connection
export const POLYGON_NETWORK = {
  chainId: `0x${POLYGON_CONFIG.chainId.toString(16)}`, // 0x13882
  chainName: POLYGON_CONFIG.chainName,
  nativeCurrency: POLYGON_CONFIG.nativeCurrency,
  rpcUrls: [POLYGON_CONFIG.rpcUrl],
  blockExplorerUrls: [POLYGON_CONFIG.blockExplorerUrl],
};

// Polygon Provider Class
export class PolygonProvider {
  private provider: ethers.BrowserProvider | null = null;
  private signer: ethers.JsonRpcSigner | null = null;
  private address: string | null = null;

  constructor() {
    this.provider = null;
    this.signer = null;
    this.address = null;
  }

  // Initialize Polygon connection with Phantom (Ethereum mode)
  async connect(): Promise<{
    address: string;
    provider: ethers.BrowserProvider;
    signer: ethers.JsonRpcSigner;
  }> {
    console.log('🔍 Detecting wallets...');
    
    // Check for Ethereum provider (Phantom, MetaMask, etc.)
    if (typeof window.ethereum === 'undefined') {
      throw new Error('❌ No Ethereum wallet found!\n\n✅ Please install Phantom:\n→ https://phantom.app\n\nOr install MetaMask as fallback:\n→ https://metamask.io');
    }

    let ethereum = window.ethereum;
    let selectedWallet = 'unknown';

    // Debug: Log all available providers
    console.log('🔍 Available providers:', window.ethereum.providers);
    console.log('🔍 Primary provider flags:', {
      isMetaMask: window.ethereum.isMetaMask,
      isPhantom: window.ethereum.isPhantom,
      isBraveWallet: window.ethereum.isBraveWallet,
      isCoinbaseWallet: window.ethereum.isCoinbaseWallet
    });

    // If multiple wallets are installed, aggressively prefer Phantom
    if (window.ethereum.providers && Array.isArray(window.ethereum.providers)) {
      console.log('🔍 Multiple wallets detected, searching for Phantom...');
      
      // Look for Phantom with multiple detection methods
      const phantomProvider = window.ethereum.providers.find((provider: WalletProvider) => {
        console.log('🔍 Checking provider:', {
          isPhantom: provider.isPhantom,
          isBraveWallet: provider.isBraveWallet,
          constructor: provider.constructor?.name
        });
        return provider.isPhantom || provider.isBraveWallet || 
               provider.constructor?.name?.toLowerCase().includes('phantom');
      }) as WalletProvider | undefined;
      
      if (phantomProvider) {
        ethereum = phantomProvider as typeof window.ethereum;
        selectedWallet = 'phantom';
        console.log('✅ Phantom detected and selected from multiple providers');
      } else {
        // Only fallback to MetaMask if Phantom is truly not available
        const metamaskProvider = window.ethereum.providers.find(
          (provider: WalletProvider) => provider.isMetaMask
        ) as WalletProvider | undefined;
        
        if (metamaskProvider) {
          ethereum = metamaskProvider as typeof window.ethereum;
          selectedWallet = 'metamask';
          console.log('⚠️ MetaMask detected as fallback (Phantom not found)');
        } else {
          throw new Error('⚠️ Multiple wallets detected but Phantom not found!\n\n✅ Please install Phantom:\n→ https://phantom.app\n\nOr install MetaMask:\n→ https://metamask.io');
        }
      }
    } else {
      // Single wallet provider - check if it's Phantom
      if (window.ethereum.isPhantom || window.ethereum.isBraveWallet) {
        selectedWallet = 'phantom';
        console.log('✅ Phantom wallet detected (single provider)');
      } else if (window.ethereum.isMetaMask) {
        selectedWallet = 'metamask';
        console.log('⚠️ MetaMask detected (single provider) - Phantom preferred');
        // For single MetaMask, we should still encourage Phantom
        throw new Error('⚠️ MetaMask detected!\n\nFor the best experience, please install Phantom wallet:\n\n✅ Install Phantom:\n→ https://phantom.app\n\nPhantom provides a better user experience with modern UI and multi-chain support.');
      } else {
        const walletName = window.ethereum.isCoinbaseWallet ? 'Coinbase Wallet' : 
                          'Unknown wallet';
        
        throw new Error(`⚠️ ${walletName} detected!\n\nPhantom is preferred for best compatibility.\n\n✅ Please install Phantom:\n→ https://phantom.app\n\nOr temporarily disable ${walletName}.`);
      }
    }

    console.log(`🎯 Selected wallet: ${selectedWallet}`);

    try {
      console.log(`🔗 Connecting to ${selectedWallet === 'phantom' ? 'Phantom' : 'wallet'}...`);
      
      // Ensure ethereum is defined
      if (!ethereum) {
        throw new Error('Ethereum provider not found');
      }
      
      // Request account access
      const accounts = await ethereum.request({ 
        method: 'eth_requestAccounts' 
      }) as string[];
      
      if (!accounts || accounts.length === 0) {
        throw new Error('No accounts found. Please unlock Phantom.');
      }
      
      console.log('✅ Phantom connected:', accounts[0]);
      
      // Try to switch to Polygon network
      try {
        console.log('🔄 Switching to Polygon Amoy network...');
        await ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: POLYGON_NETWORK.chainId }],
        });
        console.log('✅ Switched to Polygon Amoy');
      } catch (switchError) {
        const error = switchError as RpcError;
        // If switch fails, try to add the network
        if (error.code === 4902 || error.code === -32603) {
          console.log('➕ Adding Polygon Amoy network to Phantom...');
          try {
            await ethereum.request({
              method: 'wallet_addEthereumChain',
              params: [POLYGON_NETWORK],
            });
            console.log('✅ Polygon Amoy network added');
          } catch (addError) {
            const addErrorObj = addError as RpcError;
            throw new Error(`Failed to add Polygon Amoy network: ${addErrorObj.message}`);
          }
        } else if (error.code === 4001) {
          throw new Error('Connection rejected. Please approve the network switch in Phantom.');
        } else {
          throw switchError;
        }
      }

      // Create provider and get signer using the selected ethereum provider
      this.provider = new ethers.BrowserProvider(ethereum);
      this.signer = await this.provider.getSigner();
      this.address = accounts[0];
      
      console.log('🎉 Successfully connected to Polygon via Phantom!');

      return {
        address: this.address,
        provider: this.provider,
        signer: this.signer,
      };
    } catch (error) {
      const err = error as RpcError;
      console.error('❌ Polygon connection failed:', error);
      
      // Provide user-friendly error messages
      if (err.message.includes('User rejected')) {
        throw new Error('Connection rejected. Please approve the connection in Phantom.');
      } else if (err.message.includes('Already processing')) {
        throw new Error('Phantom is busy. Please check Phantom and try again.');
      }
      
      throw error;
    }
  }

  // Get current network
  async getNetwork() {
    if (!this.provider) {
      throw new Error('Provider not initialized');
    }
    return await this.provider.getNetwork();
  }

  // Check if connected to Polygon
  async isConnectedToPolygon(): Promise<boolean> {
    try {
      const network = await this.getNetwork();
      return Number(network.chainId) === POLYGON_CONFIG.chainId;
    } catch {
      return false;
    }
  }

  // Execute transaction on Polygon
  async executeTransaction(transaction: {
    to: string;
    value?: string;
    data?: string;
    gasLimit?: string;
  }) {
    if (!this.signer) {
      throw new Error('Wallet not connected');
    }

    // Check if we're on Polygon
    const isOnPolygon = await this.isConnectedToPolygon();
    if (!isOnPolygon) {
      throw new Error('Please switch to Polygon Amoy network');
    }

    try {
      // For Polygon, we use standard gas fees
      const txResponse = await this.signer.sendTransaction({
        to: transaction.to,
        value: transaction.value || '0x0',
        data: transaction.data || '0x',
        gasLimit: transaction.gasLimit || '0x5208',
      });

      return txResponse;
    } catch (error) {
      console.error('Transaction failed:', error);
      throw error;
    }
  }

  // Get account balance
  async getBalance(): Promise<string> {
    if (!this.provider || !this.address) {
      throw new Error('Provider not initialized');
    }
    
    const balance = await this.provider.getBalance(this.address);
    return ethers.formatEther(balance);
  }

  // Disconnect wallet
  disconnect() {
    this.provider = null;
    this.signer = null;
    this.address = null;
  }

  // Get current address
  getAddress(): string | null {
    return this.address;
  }

  // Get current provider
  getProvider(): ethers.BrowserProvider | null {
    return this.provider;
  }

  // Get current signer
  getSigner(): ethers.JsonRpcSigner | null {
    return this.signer;
  }
}

// Export singleton instance
export const polygonProvider = new PolygonProvider();

// Utility function to force Phantom usage
export const forcePhantomUsage = () => {
  // Clear any cached wallet connections
  if (typeof window !== 'undefined') {
    // Force detection of Phantom
    const phantomProvider = window.ethereum?.providers?.find((provider: WalletProvider) => 
      provider.isPhantom || provider.isBraveWallet
    );
    
    if (phantomProvider) {
      // Temporarily override window.ethereum to force Phantom
      const originalEthereum = window.ethereum;
      window.ethereum = phantomProvider as typeof window.ethereum;
      
      // Restore after a short delay
      setTimeout(() => {
        window.ethereum = originalEthereum;
      }, 1000);
      
      console.log('🔧 Forced Phantom usage');
      return true;
    }
  }
  return false;
};

// Utility functions
export const formatAddress = (address: string): string => {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
};

export const formatBalance = (balance: string): string => {
  const num = parseFloat(balance);
  if (num < 0.001) return '< 0.001 MATIC';
  return `${num.toFixed(4)} MATIC`;
};

// Polygon specific error messages
export const POLYGON_ERRORS = {
  NETWORK_NOT_FOUND: 'Polygon Amoy network not found. Please add it to Phantom.',
  USER_REJECTED: 'Transaction rejected by user',
  INSUFFICIENT_FUNDS: 'Insufficient funds for gas fees',
  WRONG_NETWORK: 'Please switch to Polygon Amoy network',
  WALLET_NOT_CONNECTED: 'Please connect Phantom wallet first',
};
