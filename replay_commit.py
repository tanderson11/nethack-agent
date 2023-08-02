import sys
import nh_git

if len(sys.argv) != 2:
    raise ValueError("expected commit sha as argument")

commit_sha = sys.argv[1]
cherry_pick_output = nh_git.cherry_pick(commit_sha)
nh_git.revert(commit_sha)

import pdb; pdb.set_trace()