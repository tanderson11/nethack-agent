![Nethack Banner](https://aicrowd-production.s3.eu-central-1.amazonaws.com/misc/neurips-2021-nethack-challenge-media/nethack_final_link+preview_starter_kit.jpg)

# **[Facebook AI Research - The NetHack Challenge](https://nethackchallenge.com/report.html)**

# Table of Contents
1. [Intro](#intro)
2. [Installing the package](#installation)
3. [Package structure](#structure)
4. [Future direction](#future)

# [Intro][intro]

This repository is the submission from the StudentsOfStone (@tanderson11 and @canderson) to the 2021 NetHack Challenge sponsored by Facebook AI Research. The NetHack Challenge was a competition to build an agent &mdash; either a traditional "symbolic" agent or a machine learning agent &mdash; to play the 1987 computer game NetHack.

Despite its simple text-based graphics, NetHack is challenging and complicated. Casual players routinely play the game for years without ever winning ("ascending"), and one playthrough of the game may take many hours to complete but end instantly when an unforseen threat (a black dragon? a splintered drawbridge?) punishes the player for an ill-planned keystroke. Over decades of development, the world of NetHack has grown into a spiked mass of corner cases. Levitating and trying to move? Try throwing an apple in the opposite direction and profit from the conservation of momentum. Hungry? Try eating a tin of food &mdash; but don't eat slippery fried food on top of a stairwell and then pick up a glass bottle, it might slip through your fingers and break as it falls down the stairs. NetHack a museum of physical comedy reminiscent of the Three Stooges or Road Runner. Every monster, item, and trap appears to the player as a single ASCII character on their screen. And every event in the game &mdash; brutal defeats and rare victories alike &mdash; is communicated to the player one line at a time in a text field above the map.

It's not surprising that NetHack is a challenge for artificial intelligence. Planning effective turns can require an encyclopedic knowledge of what challenges different enemies present. On top of that, the player's interface with the game is often the first victim of dangerous foes. If a raven scratches your eyes, you become temporarily blind. Then, even the slim affordance of one letter on screen per enemy is retracted, as the display doesn't update until you smash headfirst into a wall. And, when forced to hallucinate, players might encounter tribbles from Star Trek, snarks from Lewis Carroll's *The Hunting Of*, or simply "existential angst" (from my real life?).

For this challenge, Facebook AI Research equipped players with the [NetHack Learning Environment](https://github.com/facebookresearch/nle) (NLE) &mdash; a wrapper around NetHack's C executable that makes the screen accessible as a Python array to agents in between each turn. We approached the NetHack challenge with the goal of building a symbolic bot that knows a few simple strategies but can access an enriched representation of the state of the game on each turn. By investing in technology to parse the game messages and to turn the condensed environment (the grid of characters) into a full representation of enemies, geometry, and items, we were able to teach our agent simple heuristics for best play. Our approach was successful, and our agent won the [2nd prize overall](https://nethackchallenge.com/report.html) in the competition. We're optimisic about the potential for this approach to achieve a game victory, and we look forwards to spending more time in the future to realize this goal.

# [Installing the package][installation]

To test or extend our agent, first clone this git repository and then install requirements. We manage dependencies through [Poetry](https://python-poetry.org/docs/), which makes it easy to manage specific versions of required packages. The steps to install this repository are simple:

- Clone the repository.
- Install Poetry (see [the docs](https://python-poetry.org/docs/)).
- Execute `poetry install` from the root of the repository.

# [Package structure][#structure]

## Starter kit and submission 

The following default file structure is in place as provided in the starter kit.
```
.
├── aicrowd.json                  # Submission meta information - add tags for tracks here
├── apt.txt                       # Packages to be installed inside submission environment
├── requirements.txt              # Python packages to be installed with pip
├── rollout.py                    # This will run rollouts on a batched agent
├── test_submission.py            # Run this on your machine to get an estimated score
├── run.sh                        # Submission entrypoint
├── utilities                     # Helper scripts for setting up and submission 
│   └── submit.sh                 # script for easy submission of your code
├── envs                          # Operations on the env like batching and wrappers
│   ├── batched_env.py            # Batching for multiple envs
│   └── wrappers.py   	          # Add wrappers to your env here
├── agents                        # Baseline agents for submission
│   ├── batched_agent.py          # Abstraction reference batched agents
│   ├── random_batched_agent.py	  # Batched agent that returns random actions
│   ├── rllib_batched_agent.py	  # Batched agent that runs with the rllib baseline
│   └── torchbeast_agent.py       # Batched agent that runs with the torchbeast baseline
├── nethack_baselines             # Baseline agents for submission
│    ├── other_examples  	
│    │   └── random_rollouts.py   # Barebones random agent with no batching
│    ├── rllib	                  # Baseline agent trained with rllib
│    └── torchbeast               # Baseline agent trained with IMPALA on Pytorch
└── notebooks                 
    └── NetHackTutorial.ipynb     # Tutorial on the Nethack Learning Environment

```

## Agent

The code for the agent is layed out as follows:

```
.
├── unit_tests.py                 # Unit tests.
├── pyproject.toml                # Package dependencies.
├── environment_files             # Files to `source` to set shell environment variables
│   ├── development.env           # Debugging is on and multithreading is off
│   ├── good_roles.env            # Agent quits unless it gets a 'good' role.
│   └── test_run.env   	          # Like the conditions for competition submission.
└── agents                        # Baseline agents for submission
    ├── custom_agent.py           # Core logic to track state and input action on turn.
    ├── representation            # Module for enriching representations of game observation.
    │   ├── spoilers              # Files that describe NetHack game objects.
    │   │   └── many files
    │   ├── character.py          # State about player's status and attributes.
    │   ├── constants.py          # NetHack constants.
    │   ├── glyphs.py             # Mappings of glyphs to game entities.
    │   ├── inventory.py          # Parsers of item strings into item objects.
    │   ├── map.py                # State about level geometry and connectivity.
    │   ├── monster_messages.py   # Methods for identifying what monster is acting.
    │   ├── neighborhood.py       # Vision, pathfinding, and state about local geometry.
    │   └── physics.py            # Mappings of directions and actions.
    ├── advice                    # Implementations of specific strategies.
    │   ├── advisors.py           # Specific advisors that can execute stratgems.
    │   ├── advisor_sets.py       # Ranked sets of advisors that form complete strategies. 
    │   ├── menuplan.py           # Methods for navigating menus in the game.
    │   ├── preferences.py        # Preferred way to take certain actions.
    │   └── wish.py               # Knowledge of what to wish for and how.
    └── wizmode                   # Tools for entering wizard mode to test certain game conditions.
        └── wizmodeprep.py        # Routines for accumulating powerful items to debug.
```

# [Future directions][future]


## Agent contributors
- [Thayer Anderson](https://github.com/tanderson11)
- [Christian Anderson](https://github.com/canderson)

## NetHack Challenge starter kit contributors

- [Dipam Chakraborty](https://www.aicrowd.com/participants/dipam)
- [Shivam Khandelwal](https://www.aicrowd.com/participants/shivam)
- [Eric Hambro](https://www.aicrowd.com/participants/eric_hammy)
- [Danielle Rothermel](https://www.aicrowd.com/participants/danielle_rothermel)
- [Jyotish Poonganam](https://www.aicrowd.com/participants/jyotish)
