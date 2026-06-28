# GitHub Repository Setup for Updates

## Step 1: Create GitHub Account
1. Go to https://github.com
2. Sign up for a free account if you don't have one

## Step 2: Create Repository
1. Click the "+" icon in the top-right corner
2. Select "New repository"
3. Repository name: `UltimateAI` (or your preferred name)
4. Make it **Public** (required for free updates)
5. Click "Create repository"

## Step 3: Push Your Code
Open a terminal in your project directory and run:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/UltimateAI.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

## Step 4: Create First Release
1. Go to your repository on GitHub
2. Click "Releases" on the right side
3. Click "Create a new release"
4. **Tag version**: `v1.0.0` (must start with "v")
5. **Release title**: `Version 1.0.0`
6. **Description**: `Initial release of UltimateAI`
7. Click "Publish release"

## Troubleshooting: Can't Publish Release

If you can save as draft but can't publish:

### 1. Check Tag Format
- Tag must start with "v" (e.g., `v1.0.0`, not `1.0.0`)
- Tag must be unique (can't reuse existing tags)

### 2. Check Repository Permissions
- Make sure you have write access to the repository
- If it's an organization repo, check your permissions

### 3. Check Account Status
- GitHub may require email verification for new accounts
- Check your email for verification requests

### 4. Check Branch Protection
- If main branch is protected, you might need to create the tag locally:
  ```bash
  git tag v1.0.0
  git push origin v1.0.0
  ```

### 5. Alternative: Create Tag via Git CLI
If GitHub UI doesn't work, create the tag from command line:
```bash
git tag v1.0.0
git push origin v1.0.0
```
Then go to GitHub Releases and the tag will appear automatically.

## Step 5: Add Installer to Release (Optional)
For automatic updates, you'll need to build an installer:
1. Use PyInstaller or similar to create an EXE
2. Attach the EXE file to your GitHub release
3. The update system will download this file

## Step 6: Configure Update System
Once you have your repository URL, update `update_config.json`:
```json
{
  "manifest_url": "https://api.github.com/repos/YOUR_USERNAME/UltimateAI/releases/latest"
}
```

Replace `YOUR_USERNAME` with your GitHub username.

## Testing
After setup:
1. Create a new release with tag `v2.0.0`
2. Click "Check for Updates" in the app
3. It should detect the new version
