import subprocess

owner = "tanderson11"
repo  = "nethack-agent"

with open('secrets/pat.txt', 'r') as f:
    pat = f.readlines()

def get_git_revision_hash() -> str:
    return subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()

def get_git_revision_short_hash() -> str:
    return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()

def commit(path, branch='assets', push=False):
    # save current branch info
    start_branch = subprocess.check_output(['git', 'branch', '--show-current']).decode('ascii').strip()
    # stash local changes (won't stash created files)
    stash_output = subprocess.check_output(['git', 'stash']).decode('ascii').strip()
    did_stash = (stash_output != "No local changes to save")
    # checkout to target branch
    subprocess.run(['git', 'checkout', branch])
    # add target file (directory often)
    subprocess.run(['git', 'add', '-f', path])
    # commit
    subprocess.run(['git', 'commit', '-m', 'Commit by agent.'])
    # get short hash of the new commit we made, which is our retvalue
    commit_sha = get_git_revision_hash()
    # push if desired
    if push:
        subprocess.run(['git', 'push'])
    # go back to original branch
    subprocess.run(['git', 'checkout', start_branch])
    # pop the stash if there were local changes
    if did_stash:
        subprocess.run(['git', 'stash', 'pop'])
    
    return commit_sha
    

