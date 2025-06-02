#!/bin/bash
# setup_m4_pro.sh - Initial setup for Research Agent on M4 Pro
# Run this from /Users/danaschreiber/documents/AI-Projects/research-agent/

set -e  # Exit on any error

echo "🚀 Setting up Research Agent on M4 Pro..."
echo "📁 Working directory: $(pwd)"
echo "=" * 50

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This script is designed for macOS. Please run on your M4 Pro."
    exit 1
fi

# Check if we're on Apple Silicon
if [[ $(uname -m) != "arm64" ]]; then
    echo "❌ This script is optimized for Apple Silicon (M4 Pro)."
    exit 1
fi

echo "✅ Detected macOS on Apple Silicon"

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "📦 Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "✅ Homebrew is installed"
fi

# Install Python 3.11 if not present
if ! command -v python3.11 &> /dev/null; then
    echo "🐍 Installing Python 3.11..."
    brew install python@3.11
else
    echo "✅ Python 3.11 is installed"
fi

# Check for Ollama
if ! command -v ollama &> /dev/null; then
    echo "🤖 Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    
    # Start Ollama service
    echo "🚀 Starting Ollama..."
    ollama serve &
    sleep 5
else
    echo "✅ Ollama is installed"
    
    # Check if Ollama is running
    if ! pgrep -x "ollama" > /dev/null; then
        echo "🚀 Starting Ollama..."
        ollama serve &
        sleep 5
    fi
fi

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3.11 -m venv research_agent_env

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source research_agent_env/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install basic requirements
echo "📦 Installing Python packages..."
pip install -r requirements.txt

# Create .env file from template
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file..."
    cp .env.template .env
    echo "✅ Created .env file. You can customize it later."
else
    echo "✅ .env file already exists"
fi

# Download essential AI models
echo "🧠 Downloading essential AI models..."
echo "This may take a few minutes depending on your internet connection..."

# Download models in order of priority
models=("llama3.1:8b" "gemma2:9b" "qwen2.5:7b")

for model in "${models[@]}"; do
    echo "📥 Downloading $model..."
    if ollama pull $model; then
        echo "✅ Successfully downloaded $model"
    else
        echo "⚠️  Failed to download $model. You can try again later with: ollama pull $model"
    fi
done

# Test the setup
echo "🧪 Testing setup..."
python3.11 src/hello_agent.py

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Activate virtual environment: source research_agent_env/bin/activate"
echo "2. Test the hello agent: python src/hello_agent.py"
echo "3. Start developing your research agent!"
echo ""
echo "Available models:"
ollama list
echo ""
echo "Happy coding! 🚀"
