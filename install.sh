#!/bin/bash
# Bonfire CLI installer — creates an isolated venv and a global wrapper script.
set -e

VENV_DIR="${HOME}/.local/share/bonfire-venv"
BIN_DIR="${HOME}/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Bonfire CLI..."

# Create venv
echo "  Creating venv at ${VENV_DIR}..."
python3 -m venv "$VENV_DIR"

# Install bonfire-cli into the venv
echo "  Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR"

# Create wrapper script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/bonfire" <<WRAPPER
#!/bin/bash
exec "$VENV_DIR/bin/bonfire" "\$@"
WRAPPER
chmod +x "$BIN_DIR/bonfire"

# Check if ~/.local/bin is on PATH
if ! echo "$PATH" | tr ':' '\n' | grep -q "^${BIN_DIR}$"; then
    echo ""
    echo "  Warning: ${BIN_DIR} is not on your PATH."
    echo "  Add this to your shell profile (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# Remind about .env
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo ""
    echo "  Setup: copy .env.example to .env and fill in your credentials:"
    echo ""
    echo "    cp .env.example .env"
    echo ""
fi

echo "Done! Run 'bonfire --help' to get started."
