# GitHub Repository Configuration Guide

This guide walks through the essential GitHub repository settings for secure CI/CD workflows, branch protections, and access control for the RDWC-v4 project.

## 1. Repository Secrets Configuration

GitHub Actions workflows (especially `deploy-pi.yml`) require sensitive credentials stored as encrypted secrets.

### Navigate to Secrets
1. Go to your repository on GitHub: `https://github.com/collinerasmus/RDWC-v4`
2. Click **Settings** (top menu)
3. In the left sidebar, expand **Secrets and variables** → click **Actions**

### Required Secrets for Deployment

Click **New repository secret** and add each of the following:

#### `SSH_PRIVATE_KEY`
- **Description**: Private SSH key for passwordless authentication to your Raspberry Pi
- **Value**: Your private SSH key content (entire file including `-----BEGIN OPENSSH PRIVATE KEY-----` header)
- **How to generate** (if needed):
  ```bash
  # On your dev machine
  ssh-keygen -t ed25519 -C "github-actions@rdwc-deploy"
  # Copy public key to Pi
  ssh-copy-id pi@192.168.88.49
  # Copy private key content to GitHub secret
  cat ~/.ssh/id_ed25519
  ```

#### `PI_HOST`
- **Description**: Hostname or IP address of your Raspberry Pi
- **Value**: `192.168.88.49` (or your Pi's actual IP/hostname)

#### `PI_USER`
- **Description**: SSH username for deployment
- **Value**: `pi` (or your actual Pi username)

### Verification
After adding secrets:
- Secrets will show as `***` (masked) in the UI
- Workflow runs will use these secrets automatically
- Check workflow run logs to verify SSH connection succeeds

---

## 2. Collaborators & Access Control

Protect your repository from unauthorized changes by reviewing who has access.

### Review Current Access
1. Go to **Settings** → **Collaborators and teams** (left sidebar)
2. Review the list of people with access
3. Check their permission levels:
   - **Admin**: Full control (use sparingly)
   - **Maintain**: Manage repository without destructive access
   - **Write**: Push code, merge PRs
   - **Read**: View and clone only

### Recommended Actions
- **Remove** any collaborators you don't recognize
- **Downgrade** permissions for collaborators who don't need write access
- **Enable** "Allow auto-merge" if you want automated PR merging after checks pass
- **Consider** requiring 2FA for all collaborators (under Organization settings if applicable)

### Outside Collaborators
If you have external contributors:
- Grant **Write** access only when necessary
- Use **Pull Request reviews** (see Branch Protection) to gate their changes
- Remove access when collaboration ends

---

## 3. Branch Protection Rules

Prevent breaking changes to `main` by requiring status checks and reviews before merging.

### Configure Protection for `main`
1. Go to **Settings** → **Branches** (left sidebar)
2. Under **Branch protection rules**, click **Add rule** (or edit existing `main` rule)
3. Enter branch name pattern: `main`

### Recommended Protection Settings

#### ✅ Require a pull request before merging
- **Enable**: Forces all changes to go through PR workflow
- **Require approvals**: Set to **1** (at least one reviewer must approve)
- **Dismiss stale pull request approvals when new commits are pushed**: Recommended
- **Require review from Code Owners**: Optional (create `CODEOWNERS` file if needed)

#### ✅ Require status checks to pass before merging
- **Enable**: Ensures CI/tests pass before merge
- **Require branches to be up to date before merging**: Recommended (prevents stale merges)
- **Status checks that are required**:
  - Add: `CodeQL` (from your CodeQL analysis workflow)
  - Add: `Analyze` (from CodeQL Scan job)
  - *(Note: `CI` workflow is currently empty, but add it here once you populate `ci.yml`)*

#### ✅ Require conversation resolution before merging
- **Enable**: Ensures all review comments are addressed

#### ✅ Require signed commits (Optional but Recommended)
- **Enable**: Cryptographically sign commits for added security
- **Setup**: Contributors must configure GPG keys locally
  ```bash
  git config --global commit.gpgsign true
  git config --global user.signingkey YOUR_GPG_KEY_ID
  ```

#### ✅ Require linear history (Optional)
- **Enable**: Prevents merge commits, enforces rebase or squash
- **Useful for**: Clean commit history

#### ✅ Do not allow bypassing the above settings
- **Enable**: Even admins must follow the rules
- **Or**: Allow admins to bypass (useful for emergency hotfixes)

#### ❌ Require deployments to succeed before merging (Skip for now)
- Not needed unless you have pre-merge deployment environments

#### ✅ Lock branch (Optional)
- Use only if you want `main` to be read-only temporarily

### After Configuration
- Click **Create** or **Save changes**
- Test by creating a new PR and verifying checks are enforced

---

## 4. Additional Security Recommendations

### Enable Dependabot
1. **Settings** → **Security** → **Code security and analysis**
2. Enable:
   - **Dependency graph**: Already enabled (shows dependencies)
   - **Dependabot alerts**: Get notified of vulnerabilities in `requirements.txt`
   - **Dependabot security updates**: Auto-create PRs to fix vulnerabilities
   - **Dependabot version updates**: Optional (auto-update dependencies)

### Enable CodeQL (Already Active)
- Your repository already has CodeQL scanning via `.github/workflows/codeql-analysis.yml`
- View results: **Security** tab → **Code scanning**

### Enable Secret Scanning
1. **Settings** → **Security** → **Code security and analysis**
2. Enable **Secret scanning**: Detects accidentally committed credentials

### Repository Visibility
- Current: **Private** (recommended for production systems)
- If you make it public, ensure no secrets are in code or commit history

---

## 5. Workflow-Specific Notes

### `deploy-pi.yml` Workflow
- **Trigger**: Manual (`workflow_dispatch`) or push to `main`
- **Actions**:
  1. Checkout code
  2. Setup SSH using `SSH_PRIVATE_KEY` secret
  3. Rsync code to Pi at `$PI_USER@$PI_HOST:/home/$PI_USER/rdwc`
  4. Restart `rdwc.service` systemd service
- **Security**: Secrets never appear in logs (masked by GitHub Actions)

### `ci.yml` Workflow (Currently Empty)
To re-enable CI checks:
1. Restore the CI workflow content (test matrix, linters, pytest)
2. Add `CI` as a required status check in branch protection
3. Ensure tests pass before merging PRs

### `codeql-analysis.yml` Workflow
- **Status**: Active and passing
- **Scans**: Python code for security vulnerabilities
- **Reports**: Visible in Security tab

---

## 6. Quick Reference Checklist

- [ ] **Secrets added**: `SSH_PRIVATE_KEY`, `PI_HOST`, `PI_USER`
- [ ] **Collaborators reviewed**: Only trusted users with appropriate permissions
- [ ] **Branch protection on `main`**: Require PR reviews and status checks
- [ ] **Signed commits configured**: Optional but recommended
- [ ] **Dependabot enabled**: Auto-detect vulnerabilities
- [ ] **Secret scanning enabled**: Prevent credential leaks
- [ ] **Test workflow**: Create a test PR and verify checks run

---

## 7. Testing Your Setup

### Test Deployment Workflow
1. Merge PR #34 (fix-deploy-workflow)
2. Go to **Actions** tab
3. Select **Deploy to Raspberry Pi** workflow
4. Click **Run workflow** → choose `main` branch → **Run workflow**
5. Monitor logs to verify SSH connection and rsync succeed

### Test Branch Protection
1. Create a new branch: `git checkout -b test-branch-protection`
2. Make a small change (e.g., update README)
3. Push and create a PR
4. Verify:
   - You cannot merge without required checks passing
   - You cannot merge without 1 approval (if configured)
   - You get clear status indicators on the PR page

---

## Support & Troubleshooting

### Deployment Fails with "Permission denied (publickey)"
- Verify `SSH_PRIVATE_KEY` secret matches the public key on your Pi
- Check Pi user's `~/.ssh/authorized_keys` file
- Test SSH locally: `ssh -i ~/.ssh/id_ed25519 pi@192.168.88.49`

### Status Checks Never Complete
- Verify workflow YAML syntax is correct
- Check workflow run logs in **Actions** tab for errors
- Ensure workflow has `push:` or `pull_request:` triggers

### Branch Protection "Required status check not found"
- Status check names must match job names in workflow files
- Wait for at least one workflow run to complete on a PR
- Then the status check will appear in the dropdown

---

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Managing GitHub Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
- [Dependabot Configuration](https://docs.github.com/en/code-security/dependabot)

---

**Last Updated**: 2025-11-11  
**Repository**: collinerasmus/RDWC-v4  
**Maintainer**: @collinerasmus
