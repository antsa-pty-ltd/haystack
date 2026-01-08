#!/bin/bash
# Setup script to install git hooks that enforce workflow policies

echo "🔧 Setting up git hooks..."

# Install pre-push hook
if [ -f .git/hooks/pre-push ]; then
    echo "⚠️  Pre-push hook already exists. Backing up..."
    mv .git/hooks/pre-push .git/hooks/pre-push.backup
fi

cat > .git/hooks/pre-push << 'HOOK_EOF'
#!/bin/bash

# Pre-push hook to prevent direct pushes to master/main
# This hook prevents pushing directly to master and suggests using PRs through develop

protected_branches=("master" "main")
current_branch=$(git symbolic-ref HEAD | sed -e 's,.*/\(.*\),\1,')

for protected in "${protected_branches[@]}"; do
    if [ "$protected" == "$current_branch" ]; then
        echo "❌ BLOCKED: Direct pushes to '$protected' are not allowed!"
        echo ""
        echo "🔄 Please use the following workflow:"
        echo "   1. Create/switch to a feature branch: git checkout -b feature/your-feature"
        echo "   2. Make your changes and commit them"
        echo "   3. Push your branch: git push origin feature/your-feature"
        echo "   4. Create a Pull Request to 'develop' branch"
        echo "   5. After approval, merge develop to master via PR"
        echo ""
        echo "ℹ️  If you need to bypass this (not recommended): git push --no-verify"
        exit 1
    fi
done

exit 0
HOOK_EOF

chmod +x .git/hooks/pre-push

echo "✅ Git hooks installed successfully!"
echo ""
echo "📋 Protected branches: master, main"
echo "🔒 Direct pushes to these branches are now blocked locally"
echo ""
echo "To remove these hooks: rm .git/hooks/pre-push"
