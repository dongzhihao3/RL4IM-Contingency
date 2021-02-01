import os
import time
import json
import random

import tqdm
import numpy as np
import torch as th
import matplotlib.pyplot as plt

from src.utils.logging import Logger
from src.utils.os_utils import generate_id
import ipdb


class Runner:
    def __init__(self, args, environment, agent, verbose=True, logger: Logger=None):
        self.environment = environment
        self.agent = agent
        self.verbose = verbose
        self.logger = logger
        self.args = args
        self.results_path = self.args.local_results_path
        os.makedirs(self.results_path, exist_ok=True)
        self.model_path = os.path.join(self.results_path, 'models')
        os.makedirs(self.model_path, exist_ok=True)

    def step(self):
        # observation = self.environment.observe().clone()
        # action = self.agent.act(observation).copy()
        # reward, done = self.environment.act(action)
        # self.agent.reward(observation, action, reward,done)
        # return observation, action, reward, done
        pass

    def evaluate(self, num_episode=5):
        """ Start evaluation """
        print('----------------------------------------------start evaluation---------------------------------------------------------')
        episode_accumulated_rewards = []
        feasible_actions = list(range(self.environment.N))
        mode = 'test'

        #the last graph in graphs is the test graph 
        #g_index = random.choice([i for i, g in enumerate(self.environment.graphs) if i != self.environment.graph_index])
        g_index = self.args.graph_nbr_train #TODO: use one test graph for sanity chaeck, use all test graphs at last
        print('graph index: ', g_index)
        #ipdb.set_trace()
        g_name = self.environment.graphs[g_index].graph_name
        print('graph: {}, nodes: {}, edges: {}'.format(g_index, len(self.environment.graphs[g_index].nodes), len(self.environment.graphs[g_index].edges)))

        if self.agent.method == 'RL':
            for episode in range(num_episode):
                # select other graphs
                self.environment.reset(g_index=g_index, mode=mode)
                #TODO: revise agent.py to disginguish train/test
                self.agent.reset(g_index=g_index, mode=mode)  
                feasible_actions = list(range(self.environment.N))
                accumulated_reward = 0
                pri_action = [ ]
                invited = []
                presents = []

                for i in range(1, self.environment.T+1):
                    state = self.environment.state.copy()
                    sec_action = self.agent.act(th.from_numpy(state).float().transpose(1, 0)[None, ...],
                                            feasible_actions=feasible_actions.copy(), mode=mode)
                    #print('feasible actions: ',feasible_actions)
                    feasible_actions = self.environment.try_remove_feasible_action(feasible_actions, sec_action)
                    #print('feasible actions: ',feasible_actions)
                    pri_action.append(sec_action)
                    next_state, _, done = self.environment.step(i, pri_action, sec_action=sec_action)

                    if i % self.environment.budget == 0:
                        present, _ = self.environment.transition(pri_action)
                        presents += present
                        invited += pri_action
                        pri_action=[ ]

                    if done:
                        accumulated_reward = self.environment.run_cascade(seeds=presents, cascade=self.environment.cascade, sample=self.environment.num_simul)
                        episode_accumulated_rewards.append(accumulated_reward)
                        print('accumulated reward of episode {} is: {}'.format(episode, accumulated_reward))
                        print('invited: ', invited)
                        print('present: ', presents) 
        else:
            print('method is :', self.agent.method)
            for episode in range(num_episode):
                self.environment.reset(test_mode=True)
                feasible_actions = list(range(self.environment.N))
                invited = []
                presents = []
                accumulated_reward = 0
                for i in range(1, self.environment.T+1):
                    if (i-1) % self.environment.budget == 0:
                        #note that the other methods select budget number of nodes a time
                        print('step: {}, feasible actions: {}'.format(i, len(feasible_actions)))
                        pri_action, _ = self.agent.act(feasible_actions,self.environment.budget,self.environment.f_multi,presents)
                        invited+=pri_action
                        present, _ = self.environment.transition(pri_action)
                        presents+=present
                    for sec_action in pri_action:
                        feasible_actions = self.environment.try_remove_feasible_action(feasible_actions, sec_action)

                    if i == self.environment.T:
                        accumulated_reward = self.environment.run_cascade(seeds=presents, cascade=self.environment.cascade, sample=self.environment.num_simul)
                        episode_accumulated_rewards.append(accumulated_reward)
                        print('accumulated reward of episode {} is: {}'.format(episode, accumulated_reward))
                        print('invited: ', invited)
                        print('present: ', presents)
        ave_cummulative_reward = np.mean(episode_accumulated_rewards)
        print('average cummulative reward is: ', ave_cummulative_reward)
        print('----------------------------------------------end evaluation---------------------------------------------------------')
        print(' ')
        return g_name, ave_cummulative_reward 
    
    def loop(self):

        cumul_reward = 0.0
        graph_cumul_reward = {}
        graph_eval_reward = {}
        mode = 'train'
        st = time.time()

        for epoch in range(self.args.nbr_epoch):
            print('epoch: ', epoch)
            for g_index in range(self.args.graph_nbr_train):  # graph list; first  graph_nbr_train graphs are training, the rest are for test
                graph_name = self.agent.graphs[g_index].graph_name
                print('graph: {}, nodes: {}, edges: {}'.format(g_index, len(self.environment.graphs[g_index].nodes), len(self.environment.graphs[g_index].edges)))
                for episode in range(self.args.max_episodes):
                    print('episode: {}'.format(episode))
                    self.environment.reset(g_index=g_index)
                    self.agent.reset(g_index)  
                    cumul_reward = 0.0
                    pri_action = [ ]
                    feasible_actions = list(range(self.environment.N))

                    for i in range(1, self.environment.T+1):
                        state = self.environment.state.copy()
                        if (i-1) % self.environment.budget == 0:
                            pri_action=[ ]
                        sec_action = self.agent.act(th.from_numpy(state).float().transpose(1, 0)[None, ...], 
                                                feasible_actions=feasible_actions.copy(), mode=mode)

                        feasible_actions = self.environment.try_remove_feasible_action(feasible_actions, sec_action)
                        pri_action.append(sec_action)
                        next_state, reward, done = self.environment.step(i, pri_action, sec_action=sec_action)

                        # learning the model
                        loss = self.agent.reward(th.from_numpy(state).float().transpose(1, 0)[None, ...], sec_action, reward, done)
                        cumul_reward += reward
                        print(f"[INFO] Global_t: {self.agent.global_t}, Episode_t: {i}, Action: {sec_action}, Reward: {reward:.2f}, Epsilon: {self.agent.curr_epsilon:.2f}")
                        
                        # save the model
                        if (self.agent.global_t + 1) % 100 == 0:
                            self.agent.save_model(self.model_path)

                        if done:
                            print(f"[INFO] Global step: {self.agent.global_t}, Cumulative rewards: {cumul_reward}, Runtime (s): {(time.time()-st):.2f}")
                            print('--------------------------------------')
                            print(' ')
                            self.logger.log_stat(key=f'{graph_name}/episode_reward', 
                                                 value=cumul_reward, 
                                                 t=self.agent.global_t)
                            if loss is not None:
                                self.logger.log_stat(key=f'{graph_name}/loss', 
                                                     value=loss.detach().cpu().numpy(), 
                                                     t=self.agent.global_t)
                            

                            if graph_name not in graph_cumul_reward:
                                graph_cumul_reward[graph_name] = [cumul_reward]
                            else:
                                graph_cumul_reward[graph_name].append(cumul_reward)

                            break    
        
                    if (episode+ 1)*(g_index+1)*(epoch+1) % 10 == 0:
                        graph_name, mean_eval_reward = self.evaluate(num_episode=5)
                        if graph_name not in graph_eval_reward:
                            graph_eval_reward[graph_name] = [mean_eval_reward]
                        else:
                            graph_eval_reward[graph_name].append(mean_eval_reward)
                        
                        self.logger.log_stat(key=f'{graph_name}/eval_episode_reward', 
                                             value=mean_eval_reward, 
                                             t=self.agent.global_t)

                #if self.verbose:
                    #print(" <=> Finished game number: {} <=>".format(g_index))
                    #print("")

        with open(os.path.join(self.results_path, 'train_episode_rewards.json'), 'w') as f:
            json.dump(graph_cumul_reward, f, indent=4)
            
        with open(os.path.join(self.results_path, 'eval_episode_rewards.json'), 'w') as f:
            json.dump(graph_eval_reward, f, indent=4)
        
        return cumul_reward


