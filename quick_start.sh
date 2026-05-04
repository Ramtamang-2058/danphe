#!/bin/bash
# quick_start.sh — Get context-aware social automation running in 5 minutes

echo "🚀 Context-Aware Social Media Automation - Quick Start"
echo "======================================================"
echo ""

# Step 1: Install dependencies
echo "📦 Step 1: Installing dependencies..."
pip install -r social_requirements.txt
echo "✅ Dependencies installed"
echo ""

# Step 2: Setup environment
echo "🔑 Step 2: Setting up environment..."
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# Add your API keys here (get from NVIDIA/Gemini)
NVIDIA_API_KEY=your_nvidia_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
DANPHE_MODEL=long
DANPHE_DEBUG=0
EOF
    echo "ℹ️  Created .env file - add your API keys!"
    echo "💡 Get NVIDIA key: https://build.nvidia.com"
    echo "💡 Get Gemini key: https://aistudio.google.com"
else
    echo "✅ .env file already exists"
fi
echo ""

# Step 3: Show demo
echo "🎭 Step 3: Running demo..."
python3 demo_social_automation.py --demo context
echo ""

# Step 4: First real usage
echo "🌐 Step 4: Ready to use!"
echo ""
echo "📱 To read Instagram DM:"
echo "   python instra-automate/social_media.py instagram @username"
echo ""
echo "📢 To auto-reply on Instagram:"
echo "   python instra-automate/social_media.py instagram @username --auto-reply"
echo ""
echo "💬 With custom personality:"
echo "   python instra-automate/social_media.py instagram @username \\"
echo "     --auto-reply --personality 'casual and funny'"
echo ""
echo "✨ Check SOCIAL_MEDIA_README.md for full documentation"
echo ""
echo "✅ All set! Start automating! 🤖"
