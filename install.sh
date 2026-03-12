#!/bin/bash
# Bonfires CLI installer — creates an isolated venv and a global wrapper.
set -e

VENV_DIR="${HOME}/.local/share/bonfire-venv"
BIN_DIR="${HOME}/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Bonfires CLI..."

# Create venv
echo "  Creating venv at ${VENV_DIR}..."
python3 -m venv "$VENV_DIR"

# Install bonfires into the venv
echo "  Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR"

# Create wrapper script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/bonfire" <<WRAPPER
#!/bin/bash
exec "$VENV_DIR/bin/bonfire" "\$@"
WRAPPER
chmod +x "$BIN_DIR/bonfire"

# Check PATH
if ! echo "$PATH" | tr ':' '\n' | grep -q "^${BIN_DIR}$"; then
    echo ""
    echo "  Warning: ${BIN_DIR} is not on your PATH."
    echo "  Add this to your shell profile (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo ""
echo "Done! Run 'bonfire init' to connect to the Bonfires API."