def iter_or_loopcall(o, count):
    if callable(o):
        return [ o() for _ in range(count) ]
    else:
        # must be iterable
        return list(iter(o))


class BatchRunner:
    """
    Runs several instances of the same RL problem in parallel
    and aggregates the results.
    """

    def __init__(self, env_maker, agent_maker, count, verbose=False):
        self.environments = iter_or_loopcall(env_maker, count)
        self.agents = iter_or_loopcall(agent_maker, count)
        assert(len(self.agents) == len(self.environments))
        self.verbose = verbose
        self.ended = [ False for _ in self.environments ]

    def game(self, max_iter):
        rewards = []
        for (agent, env) in zip(self.agents, self.environments):
            env.reset()
            agent.reset()
            game_reward = 0
            for i in range(1, max_iter+1):
                observation = env.observe()
                action = agent.act(observation)
                (reward, stop) = env.act(action)
                agent.reward(observation, action, reward)
                game_reward += reward
                if stop :
                    break
            rewards.append(game_reward)
        return sum(rewards)/len(rewards)

    def loop(self, games,nb_epoch, max_iter):
        cum_avg_reward = 0.0
        for epoch in range(nb_epoch):
            for g in range(1, games+1):
                st_time = time.time()
                avg_reward = self.game(max_iter)
                cum_avg_reward += avg_reward
                ts = time.time() - st_time
                if self.verbose:
                    print("Simulation game {}:".format(g))
                    print(" ->            average reward: {}".format(avg_reward))
                    print(" -> cumulative average reward: {}".format(cum_avg_reward))
                    print(" -> expected total seconds: {:.2f}".format(ts * nb_epoch * games))
        return cum_avg_reward
