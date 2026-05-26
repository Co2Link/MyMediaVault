# Fix ownership of mounted volumes to vscode user (only if not already owned)
CURRENT_USER=$(whoami)
for path in "$HOME/.claude" "$HOME/.codex" "$HOME/.gemini"; do
    if [ -d "$path" ] && [ "$(stat -c %U "$path")" != "$CURRENT_USER" ]; then
        sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$path"
    fi
done

# Install external runtime tools used by torrent-preview.
if ! command -v ffmpeg >/dev/null 2>&1; then
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg
    sudo rm -rf /var/lib/apt/lists/*
fi

# Install OpenSpec CLI globally
npm install -g @fission-ai/openspec@latest

# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install OpenAI Codex CLI gobally
npm i -g @openai/codex

# Install the Playwright browser revision used by the e2e package.
npm --prefix apps/e2e ci
npm --prefix apps/e2e exec -- playwright install chromium --with-deps
