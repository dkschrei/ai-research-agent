# src/hello_agent.py
"""
Simple hello world agent to test Ollama integration
This validates your M4 Pro setup before building the full system
"""

import asyncio
import ollama
from typing import Dict, Any
import time
import json


class HelloAgent:
    """Simple agent to test local model integration"""
    
    def __init__(self, model_name: str = "llama3.1:8b"):
        self.model_name = model_name
        self.client = ollama.Client()
        
    def test_connection(self) -> bool:
        """Test if Ollama is running and model is available"""
        try:
            models = self.client.list()
            available_models = [model['name'] for model in models['models']]
            
            if self.model_name not in available_models:
                print(f"Model {self.model_name} not found. Available models: {available_models}")
                return False
                
            print(f"✅ Connected to Ollama. Model {self.model_name} is available.")
            return True
            
        except Exception as e:
            print(f"❌ Failed to connect to Ollama: {e}")
            return False
    
    def simple_chat(self, message: str) -> Dict[str, Any]:
        """Send a simple message to the model"""
        try:
            start_time = time.time()
            
            response = self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        'role': 'user',
                        'content': message
                    }
                ]
            )
            
            end_time = time.time()
            
            return {
                'success': True,
                'response': response['message']['content'],
                'response_time': end_time - start_time,
                'model': self.model_name
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'model': self.model_name
            }
    
    def test_agent_capabilities(self) -> Dict[str, Any]:
        """Test different agent capabilities"""
        tests = [
            {
                'name': 'Basic Reasoning',
                'prompt': 'What is 15 * 24? Explain your reasoning step by step.'
            },
            {
                'name': 'Document Analysis',
                'prompt': 'You are a document analyst. Analyze this text and extract key themes: "The global shift towards renewable energy is accelerating, driven by falling costs and climate concerns. Solar and wind power are now the cheapest sources of electricity in many regions."'
            },
            {
                'name': 'Research Planning', 
                'prompt': 'As a research assistant, create a brief research plan for investigating "the impact of AI on small business productivity". Include 3 key questions to explore.'
            }
        ]
        
        results = {}
        
        for test in tests:
            print(f"\nTesting: {test['name']}")
            print(f"Prompt: {test['prompt'][:100]}...")
            
            result = self.simple_chat(test['prompt'])
            
            if result['success']:
                print(f"✅ Response received in {result['response_time']:.2f}s")
                print(f"Response preview: {result['response'][:200]}...")
            else:
                print(f"❌ Test failed: {result['error']}")
            
            results[test['name']] = result
            
        return results


def benchmark_models(available_models: list) -> Dict[str, Dict]:
    """Benchmark different models if available"""
    benchmark_prompt = "Explain the concept of artificial intelligence in exactly 50 words."
    results = {}
    
    for model in available_models:
        if any(size in model for size in ['7b', '8b', '9b', '13b', '14b']):  # Test smaller models only
            print(f"\nBenchmarking {model}...")
            agent = HelloAgent(model)
            
            if agent.test_connection():
                result = agent.simple_chat(benchmark_prompt)
                results[model] = result
                
                if result['success']:
                    print(f"✅ {model}: {result['response_time']:.2f}s")
                else:
                    print(f"❌ {model}: Failed")
    
    return results


async def main():
    """Main test function"""
    print("🚀 Research Agent - Hello World Test")
    print("=" * 50)
    
    # Test basic connection
    agent = HelloAgent()
    
    if not agent.test_connection():
        print("\n❌ Setup incomplete. Please:")
        print("1. Start Ollama: ollama serve")
        print("2. Pull the model: ollama pull llama3.1:8b")
        return
    
    # Test basic chat
    print("\n📝 Testing basic chat...")
    result = agent.simple_chat("Hello! Please introduce yourself as a research assistant.")
    
    if result['success']:
        print(f"✅ Chat test successful! Response time: {result['response_time']:.2f}s")
        print(f"Response: {result['response']}")
    else:
        print(f"❌ Chat test failed: {result['error']}")
        return
    
    # Test agent capabilities
    print("\n🧪 Testing agent capabilities...")
    capabilities = agent.test_agent_capabilities()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 30)
    successful_tests = sum(1 for r in capabilities.values() if r['success'])
    total_tests = len(capabilities)
    
    print(f"Successful tests: {successful_tests}/{total_tests}")
    
    if successful_tests == total_tests:
        print("🎉 All tests passed! Your setup is ready for development.")
    else:
        print("⚠️  Some tests failed. Check your Ollama setup.")
    
    # Optional: Benchmark available models
    print("\n🏃 Available for model benchmarking...")
    try:
        client = ollama.Client()
        models = client.list()
        model_names = [model['name'] for model in models['models']]
        print(f"Found models: {model_names}")
        
        if len(model_names) > 1:
            choice = input("\nRun model benchmark? (y/n): ").lower().strip()
            if choice == 'y':
                benchmark_results = benchmark_models(model_names)
                
                print("\n📈 Benchmark Results:")
                for model, result in benchmark_results.items():
                    if result['success']:
                        print(f"{model}: {result['response_time']:.2f}s")
                    else:
                        print(f"{model}: Failed")
    
    except Exception as e:
        print(f"Benchmark error: {e}")
    
    print("\n✅ Hello World Agent test complete!")


if __name__ == "__main__":
    asyncio.run(main())
