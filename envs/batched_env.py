import environment

def log_new_run(env):
    if not (environment.env.print_seed or environment.env.debug): return
    env = env.unwrapped
    core_seed, disp_seed, reseed = env.get_seeds()
    print(f"[{env._episode} {reseed} {core_seed} {disp_seed}] Starting run.")

class InstrumentedEnv:
    def __init__(self, env_make_fn, seeds=[]):
        """
        Creates multiple copies of the environment with the same env_make_fn function
        """
        self.seeds = seeds
        self.env_make_fn = env_make_fn
        env, observation = self.make_environment()
        self.env = env
        self.initial_observation = observation
        self.initial_seeds = []
        self.num_actions = self.env.action_space.n

    def next_seed(self):
        if not self.seeds:
            return None
        return self.seeds.pop(0)

    def make_environment(self):
        env = self.env_make_fn()
        observation = self.reset_environment(env)
        return env, observation

    @staticmethod
    def seeded():
        return environment.env.use_seed_whitelist or environment.env.debug or environment.env.print_seed

    def reset_environment(self, env):
        next_seed = self.next_seed()
        if next_seed:
            env.unwrapped.seed(next_seed[0], next_seed[1], False)
        else:
            if environment.env.use_seed_whitelist:
                print("Ran out of seeds!")
            if self.seeded():
                env.unwrapped.seed(None, None, False)

        observation = env.reset()
        log_new_run(env)
        return observation

    def run_episode(self, agent):
        observation = self.initial_observation
        reward = 0
        done = False
        info = {}

        total_score = 0
        crashed = False

        try:
            while True:
                action = agent.step(observation, reward, done, info)
                observation, reward, done, info = self.env.step(action)
                total_score += reward
                if done:
                    break
        except Exception as e:
            print(e)
            if environment.env.debug: raise(e)
            crashed = True
        else:
            agent.run_state.log_final_state(reward, info["is_ascended"])
        finally:
            self.initial_observation = self.reset_environment(self.env)
            agent.run_state.reset()


        return info.get("is_ascended", False), crashed, total_score
