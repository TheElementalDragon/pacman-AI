import torch
import pygame
import torch.nn as nn
import numpy as np

from network import FeedForwardNN
from torch.distributions import MultivariateNormal
from torch.optim import Adam
from plotter import plot

class PPO:
	def __init__(self, env):
		# Initialize hyperparameters
		self._init_hyperparameters()

		# Extract environment information
		self.env = env
		self.obs_dim = env.observations()
		self.act_dim = env.actions()

		# Initialize actor and critic networks
		self.actor = FeedForwardNN(self.obs_dim, self.hidden_dim, self.hidden_count, self.act_dim)
		self.critic = FeedForwardNN(self.obs_dim, self.hidden_dim, self.hidden_count, 1)

		self.actor.to("cuda" if torch.cuda.is_available() else "cpu")
		self.critic.to("cuda" if torch.cuda.is_available() else "cpu")

		# Load actor and critic if specified
		if self.load_model:
			self.actor.load_state_dict(torch.load("./models/actor.pth"))
			self.critic.load_state_dict(torch.load("./models/critic.pth"))

		# Initialize optimizors
		self.actor_optim = Adam(self.actor.parameters(), lr=self.lr)
		self.critic_optim = Adam(self.critic.parameters(), lr=self.lr)

		# Create the covariance matrix for get_actioin
		self.cov_var = torch.full(size=(self.act_dim,), fill_value=0.5)
		self.cov_mat = torch.diag(self.cov_var)

		# Initialize the values to plot
		self.scores = []
		self.mean_scores = []

	def learn(self, total_timesteps):
		t_so_far = 0 # timesteps so far

		while t_so_far < total_timesteps:
			# ALG STEP 3
			batch_obs, batch_acts, batch_log_probs, batch_rtgs, batch_lens = self.rollout()

			# Calculate how many timesteps we collected this batch
			t_so_far += np.sum(batch_lens)

			# Calculate V_{phi, k}
			V, _ = self.evaluate(batch_obs, batch_acts)

			# ALG STEP 5
			# Calculate advantage
			A_k = batch_rtgs - V.detach()

			# Normalize advantages
			A_k = (A_k - A_k.mean()) / (A_k.std() + 1e-10)

			for _ in range(self.n_updates_per_iteration):
				# Calculate pi_theta(a_t | s_t)
				V, curr_log_probs = self.evaluate(batch_obs, batch_acts)

				# Calculate ratios
				ratios = torch.exp(curr_log_probs - batch_log_probs)

				# Calculate surrogate losses
				surr1 = ratios * A_k
				surr2 = torch.clamp(ratios, 1 - self.clip, 1 + self.clip) * A_k

				actor_loss = (-torch.min(surr1, surr2)).mean()
				critic_loss = nn.MSELoss()(V, batch_rtgs)

				# Calculate gradients and perform backward propagation for actor
				# network
				self.actor_optim.zero_grad()
				actor_loss.backward()
				self.actor_optim.step()

				# Calculate gradients and perform backward propagation for critic network
				self.critic_optim.zero_grad()
				critic_loss.backward()
				self.critic_optim.step()


	def evaluate(self, batch_obs, batch_acts):
		# Query critic network for a value V for each obs in batch_obs.
		V = self.critic(batch_obs).squeeze()

		# Calculate the log probabilities of batch actions using most
		# recent actor network.
		# This segment of code is similar to that in get_action()
		mean = self.actor(batch_obs)
		dist = MultivariateNormal(mean, self.cov_mat)
		log_probs = dist.log_prob(batch_acts)

		# Return the value vector V of each observation in the batch
		# and log probabilities log_probs of each action in the batch
		return V, log_probs

	def _init_hyperparameters(self):
		# Default values for hyperparameters, will need to change later.
		self.timesteps_per_batch = 10_000       # timesteps per batch
		# self.max_timesteps_per_episode = 128000      # timesteps per episode (not in use as an episode lats until game over)
		self.gamma = 0.95
		self.n_updates_per_iteration = 5
		self.clip = 0.2
		self.lr = 0.005
		self.hidden_dim = 500
		self.hidden_count = 100
		self.load_model = False

	def rollout(self):
		# Batch data
		batch_obs = []             # batch observations
		batch_acts = []            # batch actions
		batch_log_probs = []       # log probs of each action
		batch_rews = []            # batch rewards
		batch_rtgs = []            # batch rewards-to-go
		batch_lens = []            # episodic lengths in batch

		# Number of timesteps run so far this batch
		t = 0

		while t < self.timesteps_per_batch:
			# Rewards this episode
			ep_rews = []

			obs = self.env.reset()
			done = False

			ep_t = 0

			while(not done):
				# Increment timesteps ran this batch so far
				ep_t += 1
				t += 1

				# Collect observation
				batch_obs.append(obs)
				action, log_prob = self.get_action(obs)

				move = action.argmax()
				direction = pygame.K_UP

				match move:
					case 0:
						direction = pygame.K_UP
					case 1:
						direction = pygame.K_RIGHT
					case 2:
						direction = pygame.K_DOWN
					case 3:
						direction = pygame.K_LEFT

				obs, rew, done = self.env.step(direction)

				# Collect reward, action, and log prob
				ep_rews.append(rew)
				batch_acts.append(action)
				batch_log_probs.append(log_prob)

			# Plot results
			# self.scores.append(env.get_score())
			# self.mean_scores.append(np.mean(self.scores))
			plot(env.get_score())

			# Collect episodic length and rewards
			batch_lens.append(ep_t + 1) # plus 1 because timestep starts at 0
			batch_rews.append(ep_rews)

		# Reshape data as tensors in the shape specified before returning
		batch_obs = torch.tensor(batch_obs, dtype=torch.float)
		batch_acts = torch.tensor(batch_acts, dtype=torch.float)
		batch_log_probs = torch.tensor(batch_log_probs, dtype=torch.float)

		# ALG STEP #4
		batch_rtgs = self.compute_rtgs(batch_rews)

		# Return the batch data
		return batch_obs, batch_acts, batch_log_probs, batch_rtgs, batch_lens

	def get_action(self, obs):
		# Query the actor network for a mean action.
		# Same thing as calling self.actor.forward(obs)
		mean = self.actor(obs)

		# Create our Multivariate Normal Distribution
		dist = MultivariateNormal(mean, self.cov_mat)

		# Sample an action from the distribution and get its log prob
		action = dist.sample()
		log_prob = dist.log_prob(action)

		# Return the sampled action and the log prob of that action
		# Note that I'm calling detach() since the action and log_prob
		# are tensors with computation graphs, so I want to get rid
		# of the graph and just convert the action to numpy array.
		# log prob as tensor is fine. Our computation graph will
		# start later down the line.
		return action.detach().numpy(), log_prob.detach()

	def compute_rtgs(self, batch_rews):
		# The rewards-to-go (rtg) per episode per batch to return.
		# The shape will be (num timesteps per episode)
		batch_rtgs = []

		# Iterate through each episode backwards to maintain same order
		# in batch_rtgs
		for ep_rews in reversed(batch_rews):
			discounted_reward = 0 # The discounted reward so far
			for rew in reversed(ep_rews):
				discounted_reward = rew + discounted_reward * self.gamma
				batch_rtgs.insert(0, discounted_reward)

		# Convert the rewards-to-go into a tensor
		batch_rtgs = torch.tensor(batch_rtgs, dtype=torch.float)
		return batch_rtgs

from pacman import GameInstance
env = GameInstance()
model = PPO(env)
model.learn(100_000)
model.actor.save("actor.pth")
model.critic.save("critic.pth")