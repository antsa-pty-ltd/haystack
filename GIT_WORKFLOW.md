# Git Workflow & Branch Protection

## 🔒 Branch Protection Setup

Git hooks have been installed in all repositories to prevent direct pushes to `master` branch. All changes **must** go through Pull Requests via the `develop` branch.

## 📋 Repositories Protected

- ✅ `web`
- ✅ `admin` 
- ✅ `haystack-service`
- ✅ `mobile`
- ✅ `api`

## 🔄 Required Workflow

### For New Features/Changes:

1. **Create a feature branch from develop:**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and commit:**
   ```bash
   git add .
   git commit -m "feat: your descriptive commit message"
   ```

3. **Push your feature branch:**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request:**
   - Go to GitHub
   - Create PR from `feature/your-feature-name` → `develop`
   - Get code review and approval
   - Merge to `develop`

5. **Release to Production:**
   - Create PR from `develop` → `master`
   - Get approval and merge
   - This triggers production deployment

## 🚫 What's Blocked

- ❌ Direct pushes to `master` branch
- ❌ Direct pushes to `main` branch (if used)
- ❌ Force pushes to protected branches

## ⚙️ Setup for New Developers

When you clone a repository, run the setup script to install the hooks:

```bash
cd /path/to/repo
./setup-git-hooks.sh
```

This will install client-side git hooks that enforce the workflow.

## 🔓 Bypass (Emergency Only)

In exceptional circumstances, you can bypass the hook with:
```bash
git push --no-verify
```

**⚠️ WARNING:** Only use this if you have explicit permission and understand the risks!

## 📝 Commit Message Convention

Use conventional commit format:
- `feat:` - New feature
- `fix:` - Bug fix  
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding/updating tests
- `chore:` - Maintenance tasks

Example:
```bash
git commit -m "feat: add user authentication system"
git commit -m "fix: resolve timeout issue in document generation"
```

## 🔍 Branch Naming Convention

- **Feature branches:** `feature/short-description`
- **Bug fixes:** `fix/issue-description`
- **Hotfixes:** `hotfix/critical-issue`
- **Releases:** `release/v1.2.3`

Examples:
```bash
feature/ai-document-generation
fix/timeout-error
hotfix/security-patch
release/v2.0.0
```

## 🎯 Important Notes

### Limitations of Client-Side Hooks:

1. **Not enforced server-side** - Hooks only work on machines where they're installed
2. **Can be bypassed** - Using `--no-verify` flag bypasses hooks
3. **Need manual installation** - Each developer must run `setup-git-hooks.sh`

### For True Server-Side Protection:

To enforce these rules server-side (recommended for production), the organization needs:
- **GitHub Team Plan** ($4/user/month)
- Provides true branch protection rules
- Cannot be bypassed by developers
- Enforced at the GitHub server level

### Current Setup:

- ✅ Client-side hooks installed (you and your machine)
- ❌ Server-side protection (requires paid GitHub plan)
- ✅ Setup scripts available for team members
- ⚠️ Relies on team discipline and hook installation

## 🚀 Testing the Protection

Try to push directly to master (it should fail):

```bash
git checkout master
git commit --allow-empty -m "test commit"
git push origin master
# Should see: ❌ BLOCKED: Direct pushes to 'master' are not allowed!
```

## 📞 Questions?

If you have questions about the workflow or need help:
1. Check this document first
2. Ask in the team chat
3. Contact the repository maintainers

## 🔄 Updating Hooks

If the hooks are updated, team members need to re-run:
```bash
./setup-git-hooks.sh
```

---

**Last Updated:** $(date)
**Protected Since:** $(date)

